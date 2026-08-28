"""Where the bundled skill files live, whatever layout etch was installed in.

Two layouts ship (docs/PLAN.md §9):

  plugin / repo   <root>/bin/etch, <root>/lib/, <root>/skills/etching/
  standalone      <skill>/bin/etch, <skill>/lib/, <skill>/references/

The difference is only whether the CLI sits beside the skill directory or
inside it, so instead of hard-coding one shape the lookup walks a short list of
candidate skill directories and takes the first that actually holds the
snapshot. Nothing outside the install root is ever consulted: a missing file is
reported as missing rather than searched for elsewhere.

`ETCH_ROOT` (set by bin/etch, overridable by the caller) names the install root
and is the escape hatch when neither layout applies.
"""

import os

# Present in every skill directory and in no other directory of either layout,
# so it is what tells a candidate apart from its parent.
MARKER = os.path.join("references", "upstream")


def default_root():
    """The install root, as the bash entry point would compute it."""
    return os.environ.get(
        "ETCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def skill_dir(root_dir=None):
    """The bundled skill directory, or None when this install has no snapshot.

    A CLI installed without its snapshot is a supported (if reduced) install:
    validation that needs the bundled XSD degrades to an optional skipped
    check rather than an error.
    """
    root = root_dir or default_root()
    for candidate in (os.path.join(root, "skills", "etching"), root):
        if os.path.isdir(os.path.join(candidate, MARKER)):
            return candidate
    return None


def bundled(root_dir, *parts):
    """Path to a file inside the bundled skill directory, or None."""
    found = skill_dir(root_dir)
    if found is None:
        return None
    path = os.path.join(found, *parts)
    return path if os.path.isfile(path) else None


def display_path(path, root_dir):
    """A path to put in a receipt: relative to the install root where it is
    under it, absolute where it is not."""
    relative = os.path.relpath(path, root_dir)
    return path if relative.startswith(os.pardir) else relative
