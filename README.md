# etching-drawio — a validated draw.io authoring loop for agents

Diagrams an agent can be held to: drafted, validated, repaired, and delivered
with a receipt.

A Claude Code plugin — one Agent Skill plus a small CLI, no MCP server — that
replaces "the model wrote some XML and ran `drawio -x`" with a loop that has a
contract at every step. The `.drawio` file is the master and SVG/PNG/PDF are
derived from it; a delivery is a staged directory and a `current` pointer, so a
half-written export is never something a reader can pick up.

Nothing is fetched at run time. The draw.io authoring references the skill
reads are vendored, pinned by commit SHA, and verified on every build.

## Why

An agent asked for a diagram will produce XML that looks plausible, export it,
and report success. The failures are the quiet ones: an edge pointing at an id
that no longer exists, a compressed payload silently rewritten, an export that
deletes the source it came from, a second agent overwriting the first one's
file mid-run.

So the checks are machine-readable and the delivery is atomic:

- **Validation emits JSON, not prose.** Each diagnostic carries a `code`, the
  `subject` that locates the problem, and the fixes that apply to it, so the
  repair loop is driven by data rather than by re-reading an error message.
- **The repair loop has to terminate.** A state fingerprint detects a cycle and
  five fix sets is the ceiling. It stops and reports rather than looping.
- **The master is never a work in progress.** Repairs happen on a work copy;
  the master is replaced once, at the end, and only if its hash is still the
  one the run started from. A lost race is exit 3, not an overwrite.
- **A delivery leaves evidence.** The receipt records the source hash, the
  artifacts and their hashes, the draw.io Desktop version, the vendor lock, and
  every check that ran.

## Requirements

- macOS or Ubuntu LTS (other Linux is best effort; Windows via WSL)
- bash 3.2 or newer
- python3 3.9 or newer — standard library only, no `pip`, no `uv`
- [draw.io Desktop](https://github.com/jgraph/drawio-desktop/releases), for the
  subcommands that export. Validation and drafting work without it.

`xmllint` and `file` are used when present and skipped as optional checks when
not. The full declaration is `contracts/environment.md`.

## Install

As a Claude Code plugin:

```
/plugin marketplace add HidakaKoyo/etching-drawio
/plugin install etching-drawio@etching-drawio
```

The skill is then `/etching-drawio:etching`, and it also triggers on its own
when you ask for a diagram.

As a standalone skill directory, for a host that installs skills rather than
plugins:

```
python3 scripts/build-release.py --bundle <destination>
```

That writes `<destination>/etching` with the CLI inside it. Point `ETCH_CMD` at
`<destination>/etching/bin/etch`, or put it on `PATH`. Both layouts are
installed into clean directories and driven end to end by
`tests/acceptance/test_distribution.py` on every CI run.

## Usage

Ask for a diagram in normal language — "draw the ingest pipeline as a
flowchart", "fix the arrows in `architecture.drawio`", "export that to SVG" —
and the skill runs the loop. What comes back names the checks that ran and the
artifacts that were written, including the warnings it did not stop for.

The CLI underneath is usable directly:

```
etch validate [--page N] [--allow-external] [--profile P] <input.drawio>
etch export   --format svg|png|pdf --output-root DIR [options] <input.drawio>
etch deliver  --format svg|png|pdf --output-root DIR [options] <input.drawio>
etch verify   --output-root DIR
etch gc       --output-root DIR [--delete]
```

`export` builds a finished generation and leaves the `current` pointer alone;
`deliver` also commits the pointer. stdout always carries the diagnostics JSON
of `contracts/diagnostics.schema.json` and nothing else; every human-readable
line goes to stderr.

Exit codes are a contract (`contracts/exit-codes.md`):

| code | meaning |
|---|---|
| 0 | passed, or nothing to do — `status` tells the two apart |
| 1 | validation failed |
| 2 | export or output verification failed |
| 3 | hash conflict: someone else wrote the file |
| 4 | usage or profile error (no JSON) |
| 5 | a required dependency is missing |
| 6 | internal error |
| 130 | interrupted (no JSON) |

### Host conventions

A project can put an `.etching/profile.json` in its root to set
`proposal_mode`, and an `.etching/profile.md` beside it for conventions the
agent should follow: where artifacts belong, how diagrams get embedded, which
export options are off limits there. The profile is read from the current
directory only — never searched for up the tree — so run `etch` from the
directory that owns it, or pass `--profile`.

In `proposal_mode` a delivery writes `<name>.agent-proposal.drawio` and moves
no pointer: the master is left for a human to reconcile.

## Safety boundary

What the tool will not do, by design:

- **It does not silently rewrite your input.** A compressed diagram payload is
  rejected with a diagnostic rather than inflated behind your back.
- **It does not resolve external XML.** DTDs and external entities are refused
  before parsing (XXE), and byte, node-count and depth limits are enforced.
- **It does not fetch anything.** No network access at run time, in the CLI or
  in the skill. `http`/`file` URLs found inside styles are reported under
  `security/*`, and `--embed-xml` — which can carry hidden layers into a shared
  SVG — stays off unless you ask for it.
- **It does not delete your work.** Old generations go only when you run
  `etch gc --delete`, and an export never removes its own source.
- **It does not overwrite a file that changed under it.** The hash handoff
  fails the run instead.

Protection against concurrent writers holds between cooperating writers.
draw.io Desktop does not go through the handoff, so a human editing the same
file at the same moment is *detected* — `etch verify` compares the receipt
against the file on disk — rather than prevented. `proposal_mode` is the answer
where that is likely. The threat model and what is deliberately out of scope
are in [`docs/security.md`](docs/security.md).

## Scope

This is a diagram loop for draw.io, and it intends to stay one.

Not planned: an MCP server, other diagram backends, rendering-level geometry
checks (edge crossings, label overlap — the `composition/*` diagnostic
namespace is reserved but empty), and anything that edits a diagram without
being asked. If one of those turns out to be needed, the case for it goes in
first: an unused feature is a maintenance cost with no reader.

## Upstream

`skills/etching/references/upstream/` is an unmodified snapshot of the draw.io
authoring references from [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp),
pinned in `skills/etching/vendor.lock` with per-file hashes.
`scripts/verify-vendor.py` fails the build on any difference, and a weekly CI
job re-derives the closure at upstream `main` and opens an issue when it moves.
Provenance and licensing are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

The snapshot is verbatim, so where its text conflicts with this project the
skill states the override in its own words rather than editing the vendored
file.

## Versioning

| thing | rule |
|---|---|
| `.claude-plugin/plugin.json` version | the source of truth, edited by hand |
| `.claude-plugin/marketplace.json`, `skills/etching/VERSION` | generated copies; `scripts/build-release.py --check` fails the build when they drift |
| git tag | `v<plugin version>`, one to one |
| diagnostics `schemaVersion` | independent: additive change is a minor, a removal or a change of meaning is a major |
| a vendor-only update | a patch bump of the plugin version |

## Development

```
python3 scripts/build-release.py --check                                 # version copies agree
python3 scripts/validate-contracts.py                                    # schemas against fixtures
python3 scripts/verify-vendor.py                                         # snapshot against vendor.lock
ETCH_CLI=$PWD/bin/etch python3 tests/characterization/test_invariants.py # invariants
ETCH_CLI=$PWD/bin/etch python3 tests/characterization/test_migration.py  # deliberate changes
python3 tests/acceptance/test_distribution.py                            # both install layouts
python3 tests/smoke/test_real_export.py                                  # real draw.io export
```

Every case runs in its own temporary directory and, where draw.io is not the
thing under test, against a stub — so only the smoke suite needs an install.
CI runs all of it on ubuntu-latest and macos-latest.

The design record is `docs/PLAN.md`; the contracts the code answers to are in
`contracts/`.

## License

MIT, except `skills/etching/references/upstream/`, which is redistributed under
the Apache License 2.0. See [`LICENSE`](LICENSE) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
