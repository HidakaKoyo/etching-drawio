# Third-party notices

`etching-drawio` redistributes files from one third-party project. This file
lists them, where they came from, and what was changed. It is generated from
`docs/license-ledger.md` and kept in step with `skills/etching/vendor.lock`;
`scripts/verify-vendor.py` is what proves the shipped files still match.

Last re-verified against the pinned commit on 2026-08-28 (the release-candidate
license gate): all six files fetched from the pinned commit hash to the values
below, upstream still has no `NOTICE`, and none of the six carries a per-file
license header. Nothing here is of unknown provenance.

The authoritative, machine-readable record is `skills/etching/vendor.lock`
(pinned commit, per-file SHA-256, git blob id, git mode, tree oids). This
document is the human-readable view of the same facts.

## drawio-mcp

| | |
|---|---|
| Component | drawio-mcp (draw.io Claude Code skill and its shared references) |
| Source | https://github.com/jgraph/drawio-mcp |
| Commit | `14b318b19cc37b159f841227b9d11fbd18ce18ea` |
| Upstream plugin version | 1.1.0 (`plugins/claude-code/.claude-plugin/plugin.json`) |
| License | Apache License 2.0 |
| Copyright | Copyright 2025 JGraph Ltd |
| Vendored at | `skills/etching/references/upstream/` |
| Modifications | **None.** Every file is byte-identical to the upstream commit above |

The upstream license text ships with the snapshot at
`skills/etching/references/upstream/LICENSE`, satisfying Apache-2.0 section
4(a). Upstream has no `NOTICE` file at this commit, so section 4(d) does not
apply; `scripts/propose-upstream-update.py` watches for one appearing.

Because the files are unmodified, Apache-2.0 section 4(b) — the requirement to
carry prominent notices of change — has nothing to attach to. Where upstream
files link to other upstream files by absolute URL, `etching` resolves those
links through a reference-resolution table in its own `SKILL.md` rather than by
rewriting the vendored text.

### Files

Paths are relative to `skills/etching/references/upstream/` and mirror the
upstream repository layout.

| Upstream path | SHA-256 | Why it is included |
|---|---|---|
| `plugins/claude-code/skills/drawio/SKILL.md` | `4db0d9428e855b602b5afd161929dc6e35cb28678d830cfafd939f0a71bba5f5` | Closure root: the skill `etching` imports |
| `shared/xml-reference.md` | `3f7409f925ba35115ef7b644279c44b34f9fbf5b8ab539844368855db113d8aa` | Referenced by `SKILL.md` |
| `shared/mermaid-reference.md` | `977a11dd6c0e37922eb3615f50f41c0b8f2eeb732dc6905b1b8546ca829cbbf0` | Referenced by `SKILL.md` |
| `shared/style-reference.md` | `094df96981f85adb3124f40fd5ef02dc02eade1615ed6ffe4631f0e123a6366d` | Referenced by `shared/xml-reference.md` |
| `shared/mxfile.xsd` | `905db85d4e8ebec0e91518cdd62982e0afb3f09ebdcaf9e6b1952957a606639a` | Referenced by `shared/xml-reference.md` and `shared/style-reference.md` |
| `LICENSE` | `006e61a1b8c97620d75ceacc283de7a363d78da7da9a5b92203324c40feb7232` | Apache-2.0 section 4(a) |

The closure was derived by following absolute upstream URLs to a fixpoint; the
rules and the exclusions are recorded in `docs/closure-allowlist.md`.

### Note on `shared/style-reference.md`

That file states that its data was extracted from the draw.io source code, so
it is a second-order derivative of `jgraph/drawio`. It is redistributed here
under the `drawio-mcp` repository license, which covers it. `jgraph/drawio` was
checked directly and is Apache-2.0 as well, with the same copyright holder
(JGraph Ltd), so no additional obligation follows from the derivation.

## Everything else

All other files in this repository are original work under this project's own
license, MIT, in the root `LICENSE` file. That license does not cover
`skills/etching/references/upstream/`, which is governed by Apache-2.0 as
described above.
