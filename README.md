# BFME-Translation

Spanish (Latin American) translation project for **Battle for Middle-earth II: Rise of the Witch-king** (BFME2 ROTWK) and other SAGE engine games.

> *"One Token to rule them all, One Terminal at a time."*

## Description

This repository contains translations of SAGE engine game `.str` localization files, converted to a compatible format. The compiled output package is `releases/spanishpatch202.big`.

Currently focused on BFME2 ROTWK, with the goal of supporting all three SAGE-based games (BFME1, BFME2, ROTWK) and potentially other games using the SAGE engine.

## Disclaimer

This is an unofficial fan translation project. **Battle for Middle-earth II: Rise of the Witch-king** and the SAGE engine are trademarks of **Electronic Arts Inc.** The game and its assets are copyrighted by **EA Games / EA DICE** and/or their respective publishers.

All Tolkien-related intellectual property (characters, places, lore, etc.) is the property of **The Tolkien Estate** and **Middle-earth Enterprises** (formerly Saul Zaentz Company).

This translation project is not affiliated with, endorsed by, or sponsored by Tolkien, Middle-earth Enterprises, Electronic Arts, or any of their subsidiaries or licensees. All game assets remain the property of their respective owners.

## Project Structure

```
BFME-Translation/
├── gandalf.py                    # Main project and source wizard
├── catalogs/
│   └── spanish_work.json    # Main translation catalog (11,069 entries)
├── config/
│   └── project.json         # ROTWK 2.02 project configuration
├── tools/
│   └── localization/
│       ├── validate.py           # Structural catalog validation
│       ├── validate_translation.py # Translation validation
│       ├── extract.py            # Extracts entries from .str files
│       ├── update.py             # Updates the work catalog from a new source
│       ├── translate.py          # Manual review and translation CLI
│       ├── build.py              # Compiles catalog to .str format
│       └── pack.py               # Packages .str into .big
├── translations/
│   └── spanish/data/
│       └── lotr.str             # Local generated output (not versioned)
├── sources/                      # Local input .big files (not versioned)
├── source/                       # Local source .str files (not versioned)
├── releases/
│   └── spanishpatch202.big      # Local compiled package (not versioned)
├── tests/
│   └── test_localization_tools.py # Pipeline regression tests
├── AGENTS.md                     # Agent translation instructions
├── LICENSE                       # GNU GPLv3
└── README.md                     # This file
```

## How It Works

### Manual Quick Start

The repository can be used from any directory after cloning it. The current
workflow targets BFME2 ROTWK with patch 2.02.

```bash
git clone https://github.com/Doble-K/BFME-Translation
cd BFME-Translation
chmod +x tools/big4f/bin/linux/big4f
```

The original game or patch `.big` may be available in the clone at
`source/englishpatch202.big`. If it is not included, place the external file
in the local `sources/` directory using this filename:

```text
sources/rotwk-2.02.big
```

The `sources/` directory is prepared in the repository, but `.big` files inside
it are ignored by Git. Extract the available source package when creating a
new catalog:

```bash
SOURCE_BIG="source/englishpatch202.big"
test -f "$SOURCE_BIG" || SOURCE_BIG="sources/rotwk-2.02.big"
tools/big4f/bin/linux/big4f x "$SOURCE_BIG" /tmp/rotwk-source && \
python3 tools/localization/extract.py \
  /tmp/rotwk-source/data/lotr.str \
  catalogs/english.json
python3 gandalf.py \
  catalogs/english.json \
  catalogs/rotwk_work.json
```

`gandalf.py` refuses to overwrite an existing catalog unless
`--force` is supplied. If the clone already contains
`catalogs/spanish_work.json`, skip extraction and initialization and start the
translation CLI directly. The `.big` placed in `sources/` must be the original
English ROTWK 2.02 source package, not the generated Spanish package from
`releases/`.

If the repository already contains a prepared work catalog, start directly
with the CLI:

```bash
python3 tools/localization/translate.py \
  catalogs/spanish_work.json \
  --count 20 \
  --edit
```

An agent can process pending entries in bulk using the same catalog. Manual and
agent changes use the same token validation, metadata, and history rules.

Before creating a package:

```bash
python3 tools/localization/validate.py
python3 tools/localization/validate_translation.py
python3 -m unittest discover -s tests -v
```

Create the Spanish package after all required translations are complete:

```bash
python3 tools/localization/build.py --project config/project.json
python3 tools/localization/pack.py --project config/project.json
```

The generated package is written separately to:

```text
releases/spanishpatch202.big
```

After packaging, locate and verify the output with:

```bash
ls -lh releases/spanishpatch202.big
realpath releases/spanishpatch202.big
```

That exact file is the package to copy and test manually in the game. The
original input remains in `sources/`; the translated output is always in
`releases/`.
Copy that generated `.big` into the appropriate game installation directory
where the game loads language patch packages. The repository tools generate and
verify the package but do not install it into the game automatically.

For an intentionally partial test package, use `--allow-source-fallback`; do
not use that flag for a release package.

### Translation Workflow

1. **Read pending entries**: Load `catalogs/spanish_work.json` and find entries with `status: "pending"`.
2. **Translate**: Translate the `source` text into Latin American Spanish in the `translation` field, set `status` to `"translated"`, and record metadata/history.
3. **Preserve**: Never modify entry `id` fields, protected tokens (`%d`, `%s`), control characters (`\n`), or engine tags (`<COL>`).
4. **Validate**: Run both validation scripts:
   - `python3 tools/localization/validate.py`
   - `python3 tools/localization/validate_translation.py`
   If any return errors, fix them immediately before committing.
5. **Commit**: Stage only the modified files (`git add <specific-paths>`, never `git add .`) and commit with a conventional message (e.g., `feat(localization): translate batch 10`).
6. **Sync**: Pull, push, and pull again to ensure integrity.

### Agent and Manual Review Rules

- The catalog JSON is the source of truth; `.str` and `.big` files are generated artifacts.
- Duplicate non-whitespace IDs use the last occurrence as the source of truth.
- `update.py` records duplicate metadata in `duplicate_meta` and marks shadowed entries with `duplicate_shadowed`.
- IDs made only of whitespace are preserved as orphan records and are not removed automatically.
- Bulk agents should process only selected, non-empty entries. The manual CLI skips shadowed duplicates, orphan IDs, and empty source strings by default.
- Use `--include-shadowed`, `--include-orphans`, or `--include-empty` only for explicit investigation.

To review or edit pending entries manually:

```bash
python3 tools/localization/translate.py --count 10
python3 tools/localization/translate.py --count 10 --edit
```

Manual edits are token-validated, saved atomically, and recorded in entry history and metadata.

To create a new work catalog interactively, use Gandalf. It detects `.big`
files under `source/` and `sources/`, offers BFME1, BFME2, ROTWK 2.02, or a
custom SAGE project, and asks for source language, target language, encoding,
catalog output, and project configuration output:

```bash
python3 gandalf.py
```

Gandalf extracts the selected `.big` and the selected `.str` automatically and
creates both the work catalog and a project configuration. It accepts any
source-to-target language pair. The positional mode remains available for
agents that already have an extracted JSON catalog.

### Build Workflow (Release)

When a release build is requested:
1. `python3 tools/localization/validate.py`
2. `python3 tools/localization/validate_translation.py`
3. `python3 tools/localization/build.py catalogs/spanish_work.json translations/spanish/data/lotr.str --encoding cp1252`
4. `python3 tools/localization/pack.py`
5. `pack.py` verifies that the package exists, is non-empty, and contains `data/lotr.str`.

The build defaults to Windows-1252/ANSI for SAGE compatibility. Use `--encoding` with another compatible code page for languages that require it.

Release builds fail when a translation is empty. This prevents English source text from entering a release silently. The fallback is available only for an explicitly partial build:

```bash
python3 tools/localization/build.py catalogs/spanish_work.json /tmp/partial.str --allow-source-fallback
```

The command reports how many entries used source text as a fallback. Do not use this flag for a release build.

For temporary debug packages, `pack.py` builds from a temporary directory. The catalog and normal `lotr.str` remain unchanged. `DEBUGING` identifies the package as experimental:

```bash
python3 tools/localization/pack.py --debug
python3 tools/localization/pack.py --exclude-orphan-ids --dedupe-ids last --debug
```

`--exclude-orphan-ids` removes whitespace-only IDs only from the temporary debug build. `--dedupe-ids last` keeps the last non-whitespace duplicate for testing; it does not delete catalog history.

### Updating From a New Source

```bash
python3 tools/localization/extract.py input.str catalogs/new_source.json
python3 tools/localization/update.py catalogs/new_source.json catalogs/spanish_work.json
```

`extract.py` rejects undecodable files, incomplete blocks, and missing `END` markers. `update.py` invalidates stale translations when source text changes, resets review state, updates source lines, and writes atomically.

Updates are idempotent. Duplicate non-whitespace IDs use the last occurrence and receive `duplicate_meta`; whitespace-only IDs receive `orphan_meta`. Entries absent from a new source move to `retired_entries` instead of being deleted, and are restored automatically if they reappear.

The current project can also be selected explicitly:

```bash
python3 tools/localization/build.py --project config/project.json --allow-source-fallback
python3 tools/localization/pack.py --project config/project.json
```

The project configuration currently targets ROTWK 2.02. Its source archive is external and is intentionally not stored in this repository.

## Current Progress

| Metric             | Value   |
|--------------------|---------|
| Total entries      | 11,069  |
| Translated         | 1,273   |
| Pending            | 9,796   |
| **Progress**        | **11.5%**|

### Translation History

| Commit   | Description                              |
|----------|------------------------------------------|
| e688e2e  | Added GNU GPLv3 license                |
| 4c2dab3  | README rewritten in English            |
| 424efd9  | Added project README with workflow and progress |
| d9282b1  | Fixed 18 untranslated entries          |
| 0e21e10  | Batch of 100 entries translated        |
| 9e8433a  | Batch of 10 entries translated         |
| 33aaae9  | Block missing translations in release builds |
| 29f1cbe  | Validate SAGE string extraction         |
| 2a53ea3  | Record last-wins duplicate metadata     |
| aec663d  | Make manual translation review safe     |

## Translation Rules

- **Latin American Spanish**: Use standard LATAM terminology, not Spain Spanish.
- **Preserve format**: Wildcards (`%d`, `%s`, `%ls`), newlines (`\n`), and engine tags (`<COL>`) must remain intact.
- **Do not translate**: URLs, entry IDs, and format tokens.
- **Metadata**: Each entry includes `translation_meta` (origin, model, date, confidence) and `review` (AI and human review status).
- **Duplicate policy**: Normal duplicate IDs use the last source occurrence; duplicate and orphan metadata remains auditable in the catalog.

## Validation

```bash
python3 tools/localization/validate.py
python3 tools/localization/validate_translation.py
```

Both scripts must return `Errors: 0` before committing.

The structural validator reports orphan IDs separately. Use `--strict-duplicates` to make real duplicate IDs blocking errors, or repeat `--ignore-id ID` only for documented temporary exceptions.

Run the automated regression tests with:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover protected tokens, CRLF parsing, malformed `.str` blocks, source retirement and restoration, idempotent duplicate handling, strict builds, project configuration, and packaging flags.

## TODO

- [ ] Validate package contents beyond the presence of `data/lotr.str`.
- [ ] Support multiple configured `.str` files while preserving ROTWK behavior.
- [ ] Add a source archive extraction workflow for external ROTWK inputs.
- [ ] Add reproducible entry selection to the manual CLI.
- [ ] Add a review UI or a richer CLI for human and AI proposals.
- [ ] Improve merge support for new languages and mods.
