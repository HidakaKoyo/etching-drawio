etching-drawio — validated draw.io authoring loop for AI agents.
Work in progress; see docs/PLAN.md.
Private until v0.1.0.

## etch CLI

```
bin/etch validate [--page N] [--allow-external] [--profile P] <input.drawio>
bin/etch export   --format svg|png|pdf --output-root DIR [options] <input.drawio>
bin/etch deliver  --format svg|png|pdf --output-root DIR [options] <input.drawio>
bin/etch verify   --output-root DIR
bin/etch gc       --output-root DIR [--delete]
```

`export` builds a finished generation and leaves the `current` pointer alone;
`deliver` also commits the pointer. stdout always carries the diagnostics JSON
of `contracts/diagnostics.schema.json` and nothing else, and every
human-readable line goes to stderr.

Runtime: bash 3.2 or newer, python3 3.9 or newer with the standard library
only, plus draw.io Desktop for the subcommands that export
(`contracts/environment.md`). Exit codes are `contracts/exit-codes.md`.

## Tests

```
python3 scripts/validate-contracts.py                                    # schemas against fixtures
python3 scripts/verify-vendor.py                                         # snapshot against vendor.lock
python3 tests/characterization/test_invariants.py                        # invariants, legacy wrapper
ETCH_CLI=$PWD/bin/etch python3 tests/characterization/test_invariants.py # invariants, etch CLI
ETCH_CLI=$PWD/bin/etch python3 tests/characterization/test_migration.py  # deliberate changes
```

Every case runs inside its own `mkdtemp` directory and, where draw.io is not
the thing under test, against a stub, so the suites need no draw.io install.
