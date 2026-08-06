---
description: Repeat bounded parallel translation waves until the queue is complete.
agent: translation-coordinator
---

Process the localization queue with repeated parallel waves.

Run unattended. Never ask the user for shell permission or clarification. The
configured native tools and localization command allowlist are sufficient for
the complete workflow.

Interpret `$ARGUMENTS` as `PREFIX WORKERS COUNT`. Require a unique prefix for
this run matching `[A-Za-z0-9][A-Za-z0-9._-]{0,55}`, between 2 and 8 workers,
and a batch size between 1 and 100. Example:

```text
/translate-parallel-all rotwk-run1 4 25
```

Use fresh `translation-worker` subagent contexts for every wave. Worker labels
are stable across waves: `PREFIX-1`, `PREFIX-2`, and so on. Each worker processes
exactly one batch per invocation according to its authoritative agent
instructions. It must claim work through `agent_batch.py export`; never assign
IDs or split a catalog in prompts. Do not restate or override the worker
procedure in delegated prompts.

Preserve PREFIX exactly as supplied. Never shorten it, remove a suffix, use it
as a worker label by itself, or run `agent_batch.py export` or `apply` in the
coordinator. Only the isolated workers may claim and apply batches.

Before the first wave, run aggregate `agent_batch.py status` in incomplete mode.
Track the initial eligible count and a cumulative applied count. Then repeat:

1. Run aggregate status. If `eligible` is zero, leave the loop. If `available`
   is zero and no active worker starts with PREFIX, stop as blocked by unrelated
   leases; do not busy-wait or claim completion.
2. Calculate the number of workers for this wave as the smaller of WORKERS and
   `ceil(available / COUNT)`. Launch exactly that many `translation-worker`
   subagents concurrently in one parallel task call. Give each only its stable
   worker label and COUNT.
3. Wait for every worker and add its applied entry count to the cumulative
   total. A successful worker must report one applied batch or explicitly report
   that no entries were available.
4. If a worker stops, returns an empty report, attempts a denied command, or
   reports a token or response validation failure, run status and relaunch the
   same worker label once. This resumes its exact lease with a fresh context. If
   the retry still fails, release that worker's lease, release any other active
   PREFIX leases, and stop as blocked without requesting user input.
5. Run aggregate status again. Do not begin another wave while any active worker
   starts with PREFIX. If the eligible count did not decrease despite available
   work, release active PREFIX leases and stop as blocked to prevent an infinite
   loop.

When `eligible` reaches zero, run aggregate status once more and run both project
validators as separate shell calls. Require zero errors. Existing duplicate-ID
warnings may remain. Report the number of waves, cumulative entries applied,
final validation, and final queue status.

Never read batch contents in the coordinator, inspect a catalog, invoke Ollama,
commit, push, build, or package. Never report `Done` unless `eligible` is zero,
both validators have zero errors, and no active worker starts with PREFIX. On an
intentional early stop, release every active lease owned by PREFIX. Use shell
only for explicitly allowed localization commands; use native tools for every
file operation and never request additional permissions.
