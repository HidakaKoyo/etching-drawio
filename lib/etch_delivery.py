"""Generation staging, the current pointer, receipts, hash handoff and gc.

Normative text: contracts/delivery.md. The shape on disk is

    <output root>/
      generations/
        <id>.tmp/     built here, never read by anyone else
        <id>/         immutable once renamed
      current         -> generations/<id>

There is no lock. The only shared mutable things are the source .drawio and the
current pointer, and both are guarded by the hash handoff: a run that lost a
race fails its own comparison and stops with exit 3 (contracts/delivery.md §2.1).
"""

import json
import os
import shutil
import time

import etch_paths
from etch_report import UsageError, sha256_file


class Conflict(Exception):
    """The handoff comparison failed; nothing was published (exit 3)."""


class Delivery(object):
    def __init__(self, report, output_root):
        self.report = report
        self.root = ensure_output_root(output_root)
        self.generations = os.path.join(self.root, "generations")
        self.pointer = os.path.join(self.root, "current")
        self.staging = None

    # -- staging ------------------------------------------------------------

    def open_generation(self, digest):
        os.makedirs(self.generations, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        for attempt in range(100):
            suffix = "" if attempt == 0 else "-%02d" % attempt
            identifier = "%s-%s%s" % (stamp, digest[:8], suffix)
            staging = os.path.join(self.generations, identifier + ".tmp")
            final = os.path.join(self.generations, identifier)
            if os.path.exists(staging) or os.path.exists(final):
                continue
            os.mkdir(staging)
            self.identifier = identifier
            self.staging = staging
            self.final = final
            return staging
        raise UsageError("could not pick a free generation id under %s" % self.generations)

    def discard(self):
        """Reclaim our own .tmp generation. Other processes' .tmp are left alone."""
        if self.staging and os.path.isdir(self.staging):
            shutil.rmtree(self.staging, ignore_errors=True)
        self.staging = None

    def write_receipt(self, receipt):
        path = os.path.join(self.staging, "receipt.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")

    def commit_generation(self):
        os.rename(self.staging, self.final)
        self.staging = None
        return self.final

    # -- the pointer --------------------------------------------------------

    def commit_pointer(self):
        """Atomic replace, never unlink-then-create: that would open a window."""
        temporary = self.pointer + ".tmp.%d" % os.getpid()
        if os.path.islink(temporary) or os.path.exists(temporary):
            os.remove(temporary)
        os.symlink(os.path.join("generations", os.path.basename(self.final)), temporary)
        os.replace(temporary, self.pointer)

    def resolve_pointer(self):
        """Readers resolve the pointer once and then read a frozen directory."""
        if not os.path.islink(self.pointer) and not os.path.exists(self.pointer):
            return None
        target = os.path.realpath(self.pointer)
        return target if os.path.isdir(target) else None


def ensure_output_root(path):
    if not path:
        raise UsageError("--output-root is required for this subcommand")
    absolute = os.path.abspath(path)
    if not os.path.isdir(absolute):
        raise UsageError("the output root must be an existing directory: %s" % absolute)
    if not os.access(absolute, os.W_OK):
        raise UsageError("the output root is not writable: %s" % absolute)
    return absolute


def confirm_hash(report, path, expected, stage):
    """One half of the handoff. A mismatch means somebody else wrote the file."""
    actual = sha256_file(path) if os.path.isfile(path) else None
    if actual == expected:
        return
    report.failed("delivery/handoff")
    report.diagnostic(
        "delivery/hash-conflict",
        "%s does not carry the expected hash at the %s check, so nothing was published"
        % (path, stage),
        path,
        expected=expected,
        actual=actual,
    )
    raise Conflict()


def atomic_write(path, payload):
    temporary = "%s.tmp.%d" % (path, os.getpid())
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def build_receipt(
    identifier,
    tool_version,
    proposal_mode,
    source_path,
    source_digest,
    drawio,
    vendor_lock,
    artifacts,
    checks,
):
    return {
        "generation": identifier,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "toolVersion": tool_version,
        "proposalMode": proposal_mode,
        "source": {
            "path": source_path,
            "sha256": source_digest,
            "role": "proposal" if proposal_mode else "master",
        },
        "drawio": drawio,
        "vendorLock": vendor_lock,
        "artifacts": artifacts,
        "checks": checks,
    }


def vendor_lock_record(root_dir):
    path = etch_paths.bundled(root_dir, "vendor.lock")
    if path is None:
        return None
    return {"path": etch_paths.display_path(path, root_dir), "sha256": sha256_file(path)}


# ---------------------------------------------------------------------------
# gc
# ---------------------------------------------------------------------------


def collect(report, output_root, delete=False):
    """List completed generations that current does not point at.

    v1 never deletes on its own: without a reader lease the CLI cannot know
    that nobody is reading a generation, so removal stays a user decision.
    """
    delivery = Delivery(report, output_root)
    live = delivery.resolve_pointer()
    candidates = []
    if os.path.isdir(delivery.generations):
        for name in sorted(os.listdir(delivery.generations)):
            path = os.path.join(delivery.generations, name)
            if not os.path.isdir(path) or name.endswith(".tmp"):
                continue
            if live is not None and os.path.realpath(path) == live:
                continue
            candidates.append(path)

    for path in candidates:
        if delete:
            shutil.rmtree(path)
        report.diagnostic(
            "delivery/gc-candidate",
            "%s %s" % ("removed" if delete else "removable, kept (pass --delete to remove)", path),
            path,
            severity="warning",
        )
    report.passed("delivery/gc")
    return candidates
