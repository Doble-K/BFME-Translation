# AGENTS.md - BFME Translation Agent Instructions

Several agents or automated workflows may push to this repository. Keep each translation change small, verified, and easy to rebase.

## Authority and Work Selection

An explicit user request or assigned task lane overrides the generic queue. If a task names a catalog, file, or batch, stay in that lane. Otherwise:

1. `git pull --rebase origin master` (or `main`)
2. Export a bounded batch with `agent_batch.py`; never read a complete work catalog into the agent context.
3. Process controlled batches (default: 20 entries, maximum: 100) to prevent unnecessary token use.

```bash
python3 tools/localization/agent_batch.py export \
  --project config/project.json \
  --count 20 \
  --mode incomplete \
  --worker WORKER_NAME
```

Read the path printed as `BATCH_FILE` without editing it. Edit only `RESPONSE_FILE`, filling each `translation` value without changing IDs or metadata, then apply both files:

```bash
python3 tools/localization/agent_batch.py apply \
  --project config/project.json \
  --input BATCH_FILE \
  --response RESPONSE_FILE \
  --actor WORKER_NAME \
  --model MODEL_NAME
```

The `incomplete` mode selects real pending entries plus exact source placeholders recorded by the import pipeline. Export creates a read-only batch, a minimal editable response, a leased reservation, and unique `batch_id`, so active workers receive disjoint IDs. Repeating export with the same worker resumes its current files. The default lease is six hours; use `renew` before expiration or `release` when abandoning work. The tool reads the large catalog inside the local Python process, not in the LLM context. Application is atomic and rejects stale or unleased batches, changed IDs, modified manifests, truncated responses, entries that are no longer eligible, empty translations, and protected-token mismatches.

For concurrent work in the same checkout, every agent must use a unique worker name. Inspect aggregate progress without exposing source text:

```bash
python3 tools/localization/agent_batch.py status \
  --project config/project.json \
  --mode incomplete \
  --json
```

Leases coordinate processes sharing the same workspace. Agents running in separate clones require an external shared queue or repository synchronization; local lease files do not coordinate across machines.

## Bank One Verified Translation Unit

1. **Translate:** Select incomplete entries (`pending` or recorded source placeholders), translate the `source` text to Latin American Spanish inside the `translation` field, update `status` to `"translated"`, and record metadata/history.
2. **Strict Preservation:** Never modify entry `id` fields. Never translate, alter, or remove protected tokens, format wildcards (e.g., `%d`, `%s`), control characters (`\n`), or engine tags (`<COL>`).
   Proposals use `suggested`, rejected proposals use `rejected`, and system-preserved entries use `preserved` with `system_preserved`.
3. **Focused Verification:** Immediately run exact validation scripts:
   - `python3 tools/localization/validate.py --project config/project.json`
   - `python3 tools/localization/validate_translation.py --project config/project.json`
   If any validation returns errors (`Errors > 0`), fix them immediately. Never commit unvalidated data.
4. **Staging & Commit:** Stage only the specific files modified for this unit (`git add <specific-paths>`). Never use `git add .` or `git add -A`. Commit normally using conventional commit messages (e.g., `feat(localization): translate batch 01`).
5. **Sync:** Run `git pull --rebase`, push changes, and pull again to ensure integrity.

OpenCode translation workers are an exception to steps 4 and 5: they must not use Git. The coordinator or a human performs staging, commit, and synchronization after validated batches are complete.

## Build and Package Workflow

When requested to compile a release:
1. `python3 tools/localization/build.py --project config/project.json`
2. `python3 tools/localization/pack.py --project config/project.json`
3. Verify that the output package (`releases/spanishpatch202.big`) updates correctly.

## Integrity and Safety Policy

- **No Fallbacks:** Do not bypass validation checks or ignore token mismatches for convenience.
- **Data Isolation:** Agents must use `agent_batch.py` and must not open massive catalogs directly. Local tools may parse them internally without spending LLM context tokens.
- **Preserve State:** If a translation batch fails verification, revert only that modification and re-evaluate the source entries.

## Urgent Tooling Escalation

If repeated manual work, a format limitation, missing validation, or a pipeline defect would make translation unsafe or wasteful, stop that batch and report it as a tooling issue. Do not work around systematic problems by editing the full catalog or weakening validation.

A tooling proposal must state:

1. The concrete problem and how to reproduce it.
2. Whether it blocks translation or only reduces efficiency.
3. The smallest reusable command or project-level change that solves it.
4. Catalog compatibility and migration impact.
5. Tests and validation required before translation resumes.

Agents may implement a small, backward-compatible tool immediately when the problem is reproducible, the solution does not rewrite translation data, and tests can verify it. Ask for approval first when the change alters catalog semantics, performs a bulk migration, removes data, changes generated package contents, or introduces a new external service or dependency.
