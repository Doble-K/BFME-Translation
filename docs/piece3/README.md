# Piece 3 Small-Model Work Queue

This directory is the complete entry point for continuing Piece 3 with a
small-context model. Do not reconstruct the prior conversation and do not scan
the repository.

## Objective

Finish and stabilize detached OpenCode farm controls in Gandalf while preserving
safe process ownership, exact lease cleanup, and a responsive GUI.

Base commit: `8d6c624 feat(gandalf): add safe concurrent editing`.

Piece 3 is currently uncommitted. Do not commit, stage, pull, rebase, or push
unless the user explicitly requests it.

## How To Continue

1. Read this file.
2. Run the safe preflight commands below.
3. Open `QUEUE.md` and select the first `ready` packet.
4. Read only that packet and the files/ranges it permits.
5. Complete its focused verification.
6. Update only its `Result` section and its status in `QUEUE.md`.
7. Stop the session. The next model takes the next packet.

Do not read `docs/piece3-session-handoff.md`; this queue replaces it for normal
small-model work. It remains as historical source material for escalation only.

## Safe Preflight

Run only:

```bash
git status --short
git diff --stat
git diff --check
```

Expected Piece 3 files may already be modified. Never revert changes you did not
make. If another process changes a file currently being edited and creates a
direct conflict, stop and ask the user.

## Hard Context Limits

- Never read complete catalogs, generated reports, saved tool output, or a full
  repository diff.
- Never run plain `git diff`; select one file, and preferably one function.
- Do not use subagents.
- Do not search outside the files authorized by the active packet.
- Read no more than 200 lines around any match.
- Address one packet only per session.
- Run only the packet's focused tests. Packet 10 owns the full suite.
- Never start the real translation farm. Tests may use their fake temporary farm.
- Prefer deleting accidental complexity over adding compatibility layers.
- Preserve schema 1/2 compatibility only to stop an already-running old farm.
- Do not alter catalog semantics, translation data, or dependencies.

## Protected Unrelated Change

`catalogs/spanish_9770_work.json` has a suspicious unrelated `Color:Red` change
that resembles terminal input. Do not open the catalog, modify that entry, stage
the file, or include it in Piece 3. Ask the user if it blocks the work.

## Global Safety Contract

- Schema 3 operations fail closed when process identity cannot be verified.
- A recycled or unverifiable PID/process group is never signaled.
- Runtime profile edits cannot hide an active farm.
- Cleanup uses the catalog and worker labels frozen into farm state.
- Lease release uses exact labels, never broad prefix matching.
- `drain` and `resume` commands are atomically claimed and acknowledged.
- Invalid or deleted profiles permit safe status/stop recovery, not fresh start.
- Tk callbacks never perform catalog parsing or bounded log reads synchronously.
- An orphaned wave remains stoppable but cannot be started, drained, or resumed.

## Escalation

Stop and report a blocker instead of broadening scope when:

- a packet requires a file not listed in its allowed context;
- a safety invariant conflicts with existing behavior and the smallest resolution
  changes catalog semantics or compatibility policy;
- a focused test exposes unrelated failures;
- ownership cannot be proven before signaling or releasing leases;
- the suspicious catalog change interferes with validation.

Use `RESULT_TEMPLATE.md` for the packet result. Keep it short enough for the next
model to read without opening prior diffs.

## Start Prompt

```text
Read docs/piece3/README.md and docs/piece3/QUEUE.md. Take only the first ready
packet. Obey its file/range and command limits, make the smallest safe fix, run
only its focused verification, then update that packet's Result section and its
queue status. Do not inspect the rest of the repository or run the real farm.
```
