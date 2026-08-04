# AGENTS.md - BFME Translation Agent Instructions

Several agents or automated workflows may push to this repository. Keep each translation change small, verified, and easy to rebase.

## Authority and Work Selection

An explicit user request or assigned task lane overrides the generic queue. If a task names a catalog, file, or batch, stay in that lane. Otherwise:

1. `git pull --rebase origin master` (or `main`)
2. Read `catalogs/spanish_work.json` to find pending entries.
3. Process controlled batches (default: 50 entries per iteration) to prevent response truncation.

## Bank One Verified Translation Unit

1. **Translate:** Select pending entries (`status: "pending"`), translate the `source` text to Latin American Spanish inside the `translation` field, update `status` to `"translated"`, and record metadata/history.
2. **Strict Preservation:** Never modify entry `id` fields. Never translate, alter, or remove protected tokens, format wildcards (e.g., `%d`, `%s`), control characters (`\n`), or engine tags (`<COL>`).
3. **Focused Verification:** Immediately run exact validation scripts:
   - `python3 tools/localization/validate.py`
   - `python3 tools/localization/validate_translation.py`
   If any validation returns errors (`Errors > 0`), fix them immediately. Never commit unvalidated data.
4. **Staging & Commit:** Stage only the specific files modified for this unit (`git add <specific-paths>`). Never use `git add .` or `git add -A`. Commit normally using conventional commit messages (e.g., `feat(localization): translate batch 01`).
5. **Sync:** Run `git pull --rebase`, push changes, and pull again to ensure integrity.

## Build and Package Workflow

When requested to compile a release:
1. `python3 tools/localization/build.py catalogs/spanish_work.json translations/spanish/data/lotr.str`
2. `python3 tools/localization/pack.py`
3. Verify that the output package (`releases/spanishpatch202.big`) updates correctly.

## Integrity and Safety Policy

- **No Fallbacks:** Do not bypass validation checks or ignore token mismatches for convenience.
- **Data Isolation:** Query and update local JSON catalogs safely. Do not load massive files wholesale if a targeted filter can be used.
- **Preserve State:** If a translation batch fails verification, revert only that modification and re-evaluate the source entries.
