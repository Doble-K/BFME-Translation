# BFME-Translation

Multilingual localization toolkit for games built on the SAGE engine, currently
focused on **The Lord of the Rings: The Battle for Middle-earth II: The Rise of
the Witch-king** (BFME2 ROTWK) 2.02.

> *"One Token to rule them all, One Terminal at a time."*

## Quick Start

Requirements:

- Linux or a compatible shell environment.
- Python 3.
- `python3-tk` for the optional `--gui` mode.
- The `tools/big4f/bin/linux/big4f` binary, executable with `chmod +x`.

Clone the repository and prepare the SAGE archive tool:

```bash
git clone https://github.com/Doble-K/BFME-Translation
cd BFME-Translation
chmod +x tools/big4f/bin/linux/big4f
```

Place a source `.big` package in `sources/`. For the current ROTWK project,
the English reference package is:

```text
sources/englishpatch202.big
```

Start with Gandalf. It is the main entry point for creating or opening a
localization project:

```bash
python3 gandalf.py
```

With no arguments Gandalf opens the graphical project setup when Tkinter is
available. To force the terminal wizard, use:

```bash
python3 gandalf.py --cli
```

For a simple graphical project setup explicitly, use:

```bash
python3 gandalf.py --gui
```

The GUI creates the catalog and project configuration, includes a light/dark
mode toggle, and leaves translation batches on the existing CLI tools.

After selecting an existing project, the `Run` controls can start an Ollama
bulk batch or open the manual editor in a terminal. Ollama starts in dry-run
mode unless `Guardar IA` is selected, and its output is shown in the lower log
panel. The progress panel separately shows the current `n/total`, entry ID,
model, result, and a determinate progress bar. The GUI also provides
`Construir prueba`, which runs build with source fallback and then packages a
partial test `.big`; it is not a release build.

Gandalf detects `.big` files, lists their contents, selects a string file,
creates a work catalog and project configuration, and supports arbitrary
source-to-target language pairs. It supports BFME1, BFME2, ROTWK 2.02, and
custom SAGE projects.

If a work catalog already exists, continue with the translation CLI:

```bash
python3 tools/localization/translate.py \
  catalogs/spanish_work.json \
  --count 20 \
  --edit
```

For direct source extraction instead of Gandalf:

```bash
tools/big4f/bin/linux/big4f x \
  sources/englishpatch202.big \
  /tmp/rotwk-source

python3 tools/localization/extract.py \
  /tmp/rotwk-source/data/lotr.str \
  catalogs/english.json
```

Do not use a generated localization package as the source reference.

## Project Status

The project is mature enough to be treated as a multilingual toolkit. The
first production use case is Latin American Spanish for ROTWK 2.02, while
other languages and SAGE projects are supported by the same workflow.

- Current project: ROTWK 2.02.
- English reference used for comparison: `englishpatch202.big`, version 9.7.7,
  build 9770.
- Spanish package used for pipeline tests and functionality checks: version
  9.7.5.
- French package used for pipeline tests and functionality checks: version
  9.7.6.
- Current Spanish work catalog: 13,533 entries, 1,272 translated/preserved and
  12,261 pending (9.4%).
- A final, fully translated and in-game-tested Spanish package has not been
  released yet.

The French and Spanish packages are test inputs for analysis and functionality
checks. They are not language standards or guarantees that a package is
complete or current.

## V1 Scope

The active v1 workflow is intentionally small:

```text
pending -> translated
              |
              +-- needs_review when an error is reported

preserved
```

- `pending`: needs translation.
- `translated`: accepted for compilation, but it may still contain errors.
- `preserved`: source text intentionally retained for engine/system entries.
- `needs_review`: flag for a human correction; it is not a separate status.

V1 is focused on a stable multilingual catalog pipeline, manual translation,
safe bulk preparation, validation, build, and packaging. A real AI provider can
write `translated` entries with `needs_review`; the legacy `ai_translate.py`
simulation is not part of the active workflow.

## Repository Structure

```text
BFME-Translation/
├── gandalf.py                    # Interactive project and source wizard
├── catalogs/
│   └── spanish_work.json         # Editable Spanish work catalog
├── config/
│   └── project.json              # ROTWK 2.02 project configuration
├── tools/
│   ├── big4f/                    # Local .big listing, extraction, and packing tool
│   └── localization/
│       ├── validate.py            # Structural catalog validation
│       ├── validate_translation.py# Protected-token validation
│       ├── extract.py             # .str to JSON extraction
│       ├── update.py              # Source-to-catalog synchronization
│       ├── translate.py           # Manual translation and correction CLI
│       ├── review.py              # V2 proposal/review operations
│       ├── compare.py             # Language/version comparison reports
│       ├── build.py               # Catalog to .str generation
│       └── pack.py                # .str and assets to .big packaging
├── translations/                 # Generated .str files
├── sources/                      # Input .big files
├── source/                       # Extracted .str files
├── backup/                       # Reference and test packages
├── releases/                     # Generated .big files
├── tests/                        # Pipeline regression tests
├── AGENTS.md                     # Translation workflow instructions
├── GLOSSARY.md                   # Shared terminology and style decisions
├── LICENSE                       # GNU GPLv3
└── README.md
```

## Translation Workflow

The JSON catalog is the editable source of truth. Generated `.str` and `.big`
files are build artifacts.

1. Select a limited batch of pending entries.
2. Translate `source` into Latin American Spanish in `translation`.
3. Set the entry status to `translated` and record metadata/history.
4. Normalize hotkeys before validation:

```bash
python3 tools/localization/normalize_hotkeys.py \
  catalogs/spanish_work.json \
  --write
```

5. Validate the catalog and protected tokens.
6. Review the result before compiling a release.

System-preserved entries use status `preserved` and the `system_preserved` flag.
They retain the source text intentionally, are validated and compiled normally,
but are not treated as human translations or included in normal translation
batches.

The proposal workflow is reserved for v2. The code contains experimental
support for `suggested`, `rejected`, and `reviewed`, but v1 does not require
those states or `review.py`.

For manual work:

```bash
python3 tools/localization/translate.py \
  catalogs/spanish_work.json \
  --count 20 \
  --edit
```

The CLI supports review mode, batch previews, navigation, retries, and safe
atomic writes. Same-language imports use review mode instead of pretending that
existing text is a new translation.

### Protected Tokens

When a string contains variables such as `%d`, `%s`, or `%ls`, those variables
are supplied by the game at runtime. Keep them exactly as shown and translate
only the surrounding words. For example:

```text
Source:     %d Days
Translation: %d Días
```

Never modify entry `id` fields, protected tokens, control characters such as
`\n`, `\t`, and `\r`, or engine tags such as `<COL>`. Do not translate URLs,
entry IDs, or format tokens.

Automatic control entries such as `LETTER:*` and `NUMBER:*` are hidden from
normal batches. Inspect them only for explicit investigation:

```bash
python3 tools/localization/translate.py \
  catalogs/spanish_work.json \
  --advanced \
  --count 20
```

Duplicate non-whitespace IDs use the last source occurrence. The discarded
versions remain auditable in `duplicate_meta` and `duplicate_shadowed`.
Whitespace-only IDs are preserved as orphan records and are not removed
automatically.

## Updating from a New Source

Extract the new `.str` and update the existing work catalog:

```bash
python3 tools/localization/extract.py \
  input.str \
  catalogs/new_source.json

python3 tools/localization/update.py \
  catalogs/new_source.json \
  catalogs/spanish_work.json
```

`extract.py` rejects undecodable files, incomplete blocks, and missing `END`
markers. `update.py` writes atomically, invalidates translations whose source
changed, resets review state, records duplicate metadata, and moves missing
entries to `retired_entries` instead of deleting them.

Updates are designed to be idempotent. Always inspect the resulting report and
catalog before translating new entries.

### Compare Languages or Versions

Compare catalogs by effective IDs and text without modifying either catalog:

```bash
python3 tools/localization/compare.py \
  catalogs/english.json \
  catalogs/french.json \
  --reference-name English \
  --target-name French \
  --output reports/generated/english-french.json
```

The report lists IDs missing from the target, extra target IDs, empty target
entries, texts equal to the reference, and duplicate IDs in both catalogs.
This makes version changes distinguishable from translation differences before
updating a work catalog.

## Validation and Tests

Run both validators after every translation batch and before any commit:

```bash
python3 tools/localization/validate.py --project config/project.json
python3 tools/localization/validate_translation.py --project config/project.json
python3 -m unittest discover -s tests -v
```

Both localization validators must return `Errors: 0`. Structural warnings for
historical duplicate or orphan records must be reviewed but do not necessarily
block the current catalog.

## Build a Localization Package

Do not build a release until the required translations have been completed and
validated. The normal release workflow is:

```bash
python3 tools/localization/validate.py --project config/project.json
python3 tools/localization/validate_translation.py --project config/project.json
python3 tools/localization/build.py --project config/project.json
python3 tools/localization/pack.py --project config/project.json
```

The generated package is written to:

```text
releases/spanishpatch202.big
```

`pack.py` verifies that the package exists, is non-empty, and contains
`data/lotr.str`. The output must still be tested manually in the game; the
tools do not install it automatically.

For an intentionally partial debug package only, source fallback is available:

```bash
python3 tools/localization/build.py \
  catalogs/spanish_work.json \
  /tmp/partial.str \
  --allow-source-fallback
```

Never use source fallback for a release build. Debug packaging options such as
`--debug`, `--exclude-orphan-ids`, and `--dedupe-ids last` operate on temporary
build data and do not delete catalog history.

## Project Configuration

`config/project.json` describes the current ROTWK 2.02 project:

- Source archive and string files.
- Work catalog and generated `.str` path.
- Generated package path.
- Target language and encoding.
- Output string-file header.

The current target encoding is Windows-1252 (`cp1252`) for SAGE compatibility.
The configuration is intended to become the main interface for future BFME1,
BFME2, mods, maps, and additional `.str` files.

## V2 Roadmap

V2 may add a separate proposal workflow without changing the simple v1 path:

```text
pending -> suggested -> translated -> reviewed
                    -> rejected
```

Possible v2 features include real AI providers, explicit approval/rejection,
bounded review context, multiple proposals, and richer collaboration. These
features are not required for v1 and should not block manual translation or
bulk preparation.

## Current Priorities

- Use the English ROTWK 2.02 build 9770 as the comparison reference.
- Continue using the French and Spanish packages for tests, analysis, and
  functionality checks.
- Translate in small, auditable batches and mark uncertain work with
  `needs_review`.
- Resolve or document duplicate and orphan records.
- Generate and test a complete Spanish package in the game.
- Extend the toolset to additional SAGE projects without hard-coded language
  assumptions.

## Disclaimer

This is an unofficial fan translation and localization toolkit. **The Lord of
the Rings: The Battle for Middle-earth II: The Rise of the Witch-king** and the
SAGE engine are trademarks of **Electronic Arts Inc.** The game and its assets
are copyrighted by their respective owners.

All Tolkien-related intellectual property is owned by the respective rights
holders, including **The Tolkien Estate** and **Middle-earth Enterprises**.

This project is not affiliated with, endorsed by, or sponsored by Tolkien,
Middle-earth Enterprises, Electronic Arts, or any of their subsidiaries or
licensees. Game assets remain the property of their respective owners.

## License

The project source code and tooling are distributed under the GNU General Public
License v3. See `LICENSE`.
