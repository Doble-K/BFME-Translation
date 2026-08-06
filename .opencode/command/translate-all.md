---
description: Continuously translate validated batches until no eligible entries remain.
agent: translator
---

Run the ROTWK 2.02 translation queue continuously for
`config/project.json`.

Interpret `$ARGUMENTS` as `WORKER [COUNT]`. Require an explicit unique worker
label and use count 100 when omitted. Worker must match
`[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.

For each iteration:

1. Export with `--worker WORKER`; this resumes that worker's lease when needed.
2. Read `BATCH_FILE` without editing it.
3. Edit only `RESPONSE_FILE` and fill its `translation` fields. Never create a
   helper script or rewrite the batch.
4. Apply the batch and response with actor `WORKER` and the actual selected provider/model identifier
   when available.
5. Run both validators as separate shell calls and require zero errors. Never
   combine them with shell operators.
6. Repeat without narrating every source string.

When export reports that no entries are available, run aggregate status. Finish
successfully only when `eligible` is zero and no batches remain active. If other
workers own the remaining entries, wait for the coordinator rather than
claiming completion. Stop on a repeated validation failure, stale batch that
cannot be safely resumed, ambiguous protected syntax, or a systematic tooling
defect. Report completed batches, applied entries, remaining blocker if any,
and final validation.

Never inspect a full catalog, invoke Ollama, weaken validation, commit, push,
build, or package.
