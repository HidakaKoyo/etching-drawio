"""Input safety and validation for .drawio sources.

Everything here runs before draw.io is involved, so every failure raised from
this module maps to exit 1 (contracts/exit-codes.md), except dependency and
usage problems which the caller handles.

The XML is parsed with the standard library. External entities and DTDs are
refused before the parser sees them, which is the cheapest place to close XXE:
a document that declares a DTD is rejected outright rather than parsed with a
hardened parser.
"""

import math
import os
import re
import subprocess
import xml.etree.ElementTree as ElementTree

import etch_paths

MAX_BYTES = 8 * 1024 * 1024
MAX_NODES = 200000
MAX_DEPTH = 100
MAX_DIAGNOSTICS_PER_CODE = 50

# Structural subset of shared/mxfile.xsd: which element may contain which.
# Kept as element names only. Attribute typing stays with the XSD check, which
# is optional because it needs xmllint.
ALLOWED_CHILDREN = {
    "mxfile": {"diagram"},
    "diagram": {"mxGraphModel"},
    "mxGraphModel": {"root"},
    "root": {"mxCell", "UserObject", "object"},
    "mxCell": {"mxGeometry"},
    "UserObject": {"mxCell"},
    "object": {"mxCell"},
    "mxGeometry": {"mxPoint", "Array", "mxRectangle"},
    "mxPoint": set(),
    "Array": {"mxPoint"},
    "mxRectangle": set(),
}

RAW_AMPERSAND = re.compile(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z_:][A-Za-z0-9_.:-]*;)")
EXTERNAL_URL = re.compile(r"(?:https?|file)://[^;\s<&\"']+")


class Invalid(Exception):
    """Validation stopped. The report already carries the diagnostics."""


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def first_line(payload):
    lines = payload.decode("utf-8", "replace").strip().splitlines()
    return lines[0] if lines else "(no output)"


class Validator(object):
    def __init__(self, report, root_dir, allow_external=False):
        self.report = report
        self.root_dir = root_dir
        self.allow_external = allow_external
        self.counts = {}

    def problem(self, code, message, file, **subject):
        seen = self.counts.get(code, 0) + 1
        self.counts[code] = seen
        if seen <= MAX_DIAGNOSTICS_PER_CODE:
            self.report.diagnostic(code, message, file, **subject)
        elif seen == MAX_DIAGNOSTICS_PER_CODE + 1:
            self.report.diagnostic(
                code,
                "further occurrences of %s are not listed individually" % code,
                file,
                severity="warning",
            )

    def had(self, *codes):
        return any(self.counts.get(code) for code in codes)

    # -- stages -------------------------------------------------------------

    def read_input(self, path):
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            self.problem(
                "input/too-large",
                "input is %d bytes, over the %d byte limit" % (size, MAX_BYTES),
                path,
                expected=MAX_BYTES,
                actual=size,
            )
            self.report.failed("input/size")
            raise Invalid()
        self.report.passed("input/size")
        with open(path, "rb") as handle:
            return handle.read()

    def reject_doctype(self, payload, path):
        """No DTD, no entity declarations. This is the XXE gate."""
        stripped = re.sub(rb"<!--.*?-->", b"", payload, flags=re.S)
        for marker, code, message in (
            (b"<!DOCTYPE", "input/dtd-forbidden", "the document declares a DTD"),
            (b"<!ENTITY", "input/external-entity", "the document declares an entity"),
        ):
            if marker in stripped:
                line = stripped[: stripped.index(marker)].count(b"\n") + 1
                self.problem(
                    code,
                    "%s; DTDs and entity declarations are refused before parsing" % message,
                    path,
                    line=line,
                )
                self.report.failed("input/no-dtd")
                raise Invalid()
        self.report.passed("input/no-dtd")

    def parse(self, payload, path):
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as error:
            self.problem(
                "xml/not-well-formed",
                "the document is not well-formed XML: %s" % error,
                path,
                line=getattr(error, "position", (None, None))[0],
            )
            self.ampersand_hint(payload, path)
            self.report.failed("xml/well-formed")
            raise Invalid()
        self.report.passed("xml/well-formed")
        return root

    def ampersand_hint(self, payload, path):
        text = payload.decode("utf-8", "replace")
        for number, line in enumerate(text.splitlines(), 1):
            if RAW_AMPERSAND.search(line):
                self.problem(
                    "xml/raw-ampersand",
                    "line %d may contain a raw & that needs escaping as &amp;" % number,
                    path,
                    line=number,
                )
                return

    def check_root(self, root, path):
        name = local_name(root.tag)
        if name != "mxfile":
            self.problem(
                "xml/root-element",
                "the root element is <%s>, expected <mxfile>" % name,
                path,
                expected="mxfile",
                actual=name,
            )
            self.report.failed("xml/root-element")
            raise Invalid()
        self.report.passed("xml/root-element")

    def check_limits(self, root, path):
        nodes = 0
        depth = 0
        stack = [(root, 1)]
        while stack:
            node, level = stack.pop()
            nodes += 1
            depth = max(depth, level)
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                self.problem(
                    "input/too-complex",
                    "the document exceeds the node (%d) or depth (%d) limit"
                    % (MAX_NODES, MAX_DEPTH),
                    path,
                    actual={"nodes": nodes, "depth": depth},
                )
                self.report.failed("input/limits")
                raise Invalid()
            for child in list(node):
                stack.append((child, level + 1))
        self.report.passed("input/limits")

    def check_compression(self, root, diagrams, path):
        """The uncompressed-only policy. Always on in v1 (contracts/profile.md §3)."""
        declared = root.get("compressed")
        if declared != "false":
            self.problem(
                "input/compressed-attribute",
                'the mxfile element does not carry compressed="false" (found %r)' % declared,
                path,
                severity="warning",
                expected="false",
                actual=declared,
            )
            self.report.check("input/compressed-declaration", "failed", required=False)
        else:
            self.report.passed("input/compressed-declaration", required=False)

        offenders = []
        for number, diagram in enumerate(diagrams, 1):
            has_model = any(local_name(child.tag) == "mxGraphModel" for child in list(diagram))
            if has_model:
                continue
            if (diagram.text or "").strip():
                offenders.append(number)
                self.problem(
                    "input/compressed-payload",
                    "page %d carries a compressed diagram body; the uncompressed-only "
                    "policy refuses it instead of converting it silently" % number,
                    path,
                    xpath="/mxfile/diagram[%d]" % number,
                )
            else:
                self.problem(
                    "xml/empty-diagram",
                    "page %d has no mxGraphModel and no body" % number,
                    path,
                    xpath="/mxfile/diagram[%d]" % number,
                )
        if offenders or self.had("xml/empty-diagram"):
            self.report.failed("input/uncompressed-payload")
            raise Invalid()
        self.report.passed("input/uncompressed-payload")

    def check_structure(self, root, path):
        """Element nesting against the structural subset of mxfile.xsd."""
        stack = [(root, "/%s" % local_name(root.tag))]
        while stack:
            node, xpath = stack.pop()
            name = local_name(node.tag)
            allowed = ALLOWED_CHILDREN.get(name)
            if allowed is None:
                self.problem(
                    "xml/unknown-element",
                    "<%s> is not part of the mxfile schema" % name,
                    path,
                    xpath=xpath,
                )
                continue
            for child in list(node):
                child_name = local_name(child.tag)
                child_xpath = "%s/%s" % (xpath, child_name)
                if child_name not in allowed and child_name in ALLOWED_CHILDREN:
                    self.problem(
                        "xml/unexpected-element",
                        "<%s> may not appear inside <%s>" % (child_name, name),
                        path,
                        xpath=child_xpath,
                    )
                stack.append((child, child_xpath))
        if not list(root):
            self.problem("xml/missing-diagram", "the mxfile has no <diagram> page", path)
        if self.had("xml/unknown-element", "xml/unexpected-element", "xml/missing-diagram"):
            self.report.failed("xml/schema")
            raise Invalid()
        self.report.passed("xml/schema")

    def check_xsd(self, path):
        """Optional: full XSD validation, which needs xmllint (environment.md §5)."""
        xsd = etch_paths.bundled(
            self.root_dir, "references", "upstream", "shared", "mxfile.xsd"
        )
        if xsd is None:
            self.report.skipped(
                "xml/schema-xsd",
                waiver={"reason": "bundled mxfile.xsd not found", "authorizedBy": "etch"},
            )
            return
        try:
            completed = subprocess.run(
                ["xmllint", "--noout", "--nonet", "--schema", xsd, path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            self.report.skipped(
                "xml/schema-xsd",
                waiver={"reason": "xmllint is not available", "authorizedBy": "etch"},
            )
            self.report.diagnostic(
                "xml/schema-xsd-skipped",
                "xmllint is not available, so full XSD validation was skipped",
                path,
                severity="warning",
            )
            return
        if completed.returncode != 0:
            self.report.check("xml/schema-xsd", "failed", required=False)
            self.report.diagnostic(
                "xml/schema-xsd-mismatch",
                "xmllint reports the document does not satisfy mxfile.xsd: %s"
                % first_line(completed.stderr),
                path,
                severity="warning",
            )
        else:
            self.report.passed("xml/schema-xsd", required=False)

    # -- semantic lint ------------------------------------------------------

    def lint_pages(self, diagrams, path):
        for number, diagram in enumerate(diagrams, 1):
            model = next(
                (c for c in list(diagram) if local_name(c.tag) == "mxGraphModel"), None
            )
            if model is None:
                continue
            self.lint_model(model, number, path)
        for check_id, codes in (
            ("xml/unique-ids", ("xml/duplicate-cell-id",)),
            ("xml/references", ("xml/missing-reference",)),
            ("xml/geometry", ("xml/invalid-geometry",)),
        ):
            if self.had(*codes):
                self.report.failed(check_id)
            else:
                self.report.passed(check_id)

    def lint_model(self, model, page, path):
        parents = {child: parent for parent in model.iter() for child in list(parent)}
        cells = []
        for node in model.iter():
            if local_name(node.tag) != "mxCell":
                continue
            parent = parents.get(node)
            wrapper = (
                parent
                if parent is not None and local_name(parent.tag) in ("UserObject", "object")
                else None
            )
            inner_id = node.get("id")
            wrapper_id = wrapper.get("id") if wrapper is not None else None
            cells.append((node, inner_id if inner_id is not None else wrapper_id))

        known = set()
        duplicates = set()
        for _, cell_id in cells:
            if cell_id is None:
                continue
            if cell_id in known:
                duplicates.add(cell_id)
            known.add(cell_id)
        for cell_id in sorted(duplicates):
            self.problem(
                "xml/duplicate-cell-id",
                'page %d: mxCell id "%s" is duplicated' % (page, cell_id),
                path,
                cellId=cell_id,
                xpath="/mxfile/diagram[%d]" % page,
            )

        for cell, cell_id in cells:
            identity = cell_id if cell_id is not None else "(no id)"
            for attribute in ("parent", "source", "target"):
                reference = cell.get(attribute)
                if reference is not None and reference not in known:
                    self.problem(
                        "xml/missing-reference",
                        'page %d: mxCell "%s" points at a missing id "%s" through %s'
                        % (page, identity, reference, attribute),
                        path,
                        cellId=cell_id,
                        params={"attribute": attribute, "reference": reference},
                    )
            if cell.get("vertex") == "1":
                geometry = next(
                    (n for n in list(cell) if local_name(n.tag) == "mxGeometry"), None
                )
                for dimension in ("width", "height"):
                    value = geometry.get(dimension) if geometry is not None else None
                    try:
                        number = float(value)
                        ok = math.isfinite(number) and number > 0
                    except (TypeError, ValueError):
                        ok = False
                    if not ok:
                        self.problem(
                            "xml/invalid-geometry",
                            'page %d: vertex "%s" has a %s that is not a positive number (%s)'
                            % (page, identity, dimension, value),
                            path,
                            cellId=cell_id,
                        )

    def check_external_references(self, diagrams, path):
        check_id = "security/no-external-ref"
        if self.allow_external:
            self.report.skipped(
                check_id,
                waiver={"reason": "--allow-external", "authorizedBy": "cli-flag"},
            )
            return
        found = []
        for number, diagram in enumerate(diagrams, 1):
            for node in diagram.iter():
                for attribute in ("style", "image"):
                    for match in EXTERNAL_URL.findall(node.get(attribute, "")):
                        item = (number, attribute, match[:180])
                        if item not in found:
                            found.append(item)
        for number, attribute, url in found:
            self.problem(
                "security/external-ref",
                "page %d: %s references the external resource %s" % (number, attribute, url),
                path,
                severity="warning",
                params={"attribute": attribute, "url": url},
            )
        if found:
            self.report.check(check_id, "failed", required=False)
        else:
            self.report.passed(check_id, required=False)

    def check_page_index(self, page, diagrams, path):
        count = len(diagrams)
        if page > count or page < 1:
            self.problem(
                "input/page-out-of-range",
                "page %d was requested but the document has %d page(s)" % (page, count),
                path,
                expected=count,
                actual=page,
            )
            self.report.failed("input/page-index")
            raise Invalid()
        self.report.passed("input/page-index")


def validate(report, root_dir, path, page=1, allow_external=False):
    """Run every pre-export check. Raises Invalid on the first fatal stage."""
    validator = Validator(report, root_dir, allow_external=allow_external)
    payload = validator.read_input(path)
    validator.reject_doctype(payload, path)
    root = validator.parse(payload, path)
    validator.check_root(root, path)
    validator.check_limits(root, path)
    diagrams = [node for node in list(root) if local_name(node.tag) == "diagram"]
    validator.check_structure(root, path)
    validator.check_compression(root, diagrams, path)
    validator.check_xsd(path)
    validator.lint_pages(diagrams, path)
    validator.check_external_references(diagrams, path)
    validator.check_page_index(page, diagrams, path)
    if report.status() == "failed":
        raise Invalid()
    return len(diagrams)
