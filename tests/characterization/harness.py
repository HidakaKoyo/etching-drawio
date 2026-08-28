#!/usr/bin/env python3
"""Shared plumbing for the characterization tests.

Runs with python3 >= 3.9 and the standard library only, per
contracts/environment.md. No test framework: a test is a function that raises
AssertionError, and the runners below count what raised.

Every case executes the wrapper under test in a fresh temporary directory with
fixture .drawio files generated here. Nothing outside that directory is read or
written, so the Koyo-HQ vault is never touched by a test run.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

VAULT_WRAPPER = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Koyo-HQ/bin/drawio-verify-export"
)

# The subject under test. Phase 1b points this at the new CLI for the migration
# suite; the invariant suite keeps pointing at the legacy wrapper.
LEGACY_WRAPPER = os.environ.get("LEGACY_WRAPPER", VAULT_WRAPPER)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def mxfile(body, compressed=True):
    attr = ' compressed="false"' if compressed else ""
    return '<mxfile host="characterization"%s>\n%s\n</mxfile>\n' % (attr, body)


def page(cells, name="Page-1"):
    return textwrap.dedent(
        """\
          <diagram id="d1" name="%s">
            <mxGraphModel dx="800" dy="600" grid="0" page="1">
              <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
        %s
              </root>
            </mxGraphModel>
          </diagram>"""
    ) % (name, cells)


VERTEX = (
    '        <mxCell id="%s" value="%s" style="rounded=0;" vertex="1" parent="1">\n'
    '          <mxGeometry x="40" y="40" width="120" height="60" as="geometry"/>\n'
    "        </mxCell>"
)

VALID = mxfile(page(VERTEX % ("n1", "A")))

MALFORMED_XML = '<mxfile compressed="false">\n  <diagram id="d1">\n</mxfile>\n'

RAW_AMPERSAND = mxfile(page(VERTEX % ("n1", "A &amp; B")).replace("A &amp; B", "A & B"))

DANGLING_PARENT = mxfile(
    page(
        VERTEX % ("n1", "A")
        + "\n"
        + '        <mxCell id="n2" style="rounded=0;" vertex="1" parent="ghost">\n'
        '          <mxGeometry x="200" y="40" width="120" height="60" as="geometry"/>\n'
        "        </mxCell>"
    )
)

DANGLING_EDGE_TARGET = mxfile(
    page(
        VERTEX % ("n1", "A")
        + "\n"
        + '        <mxCell id="e1" edge="1" parent="1" source="n1" target="ghost">\n'
        '          <mxGeometry relative="1" as="geometry"/>\n'
        "        </mxCell>"
    )
)

DUPLICATE_ID = mxfile(page(VERTEX % ("n1", "A") + "\n" + VERTEX % ("n1", "B")))

NOT_MXFILE = '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>\n'

UNCOMPRESSED_ATTR_MISSING = mxfile(page(VERTEX % ("n1", "A")), compressed=False)


# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------

# A stub draw.io that logs its arguments and writes a minimal but valid SVG to
# whatever -o names, so the wrapper's output verification has something real to
# inspect without launching draw.io Desktop.
DEFAULT_STUB = """
printf '%s\\n' "$*" >> "$STUB_LOG"
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


class Workspace(object):
    """A temp directory plus a PATH front-loaded with a stub draw.io."""

    def __init__(self, stub_body=None):
        self.root = tempfile.mkdtemp(prefix="etch-characterization.")
        self.bin = os.path.join(self.root, "bin")
        os.mkdir(self.bin)
        self.stub_log = os.path.join(self.root, "stub.log")
        self._write_stub(DEFAULT_STUB if stub_body is None else stub_body)

    def set_stub(self, body):
        """Replace the stub draw.io with a different bash body."""
        self._write_stub(body)

    def _write_stub(self, body):
        path = os.path.join(self.bin, "drawio")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("#!/usr/bin/env bash\nset -eu\n" + body)
        os.chmod(path, 0o755)

    def write(self, name, content):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def path(self, name):
        return os.path.join(self.root, name)

    def run(self, args, use_stub=True, env=None):
        environ = dict(os.environ)
        environ["STUB_LOG"] = self.stub_log
        if use_stub:
            environ["PATH"] = self.bin + os.pathsep + environ.get("PATH", "")
        if env:
            environ.update(env)
        return subprocess.run(
            [LEGACY_WRAPPER] + list(args),
            cwd=self.root,
            env=environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=180,
        )

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ---------------------------------------------------------------------------
# assertions
# ---------------------------------------------------------------------------

def assert_exit(result, expected, label):
    if result.returncode != expected:
        raise AssertionError(
            "%s: expected exit %d, got %d\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, expected, result.returncode, result.stdout, result.stderr)
        )


def assert_stderr_contains(result, needle, label):
    if needle not in result.stderr:
        raise AssertionError(
            "%s: stderr does not contain %r\n--- stderr ---\n%s" % (label, needle, result.stderr)
        )


def assert_missing(path, label):
    if os.path.exists(path):
        raise AssertionError("%s: %s should not exist but does" % (label, path))


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

def missing_commands(names):
    return [name for name in names if shutil.which(name) is None]


def real_drawio_present():
    """True when a genuine draw.io CLI is on PATH (the stub is not on it yet)."""
    return shutil.which("drawio") is not None


def run_suite(title, cases, verbose=False):
    """cases: list of (label, requirement_or_None, callable).

    A requirement is a string naming a precondition; when the matching probe
    fails the case is reported as skipped rather than failed.
    """
    print("== %s" % title)
    print("   subject: %s" % LEGACY_WRAPPER)
    if not os.path.exists(LEGACY_WRAPPER):
        print("   FATAL: subject not found")
        return 1, 0, len(cases)

    failures = 0
    passed = 0
    skipped = 0
    for label, skip_reason, function in cases:
        if skip_reason:
            skipped += 1
            print("  skip %-52s (%s)" % (label, skip_reason))
            continue
        workspace = Workspace()
        try:
            function(workspace)
        except AssertionError as error:
            failures += 1
            print("  FAIL %s" % label)
            for line in str(error).splitlines():
                print("       %s" % line)
        except Exception as error:  # noqa: BLE001 - report, do not mask
            failures += 1
            print("  ERROR %s: %s: %s" % (label, type(error).__name__, error))
        else:
            passed += 1
            if verbose:
                print("  ok   %s" % label)
        finally:
            workspace.close()
    print("  %d passed, %d failed, %d skipped" % (passed, failures, skipped))
    return failures, passed, skipped


def verbose_flag():
    return "-v" in sys.argv
