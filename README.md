# BFME-Translation

Spanish (Latin American) translation project for **Battle for Middle-earth I** (BFME1).

## Description

This repository contains translations of BFME1 `.str` localization files, converted to the SAGE engine-compatible format. The compiled output package is `releases/spanishpatch202.big`.

## Project Structure

```
BFME-Translation/
├── catalogs/
│   └── spanish_work.json    # Main translation catalog (11,069 entries)
├── tools/
│   └── localization/
│       ├── validate.py           # Structural catalog validation
│       ├── validate_translation.py # Translation validation
│       ├── build.py              # Compiles catalog to .str format
│       └── pack.py               # Packages .str into .big
├── translations/
│   └── spanish/data/
│       └── lotr.str             # Translated output file
├── releases/
│   └── spanishpatch202.big      # Final compiled package
├── AGENTS.md                     # Agent translation instructions
└── README.md                     # This file
```

## How It Works

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

### Build Workflow (Release)

When a release build is requested:
1. `python3 tools/localization/build.py catalogs/spanish_work.json translations/spanish/data/lotr.str`
2. `python3 tools/localization/pack.py`
3. Verify that `releases/spanishpatch202.big` updates correctly.

## Current Progress

| Metric             | Value   |
|--------------------|---------|
| Total entries      | 11,069  |
| Translated         | 245     |
| Pending            | 10,824  |
| **Progress**        | **2.2%**|

### Translation History

| Commit   | Description                              |
|----------|------------------------------------------|
| d9282b1  | Fixed 18 untranslated entries         |
| 0e21e10  | Batch of 100 entries translated        |
| 9e8433a  | Batch of 10 entries translated         |

## Translation Rules

- **Latin American Spanish**: Use standard LATAM terminology, not Spain Spanish.
- **Preserve format**: Wildcards (`%d`, `%s`, `%ls`), newlines (`\n`), and engine tags (`<COL>`) must remain intact.
- **Do not translate**: URLs, entry IDs, and format tokens.
- **Metadata**: Each entry includes `translation_meta` (origin, model, date, confidence) and `review` (AI and human review status).

## Validation

```bash
python3 tools/localization/validate.py
python3 tools/localization/validate_translation.py
```

Both scripts must return `Errors: 0` before committing.