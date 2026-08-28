"""Host profile resolution (contracts/profile.md).

Resolution stops at the first hit: --profile, then ETCHING_PROFILE, then
./.etching/profile.json, then nothing. No parent-directory search and no
guessing at a vault location. Every problem with a profile we decided to read
is fatal: falling back to defaults would silently turn proposal mode off.
"""

import json
import os

from etch_report import UsageError

ALLOWED_KEYS = {"version", "proposal_mode"}
DEFAULT = {"version": 1, "proposal_mode": False}


def resolve(explicit=None):
    path, required = _select(explicit)
    if path is None:
        return dict(DEFAULT), None
    if not os.path.isfile(path):
        if required:
            raise UsageError("the profile %s does not exist" % path)
        return dict(DEFAULT), None
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as error:
        raise UsageError("the profile %s could not be read: %s" % (path, error))
    return _validate(document, path), path


def _select(explicit):
    if explicit:
        return explicit, True
    from_environment = os.environ.get("ETCHING_PROFILE")
    if from_environment:
        return from_environment, True
    return os.path.join(os.getcwd(), ".etching", "profile.json"), False


def _validate(document, path):
    if not isinstance(document, dict):
        raise UsageError("the profile %s is not a JSON object" % path)
    unknown = sorted(set(document) - ALLOWED_KEYS)
    if unknown:
        raise UsageError("the profile %s has unknown key(s): %s" % (path, ", ".join(unknown)))
    if document.get("version") != 1:
        raise UsageError("the profile %s must declare \"version\": 1" % path)
    proposal = document.get("proposal_mode", False)
    if not isinstance(proposal, bool):
        raise UsageError("the profile %s has a non-boolean proposal_mode" % path)
    return {"version": 1, "proposal_mode": proposal}
