---
description: Translate and validate the next bounded localization batch.
agent: translator
---

Translate exactly one bounded batch for `config/project.json`.

Interpret `$ARGUMENTS` as `WORKER [COUNT]`. Require an explicit worker label so
separate sessions cannot accidentally share a batch. Use count 20 when omitted.
Worker must match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and counts must be between
1 and 100.

Run:

```bash
python3 tools/localization/agent_batch.py export \
  --project config/project.json \
  --mode incomplete \
  --count COUNT \
  --worker WORKER
```

Read `BATCH_FILE` without editing it. Edit only the separate `RESPONSE_FILE`,
filling every `translation` while preserving all IDs and metadata. Never create
a helper script. Repeating export for that worker resumes both files. Apply the
batch and response with actor `WORKER` and model
set to the actual provider/model identifier when available, using
`opencode-selected-model` only as fallback. Then run both validators required
by `AGENTS.md` as two separate shell calls, without `;`, `&&`, `echo`, or pipes.
If the response becomes malformed, run `reset-response` rather than
reconstructing the batch.

Do not read the complete catalog, use Ollama, commit, push, build, or package.
Report the number applied and validation result.
