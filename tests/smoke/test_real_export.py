#!/usr/bin/env python3
"""Real draw.io Desktop export smoke test (docs/PLAN.md §10 Phase 1d).

Everything else in tests/ runs against a bash stub standing in for draw.io. This
suite is the one place where the genuine article runs: DRAWIO_CMD resolution,
`etch export` / `etch deliver` / `etch verify`, and the SVG / PNG / PDF output
checks, all against real exporter output.

Where draw.io Desktop is absent the suite skips with a printed reason and exits
0, so it can sit in a pipeline that does not everywhere have a GUI app
installed. python3 >= 3.9, standard library only (contracts/environment.md).

    python3 tests/smoke/test_real_export.py [-v]
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ETCH = os.environ.get("ETCH_CLI", os.path.join(REPO_ROOT, "bin", "etch"))
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "smoke.drawio")
VENDOR_LOCK = os.path.join(REPO_ROOT, "skills", "etching", "vendor.lock")
VERSION_FILE = os.path.join(REPO_ROOT, "skills", "etching", "VERSION")

# The draw.io Desktop this gate was passed against. CI pins one build and
# passes it in; where the receipt records anything else, the evidence is about
# a different exporter than the one the gate names, so the run fails rather
# than quietly reporting on whatever happened to be installed.
EXPECTED_DRAWIO_VERSION = os.environ.get("EXPECT_DRAWIO_VERSION")

sys.path.insert(0, os.path.join(REPO_ROOT, "lib"))
import etch_export  # noqa: E402

EXPORT_TIMEOUT_SECONDS = 300


class SilentReport(object):
    """resolve_drawio reports through this; here the answer alone matters."""

    def failed(self, *_args, **_kwargs):
        pass

    def diagnostic(self, *_args, **_kwargs):
        pass


def resolve_drawio():
    """The CLI's own resolution order, or None when nothing is installed."""
    try:
        return etch_export.resolve_drawio(SilentReport())
    except etch_export.DependencyMissing:
        return None


def fallback_candidate():
    """An installed draw.io that resolution finds *after* PATH, if there is one."""
    for candidate in etch_export.MACOS_BUNDLES + etch_export.LINUX_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# ---------------------------------------------------------------------------
# running the CLI
# ---------------------------------------------------------------------------


class Workspace(object):
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="etch-smoke.")
        self.source = os.path.join(self.root, "smoke.drawio")
        shutil.copyfile(FIXTURE, self.source)
        self.output_root = os.path.join(self.root, "out")
        os.mkdir(self.output_root)
        # A PATH holding the declared runtime dependencies and nothing else, so
        # a case can withhold draw.io from PATH without withholding python3.
        self.leanbin = os.path.join(self.root, "leanbin")
        os.mkdir(self.leanbin)
        for name in ("python3", "bash"):
            found = shutil.which(name)
            if found:
                os.symlink(found, os.path.join(self.leanbin, name))

    def run(self, args, env=None):
        environ = dict(os.environ)
        if env:
            for key, value in env.items():
                if value is None:
                    environ.pop(key, None)
                else:
                    environ[key] = value
        return subprocess.run(
            [ETCH] + list(args),
            cwd=self.root,
            env=environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=EXPORT_TIMEOUT_SECONDS,
        )

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def report_of(result, label):
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise AssertionError(
            "%s: expected a diagnostics document on stdout\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, result.stdout, result.stderr)
        )


def assert_passed(result, label):
    if result.returncode != 0:
        raise AssertionError(
            "%s: expected exit 0, got %d\n--- stdout ---\n%s--- stderr ---\n%s"
            % (label, result.returncode, result.stdout, result.stderr)
        )
    document = report_of(result, label)
    if document.get("status") != "passed":
        raise AssertionError("%s: status is %r, expected passed" % (label, document.get("status")))
    return document


def assert_check_passed(document, check_id, label):
    for check in document.get("checks", []):
        if check.get("id") == check_id:
            if check.get("status") != "passed":
                raise AssertionError(
                    "%s: check %s is %r" % (label, check_id, check.get("status"))
                )
            return
    raise AssertionError("%s: no %s check in the document" % (label, check_id))


def artifact_paths(document):
    return [artifact["path"] for artifact in document.get("artifacts", [])]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_version_file():
    try:
        with open(VERSION_FILE, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def assert_receipt(receipt, generation, source_path, label):
    """Every field of contracts/delivery.md §6, checked against what is on disk.

    A receipt is the only durable evidence a delivery leaves behind, so the
    smoke test reads it the way a later `etch verify` or an auditor would:
    recomputing the hashes rather than trusting that they were written.
    """
    version = receipt.get("drawio", {}).get("version")
    if not version or version == "unknown":
        raise AssertionError(
            "%s: the receipt records the draw.io version as %r" % (label, version)
        )
    if EXPECTED_DRAWIO_VERSION and version != EXPECTED_DRAWIO_VERSION:
        raise AssertionError(
            "%s: the receipt records draw.io %r, but this run pins %r"
            % (label, version, EXPECTED_DRAWIO_VERSION)
        )

    expected_tool = read_version_file()
    if expected_tool and receipt.get("toolVersion") != expected_tool:
        raise AssertionError(
            "%s: the receipt records toolVersion %r, skills/etching/VERSION says %r"
            % (label, receipt.get("toolVersion"), expected_tool)
        )

    source = receipt.get("source", {})
    if source.get("sha256") != sha256_file(source_path):
        raise AssertionError(
            "%s: the receipt's source hash is not the hash of %s" % (label, source_path)
        )
    if source.get("role") != "master":
        raise AssertionError("%s: source role is %r" % (label, source.get("role")))

    artifacts = receipt.get("artifacts")
    if not artifacts:
        raise AssertionError("%s: the receipt records no artifacts" % label)
    for artifact in artifacts:
        path = artifact.get("path")
        if not os.path.isabs(path):
            path = os.path.join(generation, path)
        if not os.path.isfile(path):
            raise AssertionError("%s: receipt names a missing artifact %s" % (label, path))
        if artifact.get("sha256") != sha256_file(path):
            raise AssertionError("%s: %s does not hash to what the receipt says" % (label, path))

    lock = receipt.get("vendorLock")
    if not lock or lock.get("sha256") != sha256_file(VENDOR_LOCK):
        raise AssertionError("%s: the receipt's vendor.lock hash is wrong or absent" % label)

    if not receipt.get("checks"):
        raise AssertionError("%s: the receipt records no checks" % label)


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------


def export_format(fmt):
    """One real export per format, checked as far as the output verification."""

    def case(workspace):
        label = "export %s" % fmt
        document = assert_passed(
            workspace.run(
                ["export", "--format", fmt, "--output-root", workspace.output_root, workspace.source]
            ),
            label,
        )
        assert_check_passed(document, "export/run", label)
        assert_check_passed(document, "export/%s-valid" % fmt, label)
        produced = artifact_paths(document)
        if len(produced) != 1:
            raise AssertionError("%s: expected one artifact, got %r" % (label, produced))
        if not os.path.isfile(produced[0]) or os.path.getsize(produced[0]) == 0:
            raise AssertionError("%s: %s is missing or empty" % (label, produced[0]))
        # export builds a generation but must leave the pointer alone.
        if os.path.lexists(os.path.join(workspace.output_root, "current")):
            raise AssertionError("%s: export moved the current pointer" % label)

    return case


def case_deliver_and_verify(workspace):
    """deliver commits the pointer; verify then reads the generation back."""
    label = "deliver svg"
    document = assert_passed(
        workspace.run(
            ["deliver", "--format", "svg", "--output-root", workspace.output_root, workspace.source]
        ),
        label,
    )
    assert_check_passed(document, "delivery/pointer", label)

    pointer = os.path.join(workspace.output_root, "current")
    generation = os.path.realpath(pointer)
    if not os.path.isdir(generation):
        raise AssertionError("%s: current does not resolve to a directory" % label)

    receipt_path = os.path.join(generation, "receipt.json")
    with open(receipt_path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    assert_receipt(receipt, generation, workspace.source, label)

    verified = assert_passed(
        workspace.run(["verify", "--output-root", workspace.output_root]), "verify"
    )
    assert_check_passed(verified, "delivery/artifacts", "verify")
    assert_check_passed(verified, "delivery/handoff", "verify")


def case_explicit_drawio_cmd(workspace):
    """DRAWIO_CMD names the executable outright and is used as given."""
    command = resolve_drawio()
    document = assert_passed(
        workspace.run(
            ["export", "--format", "svg", "--output-root", workspace.output_root, workspace.source],
            env={"DRAWIO_CMD": command},
        ),
        "DRAWIO_CMD",
    )
    assert_check_passed(document, "dependency/drawio", "DRAWIO_CMD")


def case_bundle_fallback(workspace):
    """With draw.io off PATH, resolution falls through to the installed path."""
    document = assert_passed(
        workspace.run(
            ["export", "--format", "svg", "--output-root", workspace.output_root, workspace.source],
            env={"PATH": workspace.leanbin, "DRAWIO_CMD": None},
        ),
        "fallback resolution",
    )
    assert_check_passed(document, "export/run", "fallback resolution")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


def main():
    verbose = "-v" in sys.argv
    print("== Phase 1d real export smoke")
    print("   subject: %s" % ETCH)

    explicit = os.environ.get("DRAWIO_CMD")
    command = resolve_drawio()
    if command is None and explicit:
        # A DRAWIO_CMD that was set on purpose and does not work is a broken
        # environment, not an absent one. Skipping here would hide it.
        print("  FAIL DRAWIO_CMD is set to %s, which is not an executable file" % explicit)
        print("  0 passed, 1 failed, 0 skipped")
        return 1
    if command is None:
        print(
            "   SKIP: draw.io Desktop was not found (PATH, macOS bundle, Linux defaults, "
            "DRAWIO_CMD all came up empty); real export cannot be exercised here"
        )
        return 0
    installed = etch_export.drawio_version(command)
    print("   draw.io: %s (%s)" % (command, installed))
    if EXPECTED_DRAWIO_VERSION:
        print("   pinned:  %s" % EXPECTED_DRAWIO_VERSION)
        if installed != EXPECTED_DRAWIO_VERSION:
            # Running the suite against a different build would produce a green
            # result about an exporter the gate does not name.
            print(
                "  FAIL the installed draw.io reports %r, but this run pins %r"
                % (installed, EXPECTED_DRAWIO_VERSION)
            )
            print("  0 passed, 1 failed, 0 skipped")
            return 1

    on_path = shutil.which("drawio")
    fallback = fallback_candidate()
    cases = [
        ("export svg", None, export_format("svg")),
        ("export png", None, export_format("png")),
        ("export pdf", None, export_format("pdf")),
        ("deliver svg + verify", None, case_deliver_and_verify),
        ("DRAWIO_CMD is used as given", None, case_explicit_drawio_cmd),
        (
            "resolution falls back off PATH",
            None
            if fallback
            else "no draw.io outside PATH (%s)" % (on_path or "none"),
            case_bundle_fallback,
        ),
    ]

    failures = passed = skipped = 0
    for label, skip_reason, function in cases:
        if skip_reason:
            skipped += 1
            print("  skip %-40s (%s)" % (label, skip_reason))
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
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
