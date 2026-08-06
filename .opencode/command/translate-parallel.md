---
description: Run one bounded wave of isolated translation workers.
agent: translation-coordinator
---

Process exactly one bounded wave of the localization queue with parallel
workers. Do not start another wave in this command.

Interpret `$ARGUMENTS` as `PREFIX WORKERS COUNT`. Require a unique prefix for
this run matching `[A-Za-z0-9][A-Za-z0-9._-]{0,55}`, between 2 and 8 workers,
and a batch size between 1 and 100. Example:

```text
/translate-parallel rotwk-run1 4 100
```

Preserve PREFIX exactly as supplied. Never shorten it, remove a suffix, or use
it as a worker label by itself. The only valid worker labels are the exact
strings `PREFIX-1` through `PREFIX-WORKERS`.

Launch exactly WORKERS `translation-worker` subagents concurrently in one
parallel task call. Give each one a unique label `PREFIX-1`, `PREFIX-2`, and so
on, plus COUNT. Each subagent must claim through `agent_batch.py export`; never
assign IDs or split a catalog in prompts. Do not restate or override the worker
procedure in delegated prompts; the `translation-worker` agent instructions are
authoritative.

The coordinator must never run `agent_batch.py export` or `apply`, read a batch,
or edit a response. Its first translation action is the single parallel task
call that launches the isolated workers.

Wait for all workers. Then run aggregate `agent_batch.py status` and both
validators. If a worker stops or returns an empty report, locate its active
batch in status and release that lease by `batch_id` and worker before launching
a replacement with a new suffix. Do not read batch contents in the coordinator,
invoke Ollama, commit, push, build, or package.

Do not report `Done` while status contains any active worker whose name starts
with PREFIX. For a token or response validation failure, relaunch the same
`translation-worker` label so export resumes that exact batch and repairs its
`RESPONSE_FILE`. Retry once. If it still cannot apply safely, release that lease
and report the run as blocked, not complete. A successful run ends only when all
workers with PREFIX have consumed or explicitly released their leases.
