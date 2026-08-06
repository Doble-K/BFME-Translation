---
description: Validate, build, and package a complete translation candidate.
agent: translator
---

Create a candidate package only after the translation queue is complete.

1. Run `agent_batch.py status --project config/project.json --mode incomplete
   --json` and require `eligible` to be zero with no active batches.
2. Normalize hotkeys with `normalize_hotkeys.py --project config/project.json
   --write`.
3. Run both project validators and require zero errors.
4. Run strict `build.py --project config/project.json` without source fallback.
5. Run `pack.py --project config/project.json`.
6. Report the generated package path and remind the user that community review
   and in-game testing remain pending.

Do not use `--allow-source-fallback`, edit catalogs directly, commit, or push.
