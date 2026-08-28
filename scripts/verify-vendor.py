#!/usr/bin/env python3
"""Verify the vendored upstream snapshot against vendor.lock.

Fail-closed: any difference between the lock and the files on disk is an
error, because the snapshot is supposed to be a pristine copy of a pinned
upstream commit. A difference means either tampering or a hand edit, and
both are things PLAN 4.2 says must stop the build rather than be repaired.

Runs with python3 >= 3.9 and the standard library only, per
contracts/environment.md, and is callable from bash 3.2.

Usage: python3 scripts/verify-vendor.py [--lock <path>] [-v]

Exit codes are repo tooling codes, not the etch CLI codes in
contracts/exit-codes.md:
  0  lock and snapshot agree
  1  they disagree (details on stdout)
  2  the lock itself is unusable (missing, unparsable, malformed)
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / "skills" / "etching" / "vendor.lock"

LOCK_VERSION = 1
FILE_MODES = {"100644", "100755", "120000"}


class LockError(Exception):
    """The lock file cannot be trusted enough to verify anything against."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data):
    """Git's object id for a blob: sha1 over 'blob <len>\\0' + content."""
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(
        c in "0123456789abcdef" for c in value
    )


def load_lock(path):
    if not path.is_file():
        raise LockError("lock file not found: %s" % path)
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise LockError("lock file is not valid JSON: %s" % exc)
    if not isinstance(lock, dict):
        raise LockError("lock file must contain a JSON object")
    if lock.get("lockVersion") != LOCK_VERSION:
        raise LockError("unsupported lockVersion %r (this tool reads %d)"
                        % (lock.get("lockVersion"), LOCK_VERSION))

    upstream = lock.get("upstream")
    if not isinstance(upstream, dict):
        raise LockError("missing 'upstream' object")
    for key in ("repo", "commit", "fetchedAt"):
        if not isinstance(upstream.get(key), str) or not upstream[key]:
            raise LockError("upstream.%s must be a non-empty string" % key)
    if not is_hex(upstream["commit"], 40):
        raise LockError("upstream.commit must be a full 40-hex commit sha")

    if not isinstance(lock.get("snapshotRoot"), str) or not lock["snapshotRoot"]:
        raise LockError("missing 'snapshotRoot'")

    files = lock.get("files")
    if not isinstance(files, list) or not files:
        raise LockError("'files' must be a non-empty array")

    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise LockError("every 'files' entry must be an object")
        path_value = entry.get("path")
        check_snapshot_path(path_value)
        if path_value in seen:
            raise LockError("duplicate path in lock: %s" % path_value)
        seen.add(path_value)
        if entry.get("mode") not in FILE_MODES:
            raise LockError("%s: mode must be one of %s"
                            % (path_value, sorted(FILE_MODES)))
        if not is_hex(entry.get("sha256"), 64):
            raise LockError("%s: sha256 must be 64 hex chars" % path_value)
        if not is_hex(entry.get("gitBlobSha1"), 40):
            raise LockError("%s: gitBlobSha1 must be 40 hex chars" % path_value)
        size = entry.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise LockError("%s: size must be a non-negative integer" % path_value)
        target = entry.get("symlinkTarget")
        if entry["mode"] == "120000":
            if not isinstance(target, str) or not target:
                raise LockError("%s: symlink entry needs symlinkTarget" % path_value)
        elif target is not None:
            raise LockError("%s: symlinkTarget must be null for a regular file"
                            % path_value)

    trees = lock.get("trees", [])
    if not isinstance(trees, list):
        raise LockError("'trees' must be an array")
    for entry in trees:
        if not isinstance(entry, dict) or not is_hex(entry.get("oid"), 40):
            raise LockError("every 'trees' entry needs a 40-hex oid")

    return lock


def check_snapshot_path(value):
    """Reject anything that could resolve outside the snapshot directory."""
    if not isinstance(value, str) or not value:
        raise LockError("every 'files' entry needs a non-empty path")
    if value.startswith("/") or ":" in value or "\\" in value:
        raise LockError("path must be repo-relative and slash-separated: %r" % value)
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise LockError("path must not contain empty or dot segments: %r" % value)


def read_entry(base, entry):
    """Return (data, kind) for one snapshot entry, or raise OSError."""
    target = base / entry["path"]
    if entry["mode"] == "120000":
        return os.readlink(target).encode("utf-8"), "symlink"
    if target.is_symlink():
        raise OSError("expected a regular file but found a symlink")
    return target.read_bytes(), "file"


def walk_snapshot(base):
    """Every file and symlink under base, as snapshot-relative posix paths."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(base):
        here = Path(dirpath)
        # os.walk does not descend into symlinked dirs by default, but it does
        # list them in dirnames; treat them as entries so they cannot hide.
        for name in list(dirnames):
            if (here / name).is_symlink():
                dirnames.remove(name)
                found.add((here / name).relative_to(base).as_posix())
        for name in filenames:
            found.add((here / name).relative_to(base).as_posix())
    return found


def verify(lock, lock_path, verbose):
    base = (lock_path.parent / lock["snapshotRoot"]).resolve()
    problems = []

    if not base.is_dir():
        return ["snapshot directory is missing: %s" % base]

    for entry in sorted(lock["files"], key=lambda e: e["path"]):
        rel = entry["path"]
        try:
            data, kind = read_entry(base, entry)
        except OSError as exc:
            problems.append("%s: cannot read (%s)" % (rel, exc))
            continue

        if kind == "symlink" and os.readlink(base / rel) != entry["symlinkTarget"]:
            problems.append("%s: symlink target %r, lock says %r"
                            % (rel, os.readlink(base / rel), entry["symlinkTarget"]))
        if kind == "file":
            mode = "100755" if os.access(base / rel, os.X_OK) else "100644"
            if mode != entry["mode"]:
                problems.append("%s: mode %s, lock says %s" % (rel, mode, entry["mode"]))

        local = []
        if len(data) != entry["size"]:
            local.append("size %d, lock says %d" % (len(data), entry["size"]))
        actual_sha256 = sha256_bytes(data)
        if actual_sha256 != entry["sha256"]:
            local.append("sha256 %s, lock says %s" % (actual_sha256, entry["sha256"]))
        actual_blob = git_blob_sha1(data)
        if actual_blob != entry["gitBlobSha1"]:
            local.append("git blob %s, lock says %s" % (actual_blob, entry["gitBlobSha1"]))
        for detail in local:
            problems.append("%s: %s" % (rel, detail))
        if not local and verbose:
            print("  ok   %s" % rel)

    locked = set(e["path"] for e in lock["files"])
    for extra in sorted(walk_snapshot(base) - locked):
        problems.append("%s: present in the snapshot but not in the lock" % extra)

    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lock", default=str(DEFAULT_LOCK), type=Path,
                        help="path to vendor.lock (default: %s)"
                             % DEFAULT_LOCK.relative_to(ROOT))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    lock_path = args.lock.resolve()
    try:
        lock = load_lock(lock_path)
    except LockError as exc:
        print("vendor.lock unusable: %s" % exc, file=sys.stderr)
        return 2

    print("== vendor snapshot (%s @ %s)"
          % (lock["upstream"]["repo"], lock["upstream"]["commit"][:12]))
    problems = verify(lock, lock_path, args.verbose)

    if problems:
        print("  %d file(s) locked, %d problem(s):" % (len(lock["files"]), len(problems)))
        for problem in problems:
            print("  FAIL %s" % problem)
        print("\nFAILED: the snapshot does not match vendor.lock.")
        print("The snapshot is pristine vendored code; restore it from the pinned"
              " commit rather than updating the lock to match a local edit.")
        return 1

    print("  %d file(s) match the lock" % len(lock["files"]))
    print("\nOK: snapshot matches vendor.lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
