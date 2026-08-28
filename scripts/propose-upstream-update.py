#!/usr/bin/env python3
"""Resolve the upstream closure at a commit and build a candidate snapshot.

Implements PLAN 4.2 steps 1-3 and the closure rules in
docs/closure-allowlist.md 2:

  1. resolve a candidate commit sha from a tracking ref (or take one directly)
  2. re-derive the dependency closure at that sha (URL extraction to a fixpoint)
  3. download the closure and write a candidate snapshot plus a candidate lock
  4. report the difference against the lock currently in the tree

Turning a candidate into a pull request is Phase 3a and is deliberately not
implemented here. --adopt is the Phase 0c bootstrap path: it copies an already
built candidate into place so the very first vendoring goes through the same
machinery that later updates will.

Network access is plain HTTPS to the GitHub REST API and raw.githubusercontent
for a public repo; no authentication is required. Set GITHUB_TOKEN to raise the
API rate limit.

Runs with python3 >= 3.9 and the standard library only, per
contracts/environment.md, and is callable from bash 3.2.

Usage:
  python3 scripts/propose-upstream-update.py [--ref main | --commit <sha>]
                                             [--check-docs] [--adopt] [-v]

Exit codes are repo tooling codes, not the etch CLI codes in
contracts/exit-codes.md:
  0  candidate is identical to the lock in the tree (nothing to propose)
  1  candidate differs, or a documented expectation was not met
  2  operational failure (network, missing path upstream, bad arguments)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "etching"
LOCK_PATH = SKILL_DIR / "vendor.lock"
SNAPSHOT_ROOT = "references/upstream"
CANDIDATE_ROOT = ROOT / ".vendor-candidate"

UPSTREAM_OWNER = "jgraph"
UPSTREAM_REPO = "drawio-mcp"
UPSTREAM_URL = "https://github.com/%s/%s" % (UPSTREAM_OWNER, UPSTREAM_REPO)
API = "https://api.github.com/repos/%s/%s" % (UPSTREAM_OWNER, UPSTREAM_REPO)
RAW = "https://raw.githubusercontent.com/%s/%s" % (UPSTREAM_OWNER, UPSTREAM_REPO)

# docs/closure-allowlist.md 1: the closure root, and the entry that is included
# for legal rather than technical reasons.
SEED_PATHS = ["plugins/claude-code/skills/drawio/SKILL.md"]
FIXED_PATHS = {
    "LICENSE": "Apache-2.0 4(a) redistribution requirement (PLAN 5)",
}
# docs/closure-allowlist.md 3: absent at the pinned sha, must be vendored if it
# ever appears.
WATCHED_PATHS = ["NOTICE"]

REF_PATTERN = re.compile(
    r"https://(?:raw\.githubusercontent\.com/%s/%s/(?P<ref1>[^/\s]+)/(?P<p1>[^\s)\]\"'>`]+)"
    r"|github\.com/%s/%s/blob/(?P<ref2>[^/\s]+)/(?P<p2>[^\s)\]\"'>`]+))"
    % (UPSTREAM_OWNER, UPSTREAM_REPO, UPSTREAM_OWNER, UPSTREAM_REPO)
)
TRAILING_PUNCTUATION = ".,;:!?"


class Failure(Exception):
    """An operational failure that should stop the run."""


def fetch(url, accept="application/vnd.github+json"):
    request = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": "etching-drawio-vendor-sync",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer %s" % token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise Failure("GET %s -> HTTP %s %s" % (url, exc.code, exc.reason))
    except urllib.error.URLError as exc:
        raise Failure("GET %s -> %s" % (url, exc.reason))


def fetch_json(url):
    try:
        return json.loads(fetch(url).decode("utf-8"))
    except ValueError as exc:
        raise Failure("GET %s -> response is not JSON: %s" % (url, exc))


def git_blob_sha1(data):
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def resolve_commit(ref):
    commit = fetch_json("%s/commits/%s" % (API, ref)).get("sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise Failure("could not resolve ref %r to a commit sha" % ref)
    return commit


def fetch_tree(commit):
    """Full recursive tree at commit, as {path: entry}."""
    payload = fetch_json("%s/git/trees/%s?recursive=1" % (API, commit))
    if payload.get("truncated"):
        raise Failure("upstream tree listing was truncated; cannot trust the closure")
    tree = {}
    for entry in payload.get("tree", []):
        tree[entry["path"]] = entry
    if not tree:
        raise Failure("upstream tree at %s is empty" % commit)
    return tree


def download(commit, path):
    return fetch("%s/%s/%s" % (RAW, commit, path), accept="application/vnd.github.raw")


def extract_references(text):
    """Upstream paths referenced by absolute URLs in one file's body.

    docs/closure-allowlist.md 2: the ref in the URL is ignored (upstream pins
    it to main); only the path matters, and it is always read at our own
    pinned sha. URLs pointing anywhere else are not part of the closure, which
    the host and repo name in the pattern already enforce.
    """
    found = set()
    for match in REF_PATTERN.finditer(text):
        path = match.group("p1") or match.group("p2")
        path = path.rstrip(TRAILING_PUNCTUATION).split("#")[0].split("?")[0]
        if path:
            found.add(path)
    return found


def resolve_closure(commit, tree, verbose):
    """Fixpoint over URL references, starting from the seeds."""
    reasons = {}
    for path in SEED_PATHS:
        reasons[path] = "closure root"
    pending = list(SEED_PATHS)
    bodies = {}
    round_number = 0

    while pending:
        round_number += 1
        added = []
        for path in sorted(pending):
            if path not in tree:
                raise Failure(
                    "closure path %r does not exist at %s (docs/closure-allowlist.md 2"
                    " makes a vanished path a failure, not a warning)" % (path, commit))
            if tree[path].get("type") != "blob":
                raise Failure("closure path %r is not a file upstream" % path)
            data = download(commit, path)
            actual = git_blob_sha1(data)
            if actual != tree[path]["sha"]:
                raise Failure("%s: downloaded blob %s but the tree says %s"
                              % (path, actual, tree[path]["sha"]))
            bodies[path] = data
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue  # binary file: no references to extract
            for referenced in sorted(extract_references(text)):
                if referenced not in reasons:
                    reasons[referenced] = "referenced by %s" % path
                    added.append(referenced)
        if verbose:
            print("  round %d: %s" % (round_number,
                                      ", ".join(sorted(added)) if added else "no additions"))
        pending = added

    for path, reason in FIXED_PATHS.items():
        if path not in reasons:
            if path not in tree:
                raise Failure("fixed closure entry %r is missing upstream" % path)
            reasons[path] = reason
            bodies[path] = download(commit, path)

    return reasons, bodies


def build_lock(commit, tree, reasons, bodies):
    files = []
    for path in sorted(reasons):
        data = bodies[path]
        mode = tree[path]["mode"]
        files.append({
            "path": path,
            "mode": mode,
            "symlinkTarget": data.decode("utf-8") if mode == "120000" else None,
            "size": len(data),
            "gitBlobSha1": git_blob_sha1(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "reason": reasons[path],
        })

    # Tree oids for the directories the closure lives in. docs/closure-allowlist
    # 1 treats these as an early warning signal, not as the pass/fail test.
    directories = sorted(set(
        str(Path(path).parent) for path in reasons if "/" in path
    ))
    trees = []
    for directory in directories:
        entry = tree.get(directory)
        if entry is None or entry.get("type") != "tree":
            raise Failure("no tree object upstream for directory %r" % directory)
        trees.append({"path": directory, "oid": entry["sha"]})

    return {
        "lockVersion": 1,
        "upstream": {
            "repo": UPSTREAM_URL,
            "commit": commit,
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "snapshotRoot": SNAPSHOT_ROOT,
        "trees": trees,
        "files": files,
    }


def write_candidate(directory, lock, bodies):
    if directory.exists():
        shutil.rmtree(directory)
    snapshot = directory / SNAPSHOT_ROOT
    for entry in lock["files"]:
        target = snapshot / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry["mode"] == "120000":
            os.symlink(entry["symlinkTarget"], target)
        else:
            target.write_bytes(bodies[entry["path"]])
            if entry["mode"] == "100755":
                target.chmod(0o755)
    (directory / "vendor.lock").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_current_lock():
    if not LOCK_PATH.is_file():
        return None
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Failure("the lock in the tree is not valid JSON: %s" % exc)


def report_diff(current, candidate):
    """Human-readable difference. Returns a list of change lines."""
    if current is None:
        return ["no vendor.lock in the tree yet: this candidate is the initial"
                " vendoring of %d file(s)" % len(candidate["files"])]

    changes = []
    if current["upstream"]["commit"] != candidate["upstream"]["commit"]:
        changes.append("commit %s -> %s" % (current["upstream"]["commit"][:12],
                                            candidate["upstream"]["commit"][:12]))
    old = dict((e["path"], e) for e in current["files"])
    new = dict((e["path"], e) for e in candidate["files"])
    for path in sorted(set(new) - set(old)):
        changes.append("added   %s (%s)" % (path, new[path]["reason"]))
    for path in sorted(set(old) - set(new)):
        changes.append("removed %s" % path)
    for path in sorted(set(old) & set(new)):
        if old[path]["sha256"] != new[path]["sha256"]:
            changes.append("changed %s (sha256 %s -> %s)"
                           % (path, old[path]["sha256"][:12], new[path]["sha256"][:12]))
        elif old[path]["mode"] != new[path]["mode"]:
            changes.append("changed %s (mode %s -> %s)"
                           % (path, old[path]["mode"], new[path]["mode"]))
    old_trees = dict((e["path"], e["oid"]) for e in current.get("trees", []))
    for entry in candidate["trees"]:
        if old_trees.get(entry["path"]) not in (None, entry["oid"]):
            changes.append("tree oid moved for %s (closure may have shifted:"
                           " %s -> %s)" % (entry["path"],
                                           old_trees[entry["path"]][:12],
                                           entry["oid"][:12]))
    return changes


# --------------------------------------------------------------------------
# cross-check against the Phase 0a documents
# --------------------------------------------------------------------------

ELLIPSIS = "…"


def parse_markdown_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        rows.append([c.strip("`") for c in cells])
    return rows


def check_docs(candidate):
    """Machine-compare the candidate against the Phase 0a ledger documents."""
    problems = []
    by_path = dict((e["path"], e) for e in candidate["files"])

    allowlist = ROOT / "docs" / "closure-allowlist.md"
    expected = {}
    for cells in parse_markdown_rows(allowlist):
        # | # | path | mode | blob sha | size | sha256 | reason |
        if len(cells) >= 6 and cells[0].isdigit() and len(cells[5]) == 64:
            expected[cells[1]] = {
                "mode": cells[2], "gitBlobSha1": cells[3],
                "size": int(cells[4]), "sha256": cells[5],
            }
    if not expected:
        problems.append("could not parse any closure row out of %s" % allowlist.name)

    for path in sorted(set(expected) - set(by_path)):
        problems.append("%s: in closure-allowlist.md but not in the candidate closure" % path)
    for path in sorted(set(by_path) - set(expected)):
        problems.append("%s: in the candidate closure but not in closure-allowlist.md" % path)
    for path in sorted(set(expected) & set(by_path)):
        for field in ("mode", "gitBlobSha1", "size", "sha256"):
            if by_path[path][field] != expected[path][field]:
                problems.append("%s: %s is %r, closure-allowlist.md says %r"
                                % (path, field, by_path[path][field], expected[path][field]))

    ledger = ROOT / "docs" / "license-ledger.md"
    ledger_rows = 0
    for cells in parse_markdown_rows(ledger):
        # | # | path | sha256 (abbreviated) | last-changed commit | verdict |
        if len(cells) >= 3 and cells[0].isdigit() and ELLIPSIS in cells[2]:
            ledger_rows += 1
            path, abbreviated = cells[1], cells[2]
            head, tail = abbreviated.split(ELLIPSIS, 1)
            entry = by_path.get(path)
            if entry is None:
                problems.append("%s: in license-ledger.md but not in the candidate closure" % path)
            elif not (entry["sha256"].startswith(head) and entry["sha256"].endswith(tail)):
                problems.append("%s: sha256 %s does not match license-ledger.md %s"
                                % (path, entry["sha256"], abbreviated))
    if ledger_rows != len(by_path):
        problems.append("license-ledger.md lists %d closure file(s), the candidate has %d"
                        % (ledger_rows, len(by_path)))
    return problems


def adopt(candidate_dir):
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    destination = SKILL_DIR / SNAPSHOT_ROOT
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(candidate_dir / SNAPSHOT_ROOT, destination, symlinks=True)
    shutil.copyfile(candidate_dir / "vendor.lock", LOCK_PATH)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ref", help="tracking ref to resolve (default: main)")
    group.add_argument("--commit", help="use this commit sha verbatim")
    parser.add_argument("--check-docs", action="store_true",
                        help="cross-check the candidate against docs/closure-allowlist.md"
                             " and docs/license-ledger.md")
    parser.add_argument("--adopt", action="store_true",
                        help="copy the candidate into skills/etching/ (Phase 0c bootstrap;"
                             " PR creation is Phase 3a)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    try:
        if args.commit:
            if len(args.commit) != 40:
                raise Failure("--commit needs a full 40-character sha")
            commit = resolve_commit(args.commit)
            if commit != args.commit:
                raise Failure("upstream resolved %s to %s" % (args.commit, commit))
        else:
            commit = resolve_commit(args.ref or "main")

        print("== candidate %s @ %s" % (UPSTREAM_URL, commit))
        tree = fetch_tree(commit)
        reasons, bodies = resolve_closure(commit, tree, args.verbose)
        candidate = build_lock(commit, tree, reasons, bodies)
        print("  closure: %d file(s)" % len(candidate["files"]))
        for entry in candidate["files"]:
            print("    %s  %s" % (entry["sha256"][:12], entry["path"]))

        for path in WATCHED_PATHS:
            state = "present -- must be vendored" if path in tree else "absent (as expected)"
            print("  watched: %s %s" % (path, state))

        candidate_dir = CANDIDATE_ROOT / commit
        write_candidate(candidate_dir, candidate, bodies)
        print("  candidate written to %s" % candidate_dir.relative_to(ROOT))

        current = load_current_lock()
        changes = report_diff(current, candidate)
        doc_problems = check_docs(candidate) if args.check_docs else []

        if args.check_docs:
            if doc_problems:
                print("\n== documented expectations")
                for problem in doc_problems:
                    print("  FAIL %s" % problem)
            else:
                print("  docs: candidate matches closure-allowlist.md and license-ledger.md")

        if any(path in tree for path in WATCHED_PATHS):
            changes.append("a watched path appeared upstream and is not in the closure yet")

        if changes:
            print("\n== proposed changes")
            for change in changes:
                print("  %s" % change)
        else:
            print("\nOK: the candidate matches the lock in the tree; nothing to propose")

        if args.adopt:
            if doc_problems:
                raise Failure("refusing to adopt a candidate that fails --check-docs")
            adopt(candidate_dir)
            print("\nadopted into %s" % SKILL_DIR.relative_to(ROOT))
            print("run scripts/verify-vendor.py to confirm")
            return 0  # the proposed changes are now in the tree

        return 1 if (changes or doc_problems) else 0
    except Failure as exc:
        print("FAILED: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
