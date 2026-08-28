#!/usr/bin/env python3
"""Characterization tests for behaviour the port MUST preserve (Phase 1a).

Subject: the legacy bash wrapper `bin/drawio-verify-export` (read-only; this
suite never writes to the vault). Override with LEGACY_WRAPPER=<path>.

Everything asserted here is an *invariant*: it is behaviour that the etch CLI
has to keep after the port. Deliberate changes live in test_migration.py and
are not asserted against the legacy wrapper.

The suite is split in two:

  INV-*   run without a real draw.io CLI. A bash stub is put in front of PATH
          so the wrapper's `command -v drawio` probe succeeds. These cases stop
          before export, or use the stub to drive export deterministically.
  SMOKE-* need the genuine draw.io Desktop CLI on PATH and are skipped when it
          is absent.

Usage: python3 tests/characterization/test_invariants.py [-v]
Exit 0 when every non-skipped case passes.

Inventory and rationale: docs/phase1a-behavior-inventory.md
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as h  # noqa: E402


# The stub used by the conflict case: it mutates the ORIGINAL input while
# pretending to export, which is what a concurrent editor would do.
MUTATING_STUB = """
printf '%s\\n' "$*" >> "$STUB_LOG"
printf '\\n<!-- mutated during export -->\\n' >> "$MUTATE_TARGET"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then out="$arg"; fi
  prev="$arg"
done
if [ -n "$out" ]; then
  printf '<svg xmlns="http://www.w3.org/2000/svg"/>\\n' > "$out"
fi
exit 0
"""


# ---------------------------------------------------------------------------
# 1. input validation (exit 1)
# ---------------------------------------------------------------------------

def test_malformed_xml_rejected(w):
    w.write("bad.drawio", h.MALFORMED_XML)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("bad.drawio")])
    h.assert_exit(result, 1, "malformed XML")
    h.assert_stderr_contains(result, "XML が不正です", "malformed XML")


def test_raw_ampersand_hint(w):
    w.write("amp.drawio", h.RAW_AMPERSAND)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("amp.drawio")])
    h.assert_exit(result, 1, "raw ampersand")
    h.assert_stderr_contains(result, "生の &", "raw ampersand")


def test_dangling_parent_reference(w):
    w.write("dangling.drawio", h.DANGLING_PARENT)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("dangling.drawio")])
    h.assert_exit(result, 1, "dangling parent")
    h.assert_stderr_contains(result, "参照先がありません", "dangling parent")


def test_dangling_edge_target(w):
    w.write("edge.drawio", h.DANGLING_EDGE_TARGET)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("edge.drawio")])
    h.assert_exit(result, 1, "dangling edge target")
    h.assert_stderr_contains(result, "target 参照先がありません", "dangling edge target")


def test_duplicate_cell_id(w):
    w.write("dup.drawio", h.DUPLICATE_ID)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("dup.drawio")])
    h.assert_exit(result, 1, "duplicate id")
    h.assert_stderr_contains(result, "重複しています", "duplicate id")


def test_root_element_must_be_mxfile(w):
    w.write("svgroot.drawio", h.NOT_MXFILE)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("svgroot.drawio")])
    h.assert_exit(result, 1, "non-mxfile root")
    h.assert_stderr_contains(result, "root 要素", "non-mxfile root")


def test_page_index_out_of_range(w):
    w.write("ok.drawio", h.VALID)
    result = w.run(["-f", "svg", "-p", "5", "--check-only", "-o", w.path("out.svg"), w.path("ok.drawio")])
    h.assert_exit(result, 1, "page out of range")
    h.assert_stderr_contains(result, "ページ番号が範囲外", "page out of range")


# ---------------------------------------------------------------------------
# 2. warnings that do not fail the run
# ---------------------------------------------------------------------------

def test_compressed_false_missing_warns_but_passes(w):
    w.write("nocompress.drawio", h.UNCOMPRESSED_ATTR_MISSING)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("nocompress.drawio")])
    h.assert_exit(result, 0, "missing compressed attribute")
    h.assert_stderr_contains(result, 'compressed="false" ではありません', "missing compressed attribute")


def test_compressed_false_present_is_silent(w):
    w.write("ok.drawio", h.VALID)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("ok.drawio")])
    h.assert_exit(result, 0, "valid input")
    if "compressed" in result.stderr:
        raise AssertionError("valid input: unexpected compressed warning\n%s" % result.stderr)


def test_external_resource_warning(w):
    body = h.VALID.replace("rounded=0;", "rounded=0;image=https://example.com/a.png;")
    w.write("ext.drawio", body)
    result = w.run(["-f", "svg", "--check-only", "-o", w.path("out.svg"), w.path("ext.drawio")])
    h.assert_exit(result, 0, "external resource")
    h.assert_stderr_contains(result, "外部リソース参照", "external resource")

    allowed = w.run(
        ["-f", "svg", "--check-only", "--allow-external", "-o", w.path("out.svg"), w.path("ext.drawio")]
    )
    h.assert_exit(allowed, 0, "external resource allowed")
    if "外部リソース参照" in allowed.stderr:
        raise AssertionError("--allow-external should suppress the warning\n%s" % allowed.stderr)


# ---------------------------------------------------------------------------
# 3. usage / argument handling (exit 4)
# ---------------------------------------------------------------------------

def test_same_file_input_and_output_rejected(w):
    path = w.write("ok.drawio", h.VALID)
    result = w.run(["-f", "svg", "--check-only", "-o", path, path])
    h.assert_exit(result, 4, "same file")
    h.assert_stderr_contains(result, "出力先には指定できません", "same file")


def test_usage_errors(w):
    w.write("ok.drawio", h.VALID)
    cases = [
        (["-f", "svg", "--check-only", w.path("ok.drawio")], "missing -o"),
        (["-f", "svg", "--check-only", "-o", w.path("out.svg")], "missing input"),
        (["--bogus", "-o", w.path("out.svg"), w.path("ok.drawio")], "unknown option"),
        (["-f", "eps", "-o", w.path("out.eps"), w.path("ok.drawio")], "unsupported format"),
        (["-o", w.path("out.txt"), w.path("ok.drawio")], "format not inferable"),
        (["-f", "svg", "-s", "0", "-o", w.path("out.svg"), w.path("ok.drawio")], "non-positive scale"),
        (["-f", "svg", "-p", "0", "-o", w.path("out.svg"), w.path("ok.drawio")], "page index below 1"),
        (["-f", "png", "--embed-xml", "-o", w.path("out.png"), w.path("ok.drawio")], "--embed-xml on png"),
        (["-f", "svg", "-o", w.path("out.svg"), w.path("missing.drawio")], "input does not exist"),
        (["-f", "svg", "-o", w.path("nodir/out.svg"), w.path("ok.drawio")], "output dir missing"),
        (["-f", "svg", "-o", w.path("ok.drawio"), "extra.drawio", w.path("ok.drawio")], "two inputs"),
    ]
    for args, label in cases:
        h.assert_exit(w.run(args), 4, "usage: %s" % label)


# ---------------------------------------------------------------------------
# 4. lock exclusion and conflict detection
# ---------------------------------------------------------------------------

def test_output_lock_is_exclusive(w):
    w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    os.mkdir(output + ".lock")
    result = w.run(["-f", "svg", "-o", output, w.path("ok.drawio")])
    h.assert_exit(result, 2, "lock held")
    h.assert_stderr_contains(result, "別プロセスが同じ出力へ export 中です", "lock held")
    h.assert_missing(output, "lock held")
    if not os.path.isdir(output + ".lock"):
        raise AssertionError("lock held: the wrapper removed a lock it does not own")


def test_lock_released_on_success(w):
    w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    result = w.run(["-f", "svg", "-o", output, w.path("ok.drawio")])
    h.assert_exit(result, 0, "stub export")
    if not os.path.exists(output):
        raise AssertionError("stub export: verified output was not published")
    if os.path.exists(output + ".lock"):
        raise AssertionError("stub export: lock directory survived a successful run")


BROKEN_OUTPUT_STUB = """
printf '%s\\n' "$*" >> "$STUB_LOG"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then out="$arg"; fi
  prev="$arg"
done
if [ -n "$out" ]; then
  printf 'not xml at all <<<\\n' > "$out"
fi
exit 0
"""


def test_unverifiable_output_is_not_published(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    w.set_stub(BROKEN_OUTPUT_STUB)
    result = w.run(["-f", "svg", "-o", output, source])
    h.assert_exit(result, 2, "unverifiable output")
    h.assert_missing(output, "unverifiable output")


def test_failed_export_is_not_published(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    w.set_stub('printf "%s\\n" "$*" >> "$STUB_LOG"\necho "boom" >&2\nexit 7\n')
    result = w.run(["-f", "svg", "-o", output, source])
    h.assert_exit(result, 2, "export failure")
    h.assert_stderr_contains(result, "draw.io export に失敗しました", "export failure")
    h.assert_missing(output, "export failure")


def test_input_mutation_during_export_is_conflict(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    w.set_stub(MUTATING_STUB)
    result = w.run(["-f", "svg", "-o", output, source], env={"MUTATE_TARGET": source})
    h.assert_exit(result, 3, "mutation during export")
    h.assert_stderr_contains(result, "出力は公開していません", "mutation during export")
    h.assert_missing(output, "mutation during export")


def test_no_temp_residue_after_conflict(w):
    source = w.write("ok.drawio", h.VALID)
    w.set_stub(MUTATING_STUB)
    w.run(["-f", "svg", "-o", w.path("out.svg"), source], env={"MUTATE_TARGET": source})
    residue = [name for name in os.listdir(w.root) if name.startswith(".drawio-verify-export.")]
    if residue:
        raise AssertionError("conflict left temp directories behind: %s" % residue)


# ---------------------------------------------------------------------------
# 5. smoke tests that need the genuine draw.io CLI
# ---------------------------------------------------------------------------

def test_smoke_svg_export(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    result = w.run(["-f", "svg", "-o", output, source], use_stub=False)
    h.assert_exit(result, 0, "smoke svg")
    if not os.path.exists(output) or os.path.getsize(output) == 0:
        raise AssertionError("smoke svg: output missing or empty")
    published = result.stdout.strip()
    if not os.path.isabs(published) or not os.path.samefile(published, output):
        raise AssertionError(
            "smoke svg: stdout should be the published absolute path, got %r" % result.stdout
        )


def test_smoke_png_export(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.png")
    result = w.run(["-f", "png", "-s", "2", "-o", output, source], use_stub=False)
    h.assert_exit(result, 0, "smoke png")
    with open(output, "rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise AssertionError("smoke png: output is not a PNG")


def test_smoke_embed_xml_svg(w):
    source = w.write("ok.drawio", h.VALID)
    output = w.path("out.svg")
    result = w.run(["-f", "svg", "--embed-xml", "-o", output, source], use_stub=False)
    h.assert_exit(result, 0, "smoke embed-xml")
    with open(output, encoding="utf-8") as handle:
        if "content=" not in handle.read():
            raise AssertionError("smoke embed-xml: no content attribute in the SVG")


# ---------------------------------------------------------------------------

# Two invariants were retired by a contract decision rather than by the port.
# contracts/delivery.md §2.1 removes the output lock: the generation layout
# leaves only the source file and the current pointer shared, and both are
# guarded by the hash handoff. INV-13 asserts the lock excludes a second
# process, INV-14 asserts a successful run releases it and publishes to the -o
# path. Neither statement can be made about a CLI that has no lock and
# publishes into a generation, so they are skipped for the etch CLI and their
# replacement is asserted by MIG-08, MIG-09 and MIG-13.
#
# The three smoke cases are skipped for the same kind of reason: they assert
# that the artifact appears at the -o path and that stdout is that path, which
# MIG-06 and MIG-08 deliberately replace. Real export against the new
# publication layout is the gate of Phase 1d (docs/PLAN.md §10).
SUPERSEDED_BY_CONTRACT = {
    "INV-13 output lock is exclusive": "no output lock in v1 (delivery.md §2.1); see MIG-13",
    "INV-14 lock is released on success": "publication moved to generations; see MIG-08/09",
    "SMOKE-01 real svg export": "asserts the legacy -o publication and stdout path; Phase 1d",
    "SMOKE-02 real png export": "asserts the legacy -o publication; Phase 1d",
    "SMOKE-03 real svg export with embedded xml": "asserts the legacy -o publication; Phase 1d",
}


def build_cases():
    if h.NEW_CLI:
        # xmllint, file and shasum are optional for the etch CLI, so their
        # absence no longer decides whether a case can run at all.
        base_skip = None
    else:
        missing = h.missing_commands(["xmllint", "shasum", "file"])
        base_skip = "requires %s" % ", ".join(missing) if missing else None
    smoke_skip = base_skip or (None if h.real_drawio_present() else "requires the draw.io CLI")

    invariants = [
        ("INV-01 malformed XML is rejected", test_malformed_xml_rejected),
        ("INV-02 raw ampersand hint is emitted", test_raw_ampersand_hint),
        ("INV-03 dangling parent reference detected", test_dangling_parent_reference),
        ("INV-04 dangling edge target detected", test_dangling_edge_target),
        ("INV-05 duplicate mxCell id detected", test_duplicate_cell_id),
        ("INV-06 root element must be mxfile", test_root_element_must_be_mxfile),
        ("INV-07 page index out of range", test_page_index_out_of_range),
        ("INV-08 missing compressed=false warns only", test_compressed_false_missing_warns_but_passes),
        ("INV-09 compressed=false is silent", test_compressed_false_present_is_silent),
        ("INV-10 external resource reference warns", test_external_resource_warning),
        ("INV-11 input as its own output is rejected", test_same_file_input_and_output_rejected),
        ("INV-12 usage errors exit 4", test_usage_errors),
        ("INV-13 output lock is exclusive", test_output_lock_is_exclusive),
        ("INV-14 lock is released on success", test_lock_released_on_success),
        ("INV-15 mutation during export is a conflict", test_input_mutation_during_export_is_conflict),
        ("INV-16 conflict leaves no temp residue", test_no_temp_residue_after_conflict),
        ("INV-17 unverifiable output is not published", test_unverifiable_output_is_not_published),
        ("INV-18 failed export is not published", test_failed_export_is_not_published),
    ]
    smokes = [
        ("SMOKE-01 real svg export", test_smoke_svg_export),
        ("SMOKE-02 real png export", test_smoke_png_export),
        ("SMOKE-03 real svg export with embedded xml", test_smoke_embed_xml_svg),
    ]
    def skip_for(label):
        if h.NEW_CLI and label in SUPERSEDED_BY_CONTRACT:
            return SUPERSEDED_BY_CONTRACT[label]
        return base_skip

    return (
        [(label, skip_for(label), function) for label, function in invariants]
        + [
            (label, SUPERSEDED_BY_CONTRACT[label] if h.NEW_CLI else smoke_skip, function)
            for label, function in smokes
        ]
    )


def select_subject():
    """Phase 1b: ETCH_CLI points the same invariants at the new CLI."""
    new_cli = os.environ.get("ETCH_CLI")
    if not new_cli:
        return
    h.LEGACY_WRAPPER = new_cli
    h.NEW_CLI = True
    h.ARGV_ADAPTER = h.legacy_to_etch


def main():
    select_subject()
    failures, _, _ = h.run_suite("characterization: invariants", build_cases(), h.verbose_flag())
    if failures:
        print("\nFAILED: %d case(s)" % failures)
        return 1
    subject = "the etch CLI" if h.NEW_CLI else "the legacy wrapper"
    print("\nOK: %s still behaves as characterized" % subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
