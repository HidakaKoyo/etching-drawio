# Changelog

Hand-written. Versions are the plugin version in `.claude-plugin/plugin.json`;
`skills/etching/VERSION` is a generated copy of it and the diagnostics
`schemaVersion` moves independently (README, "Versioning").

## 0.1.0 — 2026-08-28

First release. Everything below is new.

### The skill

- `skills/etching` — a single entry point for diagram work: draft, validate,
  repair, deliver. It carries an unmodified snapshot of the upstream draw.io
  authoring references and resolves the absolute URLs in them to the bundled
  copies, so nothing is fetched at run time.
- Five documented overrides of the upstream skill, the load-bearing one being
  that the `.drawio` source is the master and SVG/PNG/PDF are derived: an
  export never deletes its own source.

### The CLI

- `etch validate | export | deliver | verify | gc`. stdout carries the
  diagnostics document of `contracts/diagnostics.schema.json` and nothing else;
  human-readable lines go to stderr.
- Exit codes are a contract (`contracts/exit-codes.md`): 0 passed or skipped,
  1 validation, 2 export or output verification, 3 hash conflict, 4 usage,
  5 missing dependency, 6 internal error, 130 signal.
- Delivery is a staged generation directory plus a `current` pointer and a
  receipt, committed by rename (`contracts/delivery.md`). A hash handoff around
  the source and the pointer turns a concurrent write into exit 3 rather than a
  silent overwrite. `proposal_mode` leaves the master untouched entirely.
- Input safety: DTDs and external entities refused, compressed payloads
  refused rather than silently inflated, size/node/depth limits, and external
  `http`/`file` references in styles reported under `security/*`.
- Output verification without external tools: full PNG chunk walk with CRC
  checks and an IDAT inflate, SVG well-formedness, PDF magic. `xmllint` and
  `file` are used when present and skipped as optional checks when not.

### Distribution and supply chain

- Claude Code plugin manifest and single-plugin marketplace manifest;
  `scripts/build-release.py --bundle` writes the standalone skill bundle.
- `skills/etching/vendor.lock` pins the upstream commit with per-file SHA-256,
  git blob ids and tree oids. `scripts/verify-vendor.py` fails the build on any
  difference; `scripts/propose-upstream-update.py` re-derives the closure at a
  candidate commit and runs weekly in CI, opening an issue when upstream moves.
- `THIRD_PARTY_NOTICES.md` and `docs/license-ledger.md` record every vendored
  file's provenance. Zero unknowns is a release gate.

### Verification

- CI on ubuntu-latest and macos-latest: contract fixtures, vendor snapshot,
  characterization suites, ShellCheck, a real draw.io Desktop export smoke test
  against a pinned 31.3.2, and an acceptance suite that installs both
  distribution layouts into clean directories and runs the whole loop.
