#!/usr/bin/env python3
"""Migration expectations: behaviour the port deliberately CHANGES (Phase 1a).

READ THIS FIRST
---------------
**These cases are never executed against the legacy wrapper.** They encode the
NEW expected values, which the legacy wrapper by definition does not satisfy.
Running this file today reports every case as skipped, and that is the correct
result for Phase 1a.

Phase 1b turns them on by setting ETCH_CLI to the new binary:

    ETCH_CLI=./bin/etch python3 tests/characterization/test_migration.py

and by filling in `argv_for()` below, which is the single place that knows the
new CLI's surface. That surface is not fixed yet, so `argv_for()` currently
raises. This is deliberate: no case can silently pass on a guessed interface.

Invariants (behaviour that must NOT change) live in test_invariants.py.
The old→new table with rationale is docs/phase1a-behavior-inventory.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as h  # noqa: E402


ETCH_CLI = os.environ.get("ETCH_CLI")

VALID_EXIT_CODES = {0, 1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# fixtures that only the migration suite needs
# ---------------------------------------------------------------------------

def _compressed_input():
    """A genuinely compressed .drawio (raw deflate + base64, as draw.io writes it).

    The legacy wrapper decodes this, inspects it and only warns. The contract
    rejects compressed input outright under the uncompressed-only policy, so
    the payload has to be real or MIG-03 would be rejected for the wrong reason.
    """
    import base64
    import urllib.parse
    import zlib

    model = (
        '<mxGraphModel dx="800" dy="600" grid="0" page="1"><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="n1" value="A" style="rounded=0;" vertex="1" parent="1">'
        '<mxGeometry x="40" y="40" width="120" height="60" as="geometry"/>'
        "</mxCell></root></mxGraphModel>"
    )
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = compressor.compress(urllib.parse.quote(model).encode("utf-8")) + compressor.flush()
    payload = base64.b64encode(raw).decode("ascii")
    return (
        '<mxfile host="characterization">\n'
        '  <diagram id="d1" name="Page-1">%s</diagram>\n'
        "</mxfile>\n" % payload
    )


COMPRESSED_INPUT = _compressed_input()

# a DTD-bearing document. The legacy wrapper hands this to xmllint and
# ElementTree without any XXE policy; the contract rejects it.
DOCTYPE_INPUT = (
    '<?xml version="1.0"?>\n'
    "<!DOCTYPE mxfile [<!ENTITY probe SYSTEM \"file:///etc/passwd\">]>\n"
    + h.VALID
)

# valid XML and structurally sound, but violates mxfile.xsd (unknown element).
XSD_VIOLATION = h.VALID.replace("</root>", '  <bogusElement id="x"/>\n      </root>')


# ---------------------------------------------------------------------------
# the migration table
# ---------------------------------------------------------------------------
# mode:
#   "verify"  – validation only, no export
#   "export"  – full run including export and delivery
#
# Each entry states what the legacy wrapper does today and what the new CLI is
# contractually required to do instead.

MIGRATIONS = [
    {
        "id": "MIG-01",
        "area": "dependency",
        "legacy": "missing drawio / python3 / xmllint / shasum -> exit 4",
        "new": "exit 5 with a failed required check under dependency/*",
        "contract": "contracts/exit-codes.md §2 exit 5; contracts/environment.md §3, §4.1",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 5,
        "expected_json_status": "failed",
    },
    {
        "id": "MIG-02",
        "area": "dependency",
        "legacy": "DRAWIO_CMD is not honoured; only PATH lookup of `drawio`",
        "new": "DRAWIO_CMD wins; set but not executable -> exit 5, no fallback to PATH",
        "contract": "contracts/environment.md §4.1",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 5,
        "expected_json_status": "failed",
        "env": {"DRAWIO_CMD": "/nonexistent/drawio"},
    },
    {
        "id": "MIG-03",
        "area": "input safety",
        "legacy": "compressed diagram body is decoded and inspected, only a stderr warning",
        "new": "exit 1 with an explicit input/* diagnostic; no implicit conversion",
        "contract": "docs/PLAN.md §6.4; contracts/exit-codes.md §2 exit 1 (input/*)",
        "mode": "verify",
        "fixture": COMPRESSED_INPUT,
        "expected_exit": 1,
        "expected_json_status": "failed",
    },
    {
        "id": "MIG-04",
        "area": "input safety",
        "legacy": "no DTD / external entity policy; no size, node or depth limits",
        "new": "exit 1 with input/* for DTD or external entity",
        "contract": "docs/PLAN.md §6.4; contracts/exit-codes.md §2 exit 1 (input/*)",
        "mode": "verify",
        "fixture": DOCTYPE_INPUT,
        "expected_exit": 1,
        "expected_json_status": "failed",
    },
    {
        "id": "MIG-05",
        "area": "validation severity",
        "legacy": "mxfile.xsd mismatch is a stderr warning and the run continues",
        "new": "exit 1 with an xml/* diagnostic",
        "contract": "contracts/exit-codes.md §2 exit 1 (xml/*)",
        "mode": "verify",
        "fixture": XSD_VIOLATION,
        "expected_exit": 1,
        "expected_json_status": "failed",
    },
    {
        "id": "MIG-06",
        "area": "reporting",
        "legacy": "stdout is the published output path; findings are Japanese prose on stderr",
        "new": "stdout is the diagnostics JSON and nothing else; logs on stderr",
        "contract": "docs/PLAN.md §6.1; contracts/exit-codes.md §3",
        "mode": "verify",
        "fixture": h.DUPLICATE_ID,
        "expected_exit": 1,
        "expected_json_status": "failed",
    },
    {
        "id": "MIG-07",
        "area": "reporting",
        "legacy": "usage errors print prose on stderr, nothing on stdout",
        "new": "unchanged in shape, but now contractually specified: exit 4 emits NO JSON",
        "contract": "contracts/exit-codes.md §1 (exit 4 の非対称)",
        "mode": "verify",
        "fixture": h.VALID,
        "expected_exit": 4,
        "expected_json_status": None,
        "argv_override": ["--bogus-option"],
    },
    {
        "id": "MIG-08",
        "area": "delivery",
        "legacy": "-o <path> publishes the artifact straight to that path via mv",
        "new": "generations/<id>.tmp -> generations/<id> rename, then atomic `current` swap; receipt.json per generation",
        "contract": "contracts/delivery.md §1, §2 (S3-S6)",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
    },
    {
        "id": "MIG-09",
        "area": "delivery",
        "legacy": "no receipt of any kind",
        "new": "receipt.json records artifact hashes, tool and draw.io versions, Hfinal, vendor.lock sha, checks",
        "contract": "contracts/delivery.md §6",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
    },
    {
        "id": "MIG-10",
        "area": "delivery",
        "legacy": "no proposal mode; the wrapper only ever writes the output artifact",
        "new": "proposal_mode leaves the source untouched, writes <name>.agent-proposal.drawio, does not move `current`",
        "contract": "contracts/delivery.md §3; contracts/profile.md",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
    },
    {
        "id": "MIG-11",
        "area": "output verification",
        "legacy": "PNG checked with `file` magic plus sips pixel dimensions",
        "new": "sips gone; full chunk walk with CRC checks and an IDAT zlib inflate cross-checked against IHDR",
        "contract": "docs/PLAN.md §7.2; contracts/environment.md §5",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
    },
    {
        "id": "MIG-12",
        "area": "optional tooling",
        "legacy": "xmllint and file are hard requirements; absence is exit 4",
        "new": "both are optional; absence downgrades the check to skipped with a warning diagnostic and does not change the exit code",
        "contract": "contracts/environment.md §5",
        "mode": "verify",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
    },
]


# Deltas that the contracts do not yet pin down. They are recorded here rather
# than guessed at, and must be resolved before Phase 1b can close.
OPEN_QUESTIONS = [
    {
        "id": "OPEN-01",
        "topic": "output lock contention",
        "legacy": "a second process on the same output exits 2 (別プロセスが同じ出力へ export 中です)",
        "gap": "exit-codes.md has no entry for lock contention. Under the generation layout the "
               "per-output lock may disappear entirely, or contention may become exit 3 or exit 4.",
    },
    {
        "id": "OPEN-02",
        "topic": "signal termination",
        "legacy": "HUP/INT/TERM terminate the export process group and exit 130",
        "gap": "130 is not in the exit code table. Either add it as a documented non-contract code "
               "or define what a signalled run reports.",
    },
    {
        "id": "OPEN-03",
        "topic": "internal failure of the semantic linter",
        "legacy": "an unexpected linter exit status becomes exit 4 (usage error)",
        "gap": "an internal crash is not a usage error. The contract has no code for "
               "'the tool itself broke'.",
    },
    {
        "id": "OPEN-04",
        "topic": "external resource references",
        "legacy": "http/file URLs in style or image attributes warn on stderr; --allow-external silences it",
        "gap": "no diagnostic namespace is reserved for this. Decide whether it becomes a "
               "warning diagnostic, an optional check, or an error under a policy flag.",
    },
    {
        "id": "OPEN-05",
        "topic": "the uncompressed-only policy switch",
        "legacy": "n/a (always a warning)",
        "gap": "MIG-03 assumes the policy is on. profile.schema.json currently allows only "
               "`version` and `proposal_mode`, so there is nowhere to express the policy.",
    },
]


# ---------------------------------------------------------------------------
# execution (Phase 1b)
# ---------------------------------------------------------------------------

def argv_for(entry, input_path, output_root):
    """Build the new CLI's argv for one migration case.

    THE SINGLE ADAPTATION POINT. Phase 1b replaces the raise below once the
    subcommand surface is decided (docs/PLAN.md §7 names `etch verify` and
    `etch gc`, but the export/delivery invocation is not specified yet).
    """
    raise NotImplementedError(
        "the new CLI's argv is not defined yet; fill in argv_for() in Phase 1b"
    )


def make_case(entry):
    def case(workspace):
        source = workspace.write("input.drawio", entry["fixture"])
        output_root = workspace.path("build")
        os.mkdir(output_root)
        argv = entry.get("argv_override") or argv_for(entry, source, output_root)
        result = workspace.run(argv, use_stub=False, env=entry.get("env"))
        h.assert_exit(result, entry["expected_exit"], entry["id"])
        expected_status = entry["expected_json_status"]
        if expected_status is None:
            if result.stdout.strip():
                raise AssertionError("%s: expected no stdout JSON, got %r" % (entry["id"], result.stdout))
        else:
            import json

            document = json.loads(result.stdout)
            if document.get("status") != expected_status:
                raise AssertionError(
                    "%s: expected status %r, got %r" % (entry["id"], expected_status, document.get("status"))
                )

    return case


def check_table_consistency():
    """Guard against a malformed table even when nothing is executed."""
    problems = []
    seen = set()
    for entry in MIGRATIONS:
        for field in ("id", "area", "legacy", "new", "contract", "mode", "expected_exit"):
            if field not in entry:
                problems.append("%s: missing field %r" % (entry.get("id", "?"), field))
        if entry["id"] in seen:
            problems.append("%s: duplicate id" % entry["id"])
        seen.add(entry["id"])
        if entry.get("expected_exit") not in VALID_EXIT_CODES:
            problems.append("%s: exit %r is not in the contract" % (entry["id"], entry.get("expected_exit")))
        if entry.get("mode") not in ("verify", "export"):
            problems.append("%s: unknown mode %r" % (entry["id"], entry.get("mode")))
    return problems


def main():
    verbose = h.verbose_flag()
    problems = check_table_consistency()
    if problems:
        print("== migration table is malformed")
        for problem in problems:
            print("  - %s" % problem)
        return 1

    if not ETCH_CLI:
        print("== characterization: migration (%d deliberate changes)" % len(MIGRATIONS))
        print("   ETCH_CLI is not set, so every case is skipped.")
        print("   This is the expected Phase 1a result: these expectations describe the")
        print("   NEW CLI and are never run against the legacy wrapper.")
        for entry in MIGRATIONS:
            print("  skip %s [%s] %s" % (entry["id"], entry["area"], entry["new"]))
            if verbose:
                print("       was: %s" % entry["legacy"])
                print("       ref: %s" % entry["contract"])
        print("  0 passed, 0 failed, %d skipped" % len(MIGRATIONS))
        print("\n== unresolved before Phase 1b can close (%d)" % len(OPEN_QUESTIONS))
        for question in OPEN_QUESTIONS:
            print("  %s %s" % (question["id"], question["topic"]))
            print("       now: %s" % question["legacy"])
            print("       gap: %s" % question["gap"])
        return 0

    original = h.LEGACY_WRAPPER
    h.LEGACY_WRAPPER = ETCH_CLI
    try:
        cases = [(entry["id"] + " " + entry["new"][:44], None, make_case(entry)) for entry in MIGRATIONS]
        failures, _, _ = h.run_suite("characterization: migration", cases, verbose)
    finally:
        h.LEGACY_WRAPPER = original
    if failures:
        print("\nFAILED: %d case(s)" % failures)
        return 1
    print("\nOK: the new CLI matches every migration expectation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
