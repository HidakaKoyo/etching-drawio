#!/usr/bin/env python3
"""Release build: propagate the version, and assemble the standalone bundle.

The version is edited in one place, `.claude-plugin/plugin.json`
(docs/PLAN.md §9). Everything else carries a generated copy:

  .claude-plugin/marketplace.json   the marketplace entry
  skills/etching/VERSION            read at runtime as the tool version, so
                                    that a skill distributed on its own still
                                    knows what it is
  CHANGELOG.md                      must have a section for the version

`--check` verifies those agree without writing anything; that is what CI runs,
so a hand-edited copy fails the build instead of shipping.

`--bundle <dir>` writes the standalone distribution: the skill directory with
the CLI inside it, which is the layout `lib/etch_paths.py` supports as well as
the plugin layout. The acceptance suite installs from here rather than
re-deriving what a distribution contains.

Runs with python3 >= 3.9 and the standard library only
(contracts/environment.md), and is callable from bash 3.2.

Exit codes are repo tooling codes, not the etch CLI codes in
contracts/exit-codes.md:
  0  the copies agree (or were written)
  1  they disagree
  2  an input is missing or unusable
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_MANIFEST = ROOT / ".claude-plugin" / "marketplace.json"
SKILL_DIR = ROOT / "skills" / "etching"
VERSION_FILE = SKILL_DIR / "VERSION"
CHANGELOG = ROOT / "CHANGELOG.md"

# What the standalone bundle contains: the skill itself, plus the CLI moved
# inside it so the closure has no siblings to depend on.
BUNDLE_EXTRAS = ("bin", "lib")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class BuildError(Exception):
    """An input could not be read or is not shaped as expected."""


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BuildError("not found: %s" % path)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BuildError("%s is not valid JSON: %s" % (path, exc))


def source_version():
    manifest = read_json(PLUGIN_MANIFEST)
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.match(version):
        raise BuildError(
            "plugin.json version must be a semver string, got %r" % (version,)
        )
    return version


def marketplace_version():
    manifest = read_json(MARKETPLACE_MANIFEST)
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise BuildError("marketplace.json must list exactly one plugin")
    return plugins[0].get("version")


def version_file_value():
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise BuildError("%s is not readable as UTF-8: %s" % (VERSION_FILE, exc))


def changelog_versions():
    try:
        text = CHANGELOG.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BuildError("not found: %s" % CHANGELOG)
    return re.findall(r"^## \[?(\d+\.\d+\.\d+)\]?", text, re.MULTILINE)


def check(verbose=False):
    version = source_version()
    problems = []

    found = marketplace_version()
    if found != version:
        problems.append(
            "marketplace.json says %r, plugin.json says %r" % (found, version)
        )

    found = version_file_value()
    if found != version:
        problems.append(
            "skills/etching/VERSION says %r, plugin.json says %r "
            "(run scripts/build-release.py)" % (found, version)
        )

    versions = changelog_versions()
    if version not in versions:
        problems.append("CHANGELOG.md has no section for %s" % version)
    elif versions[0] != version:
        problems.append(
            "CHANGELOG.md leads with %s, not the current %s" % (versions[0], version)
        )

    if problems:
        print("== release consistency: FAILED")
        for problem in problems:
            print("  - %s" % problem)
        return 1
    print("== release consistency: %s everywhere" % version)
    if verbose:
        print("   plugin.json, marketplace.json, skills/etching/VERSION, CHANGELOG.md")
    return 0


def write(verbose=False):
    version = source_version()
    previous = version_file_value()
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    if verbose or previous != version:
        print("== skills/etching/VERSION: %s -> %s" % (previous, version))
    return check(verbose=verbose)


def bundle(destination, verbose=False):
    """Write the standalone skill bundle into <destination>/etching."""
    version = source_version()
    target = Path(destination) / "etching"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        SKILL_DIR, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    for name in BUNDLE_EXTRAS:
        shutil.copytree(
            ROOT / name,
            target / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / name, target / name)
    (target / "VERSION").write_text(version + "\n", encoding="utf-8")
    if verbose:
        print("== bundle %s written to %s" % (version, target))
    else:
        print(str(target))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the copies without writing"
    )
    parser.add_argument(
        "--bundle", metavar="DIR", help="write the standalone skill bundle into DIR"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    arguments = parser.parse_args()

    try:
        if arguments.bundle:
            return bundle(arguments.bundle, verbose=arguments.verbose)
        if arguments.check:
            return check(verbose=arguments.verbose)
        return write(verbose=arguments.verbose)
    except BuildError as error:
        sys.stderr.write("build-release: %s\n" % error)
        return 2


if __name__ == "__main__":
    sys.exit(main())
