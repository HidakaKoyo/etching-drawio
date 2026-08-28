#!/usr/bin/env python3
"""Acceptance: both distribution layouts, installed clean and driven end to end.

contracts/environment.md §6 asks that a distribution be put into a bare
directory and then exercised — dependency resolution, validation, delivery,
verification — without reaching outside itself. This suite is that procedure,
run for each of the two layouts of docs/PLAN.md §9:

  plugin      what a marketplace install leaves in the plugin cache: the repo's
              distributed files copied wholesale, CLI beside the skill
  standalone  what `scripts/build-release.py --bundle` writes: the skill
              directory with the CLI inside it, which is the shape a skill
              copied on its own has to work in

Each install is driven the way skills/etching/SKILL.md tells an agent to drive
it: validate a broken diagram, repair a work copy, re-validate, deliver, verify.
The work happens in a directory outside the install, and the install is reached
only through the resolution order in contracts/environment.md §7, so a layout
that depended on the repo being present would fail here.

draw.io Desktop is not required: export runs against a stub, because what this
suite is about is the layout, not the exporter. Real export is
tests/smoke/test_real_export.py.

    python3 tests/acceptance/test_distribution.py [-v]
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD_RELEASE = os.path.join(REPO_ROOT, "scripts", "build-release.py")

# What a plugin install carries. Tests, docs and the vendoring machinery are
# development-time things and deliberately absent from the install.
PLUGIN_CONTENTS = (
    ".claude-plugin",
    "bin",
    "lib",
    "skills",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "README.md",
)

# The upstream snapshot the skill must carry in either layout, relative to the
# skill directory (docs/closure-allowlist.md).
CLOSURE = (
    "SKILL.md",
    "vendor.lock",
    "VERSION",
    "references/environment.md",
    "references/authoring-contract.md",
    "references/delivery-contract.md",
    "references/upstream/LICENSE",
    "references/upstream/plugins/claude-code/skills/drawio/SKILL.md",
    "references/upstream/shared/xml-reference.md",
    "references/upstream/shared/mermaid-reference.md",
    "references/upstream/shared/style-reference.md",
    "references/upstream/shared/mxfile.xsd",
)

# Two cells share an id and one of them has no width: two diagnostics from one
# validate, so the repair loop has a fix set to build rather than a single edit.
BROKEN = """<mxfile host="etch" compressed="false">
  <diagram id="page-1" name="Page-1">
    <mxGraphModel dx="800" dy="600" grid="1" page="1">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="node-a" value="Author" style="rounded=0;" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
        </mxCell>
        <mxCell id="node-a" value="Validate" style="rounded=0;" vertex="1" parent="1">
          <mxGeometry x="240" y="40" width="0" height="60" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# The same document with the duplicate id made unique and the width made
# positive: one fix set, applied to the work copy.
REPAIRED = BROKEN.replace(
    '<mxCell id="node-a" value="Validate"', '<mxCell id="node-b" value="Validate"'
).replace('width="0"', 'width="120"')

STUB_DRAWIO = """#!/usr/bin/env bash
set -eu
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then out="$arg"; fi
  prev="$arg"
done
if [ -n "$out" ]; then
  printf '<svg xmlns="http://www.w3.org/2000/svg" content="stub"><g/></svg>\\n' > "$out"
fi
exit 0
"""


class Failure(Exception):
    """An acceptance expectation was not met."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# installs
# ---------------------------------------------------------------------------


class Install(object):
    """One distribution, unpacked into a directory of its own."""

    def __init__(self, name, root, skill_dir, etch):
        self.name = name
        self.root = root
        self.skill_dir = skill_dir
        self.etch = etch


def install_plugin(base):
    """What the plugin cache holds after a marketplace install."""
    root = os.path.join(base, "plugins", "etching-drawio")
    os.makedirs(root)
    for entry in PLUGIN_CONTENTS:
        source = os.path.join(REPO_ROOT, entry)
        target = os.path.join(root, entry)
        if os.path.isdir(source):
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        else:
            shutil.copyfile(source, target)
    return Install(
        "plugin",
        root,
        os.path.join(root, "skills", "etching"),
        os.path.join(root, "bin", "etch"),
    )


def install_standalone(base):
    """What `npx skills add` style distribution of the bundle leaves behind."""
    destination = os.path.join(base, "skills")
    os.makedirs(destination)
    completed = subprocess.run(
        [sys.executable, BUILD_RELEASE, "--bundle", destination],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if completed.returncode != 0:
        raise Failure(
            "build-release --bundle failed (%d)\n%s" % (completed.returncode, completed.stderr)
        )
    root = os.path.join(destination, "etching")
    return Install("standalone", root, root, os.path.join(root, "bin", "etch"))


# ---------------------------------------------------------------------------
# driving an install
# ---------------------------------------------------------------------------


class Session(object):
    """A working directory outside the install, plus a stub draw.io on PATH."""

    def __init__(self, install, base):
        self.install = install
        self.root = os.path.join(base, "work-%s" % install.name)
        os.makedirs(self.root)
        self.bin = os.path.join(self.root, "bin")
        os.mkdir(self.bin)
        stub = os.path.join(self.bin, "drawio")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write(STUB_DRAWIO)
        os.chmod(stub, 0o755)
        self.output_root = os.path.join(self.root, "out")
        os.mkdir(self.output_root)

    def write(self, name, content):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def run(self, args):
        """Call etch the way SKILL.md says to: through ETCH_CMD."""
        environ = dict(os.environ)
        environ["PATH"] = self.bin + os.pathsep + environ.get("PATH", "")
        environ["ETCH_CMD"] = self.install.etch
        # ETCH_ROOT is what bin/etch sets for itself; clearing an inherited one
        # keeps a stray value from the parent shell out of the result.
        environ.pop("ETCH_ROOT", None)
        return subprocess.run(
            [environ["ETCH_CMD"]] + list(args),
            cwd=self.root,
            env=environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=120,
        )


def document_of(result, label):
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise Failure(
            "%s: expected a diagnostics document on stdout\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, result.stdout, result.stderr)
        )


def expect_exit(result, code, label):
    if result.returncode != code:
        raise Failure(
            "%s: expected exit %d, got %d\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, code, result.returncode, result.stdout, result.stderr)
        )


def check_status(document, check_id):
    for check in document.get("checks", []):
        if check.get("id") == check_id:
            return check
    return None


# ---------------------------------------------------------------------------
# the cases, run once per install
# ---------------------------------------------------------------------------


def case_closure(install, _session):
    """The skill directory carries everything it is supposed to carry."""
    missing = [
        name
        for name in CLOSURE
        if not os.path.isfile(os.path.join(install.skill_dir, *name.split("/")))
    ]
    if missing:
        raise Failure("the install is missing %s" % ", ".join(missing))
    if not os.access(install.etch, os.X_OK):
        raise Failure("%s is not executable" % install.etch)


def case_validate_reports_the_defects(_install, session):
    """A broken diagram fails validation with diagnostics that name the fixes."""
    source = session.write("pipeline.drawio", BROKEN)
    result = session.run(["validate", "--json", source])
    expect_exit(result, 1, "validate broken")
    document = document_of(result, "validate broken")
    if document.get("status") != "failed":
        raise Failure("validate broken: status is %r" % document.get("status"))
    codes = {diagnostic["code"] for diagnostic in document.get("diagnostics", [])}
    for expected in ("xml/duplicate-cell-id", "xml/invalid-geometry"):
        if expected not in codes:
            raise Failure(
                "validate broken: %s is not among %s" % (expected, sorted(codes))
            )


def case_bundled_xsd_resolves(_install, session):
    """The bundled mxfile.xsd is found from inside the install, in either layout.

    This is the case the layout change is for: before it, the path to the XSD
    was written as if the repo were always the root, so a standalone install
    silently lost the check.
    """
    source = session.write("clean.drawio", REPAIRED)
    result = session.run(["validate", "--json", source])
    expect_exit(result, 0, "validate repaired")
    document = document_of(result, "validate repaired")
    check = check_status(document, "xml/schema-xsd")
    if check is None:
        raise Failure("no xml/schema-xsd check in the document")
    reason = (check.get("waiver") or {}).get("reason", "")
    if "not found" in reason:
        raise Failure(
            "the bundled mxfile.xsd did not resolve in this layout (waiver: %r)" % reason
        )


def case_repair_and_deliver(install, session):
    """The SKILL.md loop, once through: validate, repair, re-validate, deliver."""
    source = session.write("pipeline.drawio", BROKEN)
    expect_exit(session.run(["validate", "--json", source]), 1, "validate")

    # One fix set, applied to a work copy; the master is not touched until the
    # CLI replaces it during delivery (contracts/delivery.md §2.1).
    work = session.write("pipeline.work.drawio", REPAIRED)
    before = sha256_file(source)
    document = document_of(session.run(["validate", "--json", work]), "re-validate")
    if document.get("status") != "passed":
        raise Failure("re-validate: status is %r" % document.get("status"))
    if sha256_file(source) != before:
        raise Failure("the repair loop wrote to the master")

    result = session.run(
        [
            "deliver",
            "--format",
            "svg",
            "--output-root",
            session.output_root,
            "--content",
            work,
            source,
        ]
    )
    expect_exit(result, 0, "deliver")
    document = document_of(result, "deliver")
    if document.get("status") != "passed":
        raise Failure("deliver: status is %r" % document.get("status"))

    pointer = os.path.join(session.output_root, "current")
    generation = os.path.realpath(pointer)
    if not os.path.isdir(generation):
        raise Failure("current does not resolve to a generation directory")

    with open(os.path.join(generation, "receipt.json"), encoding="utf-8") as handle:
        receipt = json.load(handle)

    # The receipt has to describe *this* install: its version file and its own
    # vendor.lock, not the repo's.
    with open(os.path.join(install.skill_dir, "VERSION"), encoding="utf-8") as handle:
        version = handle.read().strip()
    if receipt.get("toolVersion") != version:
        raise Failure(
            "receipt toolVersion is %r, the install says %r"
            % (receipt.get("toolVersion"), version)
        )
    lock = receipt.get("vendorLock")
    if not lock:
        raise Failure("the receipt records no vendor.lock")
    expected = sha256_file(os.path.join(install.skill_dir, "vendor.lock"))
    if lock.get("sha256") != expected:
        raise Failure("the receipt's vendor.lock hash is not this install's")

    expect_exit(
        session.run(["verify", "--output-root", session.output_root]), 0, "verify"
    )


def case_missing_dependency_is_exit_5(_install, session):
    """A DRAWIO_CMD that names nothing executable stops at exit 5, with JSON."""
    source = session.write("dependency.drawio", REPAIRED)
    environ = dict(os.environ)
    environ["ETCH_CMD"] = session.install.etch
    environ["DRAWIO_CMD"] = os.path.join(session.root, "no-such-drawio")
    result = subprocess.run(
        [
            session.install.etch,
            "export",
            "--format",
            "svg",
            "--output-root",
            session.output_root,
            source,
        ],
        cwd=session.root,
        env=environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=120,
    )
    expect_exit(result, 5, "missing dependency")
    document = document_of(result, "missing dependency")
    codes = {diagnostic["code"] for diagnostic in document.get("diagnostics", [])}
    if "dependency/drawio" not in codes:
        raise Failure("missing dependency: codes were %s" % sorted(codes))


CASES = (
    ("the install carries its closure", case_closure),
    ("validate names the defects", case_validate_reports_the_defects),
    ("the bundled XSD resolves", case_bundled_xsd_resolves),
    ("repair loop through to delivery", case_repair_and_deliver),
    ("a missing draw.io is exit 5", case_missing_dependency_is_exit_5),
)

LAYOUTS = (
    ("plugin", install_plugin),
    ("standalone", install_standalone),
)


def main():
    verbose = "-v" in sys.argv
    print("== Phase 3a acceptance: distribution layouts")
    base = tempfile.mkdtemp(prefix="etch-acceptance.")
    passed = failures = 0
    try:
        for name, installer in LAYOUTS:
            try:
                install = installer(base)
            except Failure as error:
                failures += 1
                print("  FAIL %s: could not install: %s" % (name, error))
                continue
            print("   %s install: %s" % (name, install.root))
            for label, function in CASES:
                session = Session(install, tempfile.mkdtemp(prefix="etch-work.", dir=base))
                try:
                    function(install, session)
                except Failure as error:
                    failures += 1
                    print("  FAIL %s / %s" % (name, label))
                    for line in str(error).splitlines():
                        print("       %s" % line)
                except Exception as error:  # noqa: BLE001 - report, do not mask
                    failures += 1
                    print("  ERROR %s / %s: %s: %s" % (name, label, type(error).__name__, error))
                else:
                    passed += 1
                    if verbose:
                        print("  ok   %s / %s" % (name, label))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("  %d passed, %d failed" % (passed, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
