#!/usr/bin/env python3
"""Shared plumbing for the characterization tests.

Runs with python3 >= 3.9 and the standard library only, per
contracts/environment.md. No test framework: a test is a function that raises
AssertionError, and the runners below count what raised.

Every case executes the wrapper under test in a fresh temporary directory with
fixture .drawio files generated here. Nothing outside that directory is read or
written, so the Koyo-HQ vault is never touched by a test run.
"""

import json
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

# Phase 1b: when the subject is the etch CLI the suites still state the SAME
# expectations, but the surface they are stated against moved. Two adapters live
# here so that no test case body has to be rewritten:
#
#   ARGV_ADAPTER  translates a legacy argument vector into an etch one
#   NEW_CLI       switches assert_stderr_contains to look for the diagnostic
#                 that now carries the finding, instead of the Japanese prose
#                 the legacy wrapper printed
#
# Both are off unless a suite turns them on.
NEW_CLI = False
ARGV_ADAPTER = None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCHEMA_TOOLS = []


def schema_check(stdout, label):
    """Every document the etch CLI writes must satisfy the published schema.

    The checker is the same one scripts/validate-contracts.py uses on its
    fixtures, so a document that passes here passes there too.
    """
    text = stdout.strip()
    if not text:
        return
    try:
        document = json.loads(text)
    except ValueError:
        raise AssertionError("%s: stdout is not a single JSON document:\n%s" % (label, stdout))
    if not _SCHEMA_TOOLS:
        import importlib.util

        path = os.path.join(REPO_ROOT, "scripts", "validate-contracts.py")
        spec = importlib.util.spec_from_file_location("validate_contracts", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with open(
            os.path.join(REPO_ROOT, "contracts", "diagnostics.schema.json"), encoding="utf-8"
        ) as handle:
            _SCHEMA_TOOLS.extend([module.validate, json.load(handle)])
    validate, schema = _SCHEMA_TOOLS
    errors = validate(document, schema, schema)
    if errors:
        raise AssertionError(
            "%s: the diagnostics document violates the schema:\n  %s" % (label, "\n  ".join(errors))
        )


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


# A stub that writes a real PNG, so the chunk walk, the CRC checks and the IDAT
# inflate all have something genuine to inspect. python3 builds it because a
# valid PNG is not something bash should be asked to emit.
PNG_STUB = """
printf '%s\\n' "$*" >> "$STUB_LOG"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then out="$arg"; fi
  prev="$arg"
done
if [ -n "$out" ]; then
  python3 - "$out" <<'PYEOF'
import struct, sys, zlib

width = height = 2
raw = b"".join(b"\\x00" + b"\\xff\\x00\\x00" * width for _ in range(height))


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


with open(sys.argv[1], "wb") as handle:
    handle.write(b"\\x89PNG\\r\\n\\x1a\\n")
    handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    handle.write(chunk(b"IDAT", zlib.compress(raw)))
    handle.write(chunk(b"IEND", b""))
PYEOF
fi
exit 0
"""


class Workspace(object):
    """A temp directory plus a PATH front-loaded with a stub draw.io."""

    def __init__(self, stub_body=None):
        self.root = tempfile.mkdtemp(prefix="etch-characterization.")
        self.bin = os.path.join(self.root, "bin")
        os.mkdir(self.bin)
        # A PATH that holds python3 and nothing else, for the cases that have to
        # run with a dependency genuinely absent rather than merely unused.
        self.emptybin = os.path.join(self.root, "emptybin")
        os.mkdir(self.emptybin)
        # bash and python3 are declared runtime dependencies (environment.md
        # §2, §3), so they stay reachable; what this PATH withholds is the
        # optional tooling and draw.io itself.
        for name in ("python3", "bash"):
            found = shutil.which(name)
            if found:
                os.symlink(found, os.path.join(self.emptybin, name))
        # And a PATH with only bash, for the case where python3 itself is the
        # missing dependency and the bash entry point has to report it alone.
        self.bashonly = os.path.join(self.root, "bashonly")
        os.mkdir(self.bashonly)
        found = shutil.which("bash")
        if found:
            os.symlink(found, os.path.join(self.bashonly, "bash"))
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
        args = ARGV_ADAPTER(list(args), self) if ARGV_ADAPTER else list(args)
        result = subprocess.run(
            [LEGACY_WRAPPER] + list(args),
            cwd=self.root,
            env=environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=180,
        )
        if NEW_CLI:
            schema_check(result.stdout, "etch %s" % " ".join(args[:2]))
        return result

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 1b adapters
# ---------------------------------------------------------------------------

def legacy_to_etch(args, workspace):
    """Translate a legacy argument vector into the etch CLI's surface.

    The mapping is mechanical:

      --check-only        -> `etch validate`
      anything else       -> `etch deliver` (the subcommand that publishes)
      -o <path>           -> --output-root, see output_root_for() below
      -p / -s / --embed-xml / --allow-external -> their long forms

    Options the legacy wrapper did not know stay untouched, so an unknown option
    is still an unknown option to the subject under test.

    A legacy call with no -o at all is translated to `deliver`, not `validate`:
    the case exists to assert that a missing mandatory argument is a usage
    error, and --output-root is where that obligation now lives.
    """
    fmt = page = scale = out = None
    check_only = allow_external = embed = False
    inputs = []
    extra = []
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if token == "-f" and rest:
            fmt = rest.pop(0)
        elif token in ("-p", "--page-index") and rest:
            page = rest.pop(0)
        elif token == "-s" and rest:
            scale = rest.pop(0)
        elif token == "-o" and rest:
            out = rest.pop(0)
        elif token == "--check-only":
            check_only = True
        elif token == "--allow-external":
            allow_external = True
        elif token == "--embed-xml":
            embed = True
        elif token.startswith("-"):
            extra.append(token)
        else:
            inputs.append(token)

    # --check-only becomes `validate`, except when -o names something that
    # already exists: the legacy wrapper rejected that at argument-validation
    # time, before --check-only had any effect (INV-11), so the translation has
    # to keep it on the subcommand that owns an output location.
    if check_only and out is not None and not os.path.exists(out):
        argv = ["validate"]
    else:
        argv = ["deliver"]
        if fmt is not None:
            argv += ["--format", fmt]
        root = output_root_for(out, workspace)
        if root is not None:
            argv += ["--output-root", root]
        if scale is not None:
            argv += ["--scale", scale]
        if embed:
            argv.append("--embed-xml")
    if page is not None:
        argv += ["--page", page]
    if allow_external:
        argv.append("--allow-external")
    return argv + extra + inputs


def output_root_for(out, workspace):
    """Map the legacy -o file path onto an output root directory.

    The legacy wrapper published one artifact at one path; the etch CLI
    publishes a generation under a root. Three situations have to stay
    distinguishable, because separate invariants rest on them:

      * -o names something that already exists (INV-11 points it at the input
        file) -> pass it through, so the CLI rejects a non-directory
      * -o names a path whose parent is missing -> pass it through, so the CLI
        rejects a missing output location
      * -o names a plain new artifact path -> give the CLI a sibling directory
        and never create the artifact path itself, so `assert_missing(output)`
        keeps meaning "nothing was published"
    """
    if out is None:
        return None
    parent = os.path.dirname(out) or "."
    if os.path.exists(out) or not os.path.isdir(parent):
        return out
    root = out + ".generations"
    if not os.path.isdir(root):
        os.mkdir(root)
    return root


# Where each legacy stderr phrase now shows up. The condition being asserted is
# the same one; only its carrier moved from Japanese prose to a diagnostic code
# (or, for usage errors which emit no JSON, to English prose on stderr).
NEEDLE_MAP = {
    "XML が不正です": ("code", "xml/not-well-formed"),
    "生の &": ("code", "xml/raw-ampersand"),
    "参照先がありません": ("code", "xml/missing-reference"),
    "target 参照先がありません": ("code", "xml/missing-reference", "target"),
    "重複しています": ("code", "xml/duplicate-cell-id"),
    "root 要素": ("code", "xml/root-element"),
    "ページ番号が範囲外": ("code", "input/page-out-of-range"),
    'compressed="false" ではありません': ("code", "input/compressed-attribute"),
    "外部リソース参照": ("code", "security/external-ref"),
    "draw.io export に失敗しました": ("code", "export/failed"),
    "出力は公開していません": ("code", "delivery/hash-conflict"),
    "出力先には指定できません": ("stderr", "output root"),
}


def assert_diagnostic(result, needle, label):
    mapping = NEEDLE_MAP.get(needle)
    if mapping is None:
        raise AssertionError("%s: no etch mapping for the legacy phrase %r" % (label, needle))
    if mapping[0] == "stderr":
        if mapping[1] not in result.stderr.lower():
            raise AssertionError(
                "%s: stderr does not mention %r\n--- stderr ---\n%s"
                % (label, mapping[1], result.stderr)
            )
        return
    code = mapping[1]
    required_text = mapping[2] if len(mapping) > 2 else None
    try:
        document = json.loads(result.stdout)
    except ValueError:
        raise AssertionError(
            "%s: expected a diagnostics document on stdout\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, result.stdout, result.stderr)
        )
    for diagnostic in document.get("diagnostics", []):
        if diagnostic.get("code") != code:
            continue
        if required_text is None or required_text in json.dumps(diagnostic, ensure_ascii=False):
            return
    raise AssertionError(
        "%s: no %s diagnostic%s\n--- stdout ---\n%s"
        % (label, code, "" if required_text is None else " mentioning %r" % required_text,
           result.stdout)
    )


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
    if NEW_CLI:
        return assert_diagnostic(result, needle, label)
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
