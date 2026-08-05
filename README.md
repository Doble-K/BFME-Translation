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
├── LICENSE                       # GNU GPLv3
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
| Translated         | 1,272   |
| Pending            | 9,797   |
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

## TODO

- [ ] Auto-build for `spanishpatch202.big` binary if manual build fails
- [ ] Manual control of entries or reviews (user-driven override of translations)
- [ ] Improve merge system to facilitate new languages or improvements to existing translations
- [ ] Add support for translating mods
- [ ] Consider a more generic name for the project
