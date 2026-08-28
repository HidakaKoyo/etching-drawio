"""The diagnostics document: checks, diagnostics, artifacts and their aggregate.

The document written to stdout is the machine-readable contract of the CLI
(contracts/diagnostics.schema.json). stdout carries the JSON and nothing else;
every human-readable line goes to stderr.
"""

import hashlib
import json
import os
import sys

SCHEMA_VERSION = "1.0.0"

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"


class UsageError(Exception):
    """Arguments or profile are unusable, so no document can be built (exit 4)."""


class Interrupted(Exception):
    """A signal arrived mid-run (exit 130). No document is emitted."""


class Report(object):
    def __init__(self, tool_version, quiet=False):
        self.tool_version = tool_version
        self.checks = []
        self.diagnostics = []
        self.artifacts = []
        self.quiet = quiet

    # -- checks -------------------------------------------------------------

    def check(self, check_id, status, required=True, waiver=None):
        entry = {"id": check_id, "required": required, "status": status}
        if waiver is not None:
            if required:
                raise ValueError("a required check cannot carry a waiver: %s" % check_id)
            entry["waiver"] = waiver
        self.checks.append(entry)
        return entry

    def passed(self, check_id, required=True):
        return self.check(check_id, PASSED, required=required)

    def failed(self, check_id, required=True):
        return self.check(check_id, FAILED, required=required)

    def skipped(self, check_id, required=False, waiver=None):
        return self.check(check_id, SKIPPED, required=required, waiver=waiver)

    # -- diagnostics --------------------------------------------------------

    def diagnostic(self, code, message, file, severity="error", **subject):
        entry = {
            "code": code,
            "severity": severity,
            "message": message,
            "subject": {"file": file},
        }
        for key in ("xpath", "cellId", "line"):
            if subject.get(key) is not None:
                entry["subject"][key] = subject[key]
        evidence = {}
        for key in ("expected", "actual", "params"):
            if subject.get(key) is not None:
                evidence[key] = subject[key]
        if evidence:
            entry["evidence"] = evidence
        if subject.get("fixes"):
            entry["supportedFixes"] = subject["fixes"]
        self.diagnostics.append(entry)
        self.log("[%s] %s" % (code, message))
        return entry

    def artifact(self, path, kind, digest=None):
        self.artifacts.append(
            {
                "path": path,
                "sha256": digest if digest is not None else sha256_file(path),
                "kind": kind,
            }
        )

    # -- output -------------------------------------------------------------

    def log(self, message):
        if not self.quiet:
            sys.stderr.write("etch: %s\n" % message)

    def status(self):
        if not self.checks and not self.artifacts:
            return SKIPPED
        for entry in self.checks:
            if entry["required"] and entry["status"] in (FAILED, SKIPPED):
                return FAILED
        return PASSED

    def document(self):
        return {
            "schemaVersion": SCHEMA_VERSION,
            "toolVersion": self.tool_version,
            "status": self.status(),
            "checks": self.checks,
            "diagnostics": self.diagnostics,
            "artifacts": self.artifacts,
        }

    def emit(self):
        sys.stdout.write(json.dumps(self.document(), ensure_ascii=False, sort_keys=False))
        sys.stdout.write("\n")
        sys.stdout.flush()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def kind_of(path):
    return os.path.splitext(path)[1].lstrip(".").lower()
