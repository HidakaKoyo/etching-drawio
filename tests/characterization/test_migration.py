#!/usr/bin/env python3
"""Migration expectations: behaviour the port deliberately CHANGES (Phase 1a).

READ THIS FIRST
---------------
**These cases are never executed against the legacy wrapper.** They encode the
NEW expected values, which the legacy wrapper by definition does not satisfy.
Running this file today reports every case as skipped, and that is the correct
result for Phase 1a.

Phase 1b turned them on. Run them against the new CLI with:

    ETCH_CLI=./bin/etch python3 tests/characterization/test_migration.py

`argv_for()` below is the single place that knows the new CLI's surface.

Invariants (behaviour that must NOT change) live in test_invariants.py.
The old→new table with rationale is docs/phase1a-behavior-inventory.md.
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as h  # noqa: E402


ETCH_CLI = os.environ.get("ETCH_CLI")

VALID_EXIT_CODES = {0, 1, 2, 3, 4, 5, 6}


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
        # PATH holds bash and nothing else, so python3 is genuinely missing.
        # draw.io cannot be hidden this way (the resolution order also looks in
        # the macOS bundle and the Linux defaults), and its absence is covered
        # by MIG-02; python3 is the dependency this case can make real.
        "env": {"PATH": "{bashonly}"},
        "post": "dependency_failed",
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
        "post": "dependency_failed",
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
        "stub": "svg",
        "post": "generation_layout",
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
        "stub": "svg",
        "post": "receipt_contents",
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
        "stub": "svg",
        "profile": {"version": 1, "proposal_mode": True},
        "post": "proposal_layout",
    },
    {
        "id": "MIG-11",
        "area": "output verification",
        "legacy": "PNG checked with `file` magic plus sips pixel dimensions",
        "new": "sips gone; full chunk walk with CRC checks and an IDAT zlib inflate cross-checked against IHDR",
        "contract": "docs/PLAN.md §7.2; contracts/environment.md §5",
        "mode": "export",
        "format": "png",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
        "stub": "png",
        "post": "png_verified",
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
        # xmllint is genuinely off PATH here, so the optional check really is
        # exercised rather than merely allowed to be.
        "env": {"PATH": "{emptybin}"},
        "post": "optional_check_skipped",
    },
    {
        "id": "MIG-13",
        "area": "delivery",
        "legacy": "a per-output <output>.lock directory; a second run on the same output exits 2",
        "new": "no lock at all; a stale <output>.lock is not consulted and does not block delivery",
        "contract": "contracts/delivery.md §2.1; docs/PLAN.md §6.2",
        "mode": "export",
        "fixture": h.VALID,
        "expected_exit": 0,
        "expected_json_status": "passed",
        "stub": "svg",
        "post": "lock_ignored",
    },
]


# The five deltas the contracts did not pin down in Phase 1a. All were decided
# before this suite was switched on; the decisions are recorded here because
# they are what several cases above now rest on.
RESOLVED_QUESTIONS = [
    {
        "id": "OPEN-01",
        "topic": "output lock contention",
        "legacy": "a second process on the same output exits 2 (別プロセスが同じ出力へ export 中です)",
        "decision": "the lock is gone. Generations do not share an output path, so the only "
                    "shared mutable things left are the source and the current pointer, and "
                    "both are guarded by the hash handoff: a run that lost the race stops with "
                    "exit 3. MIG-13 asserts a stale lock directory is ignored.",
        "contract": "contracts/delivery.md §2.1",
    },
    {
        "id": "OPEN-02",
        "topic": "signal termination",
        "legacy": "HUP/INT/TERM terminate the export process group and exit 130",
        "decision": "130 is documented as a reserved code outside the diagnostics contract. A "
                    "signalled run emits no JSON, because a half-run checks[] cannot be told "
                    "apart from a failed one.",
        "contract": "contracts/exit-codes.md §1, §2",
    },
    {
        "id": "OPEN-03",
        "topic": "internal failure of the semantic linter",
        "legacy": "an unexpected linter exit status becomes exit 4 (usage error)",
        "decision": "exit 6 = internal error, for the tool itself breaking rather than the "
                    "input being wrong. The diagnostics document is best-effort and uses the "
                    "internal/* namespace.",
        "contract": "contracts/exit-codes.md §2; contracts/diagnostics.schema.json",
    },
    {
        "id": "OPEN-04",
        "topic": "external resource references",
        "legacy": "http/file URLs in style or image attributes warn on stderr; --allow-external silences it",
        "decision": "the security/* namespace. security/external-ref is a warning diagnostic "
                    "and security/no-external-ref an optional check, so the exit code does not "
                    "change; --allow-external turns the check into a waived skip.",
        "contract": "contracts/exit-codes.md §2 exit 0; contracts/diagnostics.schema.json",
    },
    {
        "id": "OPEN-05",
        "topic": "the uncompressed-only policy switch",
        "legacy": "n/a (always a warning)",
        "decision": "the policy is always on in v1 and gets no profile key, so a receipt never "
                    "has to be read to find out which policy validated a document. MIG-03 "
                    "therefore holds unconditionally.",
        "contract": "contracts/profile.md §3, §4",
    },
]


# ---------------------------------------------------------------------------
# execution (Phase 1b)
# ---------------------------------------------------------------------------

def argv_for(entry, input_path, output_root):
    """Build the new CLI's argv for one migration case.

    THE SINGLE ADAPTATION POINT: the only place that knows the etch surface.
    "verify" mode maps to `etch validate` (no export, no output location);
    "export" mode maps to `etch deliver`, the subcommand that runs the whole
    S0-S7 sequence of contracts/delivery.md including the pointer commit.
    """
    if entry["mode"] == "verify":
        return ["validate", input_path]
    return [
        "deliver",
        "--format",
        entry.get("format", "svg"),
        "--output-root",
        output_root,
        input_path,
    ]


def env_for(entry, workspace):
    """Expand the placeholders a case may use in its environment overrides."""
    env = entry.get("env")
    if not env:
        return None
    return {
        key: value.format(
            root=workspace.root, emptybin=workspace.emptybin, bashonly=workspace.bashonly
        )
        for key, value in env.items()
    }


# ---------------------------------------------------------------------------
# post-conditions
# ---------------------------------------------------------------------------
# The exit code and the aggregate status say a run behaved; these say it
# produced the thing the migration is actually about.


def read_current(output_root, label):
    pointer = os.path.join(output_root, "current")
    if not os.path.islink(pointer):
        raise AssertionError("%s: no current pointer under %s" % (label, output_root))
    generation = os.path.realpath(pointer)
    if not os.path.isdir(generation):
        raise AssertionError("%s: current does not resolve to a directory" % label)
    if os.path.dirname(generation) != os.path.realpath(os.path.join(output_root, "generations")):
        raise AssertionError("%s: current points outside generations/" % label)
    return generation


def post_generation_layout(entry, workspace, source, output_root, result):
    generation = read_current(output_root, entry["id"])
    names = sorted(os.listdir(generation))
    if "receipt.json" not in names or "input.svg" not in names:
        raise AssertionError("%s: generation holds %s" % (entry["id"], names))
    leftovers = [n for n in os.listdir(os.path.join(output_root, "generations")) if n.endswith(".tmp")]
    if leftovers:
        raise AssertionError("%s: staging directories survived: %s" % (entry["id"], leftovers))


def post_receipt_contents(entry, workspace, source, output_root, result):
    generation = read_current(output_root, entry["id"])
    with open(os.path.join(generation, "receipt.json"), encoding="utf-8") as handle:
        receipt = json.load(handle)
    for field in ("toolVersion", "drawio", "vendorLock", "artifacts", "checks", "source"):
        if not receipt.get(field):
            raise AssertionError("%s: receipt has no %s" % (entry["id"], field))
    if receipt["source"]["sha256"] != sha256_of(source):
        raise AssertionError("%s: receipt does not record Hfinal of the source" % entry["id"])
    for artifact in receipt["artifacts"]:
        actual = sha256_of(os.path.join(generation, artifact["path"]))
        if actual != artifact["sha256"]:
            raise AssertionError("%s: receipt hash does not match %s" % (entry["id"], artifact["path"]))
    if any(a["path"] == "receipt.json" for a in receipt["artifacts"]):
        raise AssertionError("%s: the receipt hashes itself" % entry["id"])


def post_proposal_layout(entry, workspace, source, output_root, result):
    proposal = os.path.splitext(source)[0] + ".agent-proposal.drawio"
    if not os.path.isfile(proposal):
        raise AssertionError("%s: no proposal file at %s" % (entry["id"], proposal))
    with open(source, encoding="utf-8") as handle:
        if handle.read() != entry["fixture"]:
            raise AssertionError("%s: proposal mode modified the source" % entry["id"])
    if os.path.islink(os.path.join(output_root, "current")):
        raise AssertionError("%s: proposal mode moved the current pointer" % entry["id"])
    generations = os.listdir(os.path.join(output_root, "generations"))
    if not generations:
        raise AssertionError("%s: proposal mode produced no generation" % entry["id"])


def post_png_verified(entry, workspace, source, output_root, result):
    generation = read_current(output_root, entry["id"])
    png = os.path.join(generation, "input.png")
    with open(png, "rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise AssertionError("%s: the delivered artifact is not a PNG" % entry["id"])
    document = json.loads(result.stdout)
    if not any(c["id"] == "export/png-valid" and c["status"] == "passed" for c in document["checks"]):
        raise AssertionError("%s: no passing export/png-valid check" % entry["id"])


def post_optional_check_skipped(entry, workspace, source, output_root, result):
    document = json.loads(result.stdout)
    optional = [c for c in document["checks"] if not c["required"] and c["status"] == "skipped"]
    if not optional:
        raise AssertionError(
            "%s: expected an optional check to be skipped without xmllint, got %s"
            % (entry["id"], document["checks"])
        )


def post_lock_ignored(entry, workspace, source, output_root, result):
    read_current(output_root, entry["id"])
    if not os.path.isdir(os.path.join(output_root, "stale.lock")):
        raise AssertionError("%s: the pre-existing lock directory was removed" % entry["id"])


def post_dependency_failed(entry, workspace, source, output_root, result):
    document = json.loads(result.stdout)
    failed = [
        c
        for c in document["checks"]
        if c["required"] and c["status"] == "failed" and c["id"].startswith("dependency/")
    ]
    if not failed:
        raise AssertionError(
            "%s: expected a failed required dependency/* check, got %s"
            % (entry["id"], document["checks"])
        )


POST = {
    "dependency_failed": post_dependency_failed,
    "generation_layout": post_generation_layout,
    "receipt_contents": post_receipt_contents,
    "proposal_layout": post_proposal_layout,
    "png_verified": post_png_verified,
    "optional_check_skipped": post_optional_check_skipped,
    "lock_ignored": post_lock_ignored,
}


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def make_case(entry):
    def case(workspace):
        source = workspace.write("input.drawio", entry["fixture"])
        output_root = workspace.path("build")
        os.mkdir(output_root)
        if entry["id"] == "MIG-13":
            # what the legacy wrapper would have treated as a held lock
            os.mkdir(os.path.join(output_root, "stale.lock"))
        if entry.get("profile"):
            os.mkdir(workspace.path(".etching"))
            with open(workspace.path(".etching/profile.json"), "w", encoding="utf-8") as handle:
                json.dump(entry["profile"], handle)
        if entry.get("stub"):
            workspace.set_stub(h.PNG_STUB if entry["stub"] == "png" else h.DEFAULT_STUB)

        argv = entry.get("argv_override") or argv_for(entry, source, output_root)
        result = workspace.run(argv, use_stub=bool(entry.get("stub")), env=env_for(entry, workspace))
        h.assert_exit(result, entry["expected_exit"], entry["id"])

        expected_status = entry["expected_json_status"]
        if expected_status is None:
            if result.stdout.strip():
                raise AssertionError("%s: expected no stdout JSON, got %r" % (entry["id"], result.stdout))
        else:
            document = json.loads(result.stdout)
            if document.get("status") != expected_status:
                raise AssertionError(
                    "%s: expected status %r, got %r" % (entry["id"], expected_status, document.get("status"))
                )
        if entry.get("post"):
            POST[entry["post"]](entry, workspace, source, output_root, result)

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


def print_decisions(verbose):
    print("\n== decisions the cases above rest on (%d)" % len(RESOLVED_QUESTIONS))
    for question in RESOLVED_QUESTIONS:
        print("  %s %s" % (question["id"], question["topic"]))
        print("       decided: %s" % question["decision"])
        if verbose:
            print("       was:     %s" % question["legacy"])
            print("       ref:     %s" % question["contract"])


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
        print_decisions(verbose)
        return 0

    original = h.LEGACY_WRAPPER
    h.LEGACY_WRAPPER = ETCH_CLI
    h.NEW_CLI = True
    try:
        cases = [(entry["id"] + " " + entry["new"][:44], None, make_case(entry)) for entry in MIGRATIONS]
        failures, _, _ = h.run_suite("characterization: migration", cases, verbose)
    finally:
        h.LEGACY_WRAPPER = original
    if failures:
        print("\nFAILED: %d case(s)" % failures)
        return 1
    print_decisions(verbose)
    print("\nOK: the new CLI matches every migration expectation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
