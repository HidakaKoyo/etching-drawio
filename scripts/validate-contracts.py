#!/usr/bin/env python3
"""Validate the contract schemas against fake fixtures.

Runs with python3 >= 3.9 and the standard library only, per
contracts/environment.md. The JSON Schema keyword subset implemented here is
exactly the subset the contract schemas use; an unknown keyword is a hard
error so a schema cannot silently grow a constraint that is never checked.

Usage: python3 scripts/validate-contracts.py [-v]
Exit 0 when every fixture matches its expectation.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

ANNOTATIONS = {"$schema", "$id", "title", "description", "default", "examples", "$comment"}
APPLICATORS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "const", "pattern", "minLength", "minItems", "maxItems", "minimum",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else", "contains", "$ref",
}

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(Exception):
    pass


def resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise SchemaError("only local pointers are supported: %s" % ref)
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def validate(instance, schema, root, path="$"):
    """Return a list of human-readable error strings."""
    if isinstance(schema, bool):
        return [] if schema else ["%s: schema is false" % path]

    unknown = set(schema) - APPLICATORS - ANNOTATIONS - {"$defs"}
    if unknown:
        raise SchemaError("unsupported keyword(s) at %s: %s" % (path, sorted(unknown)))

    errors = []

    if "$ref" in schema:
        errors += validate(instance, resolve_ref(root, schema["$ref"]), root, path)

    if "type" in schema:
        wanted = schema["type"]
        wanted = wanted if isinstance(wanted, list) else [wanted]
        if not any(TYPES[t](instance) for t in wanted):
            errors.append("%s: expected type %s" % (path, "|".join(wanted)))
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected const %r" % (path, schema["const"]))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r not in enum %r" % (path, instance, schema["enum"]))

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append("%s: %r does not match /%s/" % (path, instance, schema["pattern"]))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than minLength" % path)

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: below minimum" % path)

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required property %r" % (path, key))
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors += validate(value, props[key], root, "%s.%s" % (path, key))
            elif schema.get("additionalProperties") is False:
                errors.append("%s: unexpected property %r" % (path, key))

    if isinstance(instance, list):
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], root, "%s[%d]" % (path, i))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than minItems" % path)
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: more than maxItems" % path)
        if "contains" in schema:
            if not any(not validate(item, schema["contains"], root, path) for item in instance):
                errors.append("%s: no item matches 'contains'" % path)

    for sub in schema.get("allOf", []):
        errors += validate(instance, sub, root, path)
    if "anyOf" in schema:
        if all(validate(instance, sub, root, path) for sub in schema["anyOf"]):
            errors.append("%s: matches no branch of anyOf" % path)
    if "oneOf" in schema:
        hits = sum(1 for sub in schema["oneOf"] if not validate(instance, sub, root, path))
        if hits != 1:
            errors.append("%s: matched %d branches of oneOf" % (path, hits))
    if "not" in schema and not validate(instance, schema["not"], root, path):
        errors.append("%s: matches a schema it must not match" % path)
    if "if" in schema:
        if not validate(instance, schema["if"], root, path):
            if "then" in schema:
                errors += validate(instance, schema["then"], root, path)
        elif "else" in schema:
            errors += validate(instance, schema["else"], root, path)

    return errors


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

H = "a" * 64
BASE = {"schemaVersion": "1.0.0", "toolVersion": "0.1.0"}


def doc(**over):
    d = dict(BASE, status="passed", checks=[], diagnostics=[], artifacts=[])
    d.update(over)
    return d


def check(cid="xml/well-formed", required=True, status="passed", **over):
    c = {"id": cid, "required": required, "status": status}
    c.update(over)
    return c


WAIVER = {"reason": "no draw.io on this runner", "authorizedBy": "koyo"}

DIAG = {
    "code": "xml/duplicate-cell-id",
    "severity": "error",
    "message": "cell id 'n1' appears twice",
    "subject": {"file": "diagram.drawio", "xpath": "/mxfile/diagram[1]", "cellId": "n1", "line": 12},
    "evidence": {"expected": 1, "actual": 2, "params": {"scope": "diagram"}},
    "supportedFixes": [
        {
            "fixId": "xml/renumber-cell-ids",
            "target": "n1",
            "precondition": "no edge references the duplicate by index",
            "description": "assign a fresh id to the second occurrence",
        }
    ],
}

DIAGNOSTICS_CASES = [
    ("passed: minimal green run", True, doc(checks=[check()])),
    (
        "passed: optional check failed with waiver does not change aggregate",
        True,
        doc(
            checks=[check(), check("export/pdf", required=False, status="skipped", waiver=WAIVER)],
            diagnostics=[dict(DIAG, code="export/skipped", severity="warning")],
            artifacts=[{"path": "generations/g1/diagram.svg", "sha256": H, "kind": "svg"}],
        ),
    ),
    ("skipped: nothing processed", True, doc(status="skipped")),
    (
        "failed: required check failed",
        True,
        doc(status="failed", checks=[check(status="failed")], diagnostics=[DIAG]),
    ),
    (
        "failed: required check skipped counts as unmet",
        True,
        doc(status="failed", checks=[check(cid="dependency/drawio", status="skipped")]),
    ),
    ("invalid: unknown top-level key", False, doc(checks=[check()], exitCode=0)),
    ("invalid: missing artifacts array", False, {k: v for k, v in doc(checks=[check()]).items() if k != "artifacts"}),
    ("invalid: bad status value", False, doc(status="warning", checks=[check()])),
    ("invalid: passed with an unmet required check", False, doc(checks=[check(status="failed")])),
    ("invalid: passed with zero checks", False, doc()),
    ("invalid: failed without any unmet required check", False, doc(status="failed", checks=[check()])),
    ("invalid: skipped but carries checks", False, doc(status="skipped", checks=[check()])),
    (
        "invalid: skipped but carries artifacts",
        False,
        doc(status="skipped", artifacts=[{"path": "a.svg", "sha256": H, "kind": "svg"}]),
    ),
    ("invalid: required check carries a waiver", False, doc(checks=[check(waiver=WAIVER)])),
    (
        "invalid: waiver missing authorizedBy",
        False,
        doc(checks=[check(), check("export/pdf", required=False, status="failed", waiver={"reason": "x"})]),
    ),
    ("invalid: check id without a namespace", False, doc(checks=[check(cid="wellformed")])),
    (
        "invalid: reserved composition/* namespace used in v1",
        False,
        doc(status="failed", checks=[check(status="failed")], diagnostics=[dict(DIAG, code="composition/label-overlap")]),
    ),
    (
        "invalid: diagnostic subject without file",
        False,
        doc(status="failed", checks=[check(status="failed")], diagnostics=[dict(DIAG, subject={"cellId": "n1"})]),
    ),
    (
        "invalid: artifact sha256 is not 64 hex chars",
        False,
        doc(checks=[check()], artifacts=[{"path": "a.svg", "sha256": "abc", "kind": "svg"}]),
    ),
    (
        "invalid: artifact kind outside the enum",
        False,
        doc(checks=[check()], artifacts=[{"path": "a.eps", "sha256": H, "kind": "eps"}]),
    ),
    ("invalid: schemaVersion is not semver", False, dict(doc(checks=[check()]), schemaVersion="1.0")),
    (
        "invalid: unsupported fix field",
        False,
        doc(
            status="failed",
            checks=[check(status="failed")],
            diagnostics=[dict(DIAG, supportedFixes=[dict(DIAG["supportedFixes"][0], auto=True)])],
        ),
    ),
]

PROFILE_CASES = [
    ("valid: version only", True, {"version": 1}),
    ("valid: proposal mode on", True, {"version": 1, "proposal_mode": True}),
    ("invalid: missing version", False, {"proposal_mode": True}),
    ("invalid: wrong version", False, {"version": 2}),
    ("invalid: proposal_mode is a string", False, {"version": 1, "proposal_mode": "true"}),
    ("invalid: unknown key", False, {"version": 1, "output_dir": "build"}),
]


def run(name, schema_path, cases, verbose):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    failures = 0
    print("== %s (%s)" % (name, schema_path.relative_to(ROOT)))
    for label, should_pass, instance in cases:
        errors = validate(instance, schema, schema)
        ok = (not errors) == should_pass
        if not ok:
            failures += 1
            print("  FAIL %s" % label)
            print("       expected %s, got %s" % ("pass" if should_pass else "reject",
                                                  "pass" if not errors else "reject"))
            for e in errors:
                print("       - %s" % e)
        elif verbose:
            print("  ok   %s" % label)
    print("  %d cases, %d failures" % (len(cases), failures))
    return failures


def main():
    verbose = "-v" in sys.argv
    failures = 0
    failures += run("diagnostics", CONTRACTS / "diagnostics.schema.json", DIAGNOSTICS_CASES, verbose)
    failures += run("profile", CONTRACTS / "profile.schema.json", PROFILE_CASES, verbose)
    if failures:
        print("\nFAILED: %d case(s)" % failures)
        return 1
    print("\nOK: all contract fixtures behave as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
