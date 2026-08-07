# Piece 3 Session Handoff

> **Historical document:** This handoff records an unfinished Piece 3 session
> before the roadmap marked Piece 3 complete. It is retained for audit context
> only. Do not use it as current instructions or project status; use
> [`STATUS.md`](STATUS.md), [`gandalf-roadmap.md`](gandalf-roadmap.md), and
> [`workflow.md`](workflow.md) instead.

The instructions, observed state, file list, and verification results below are
historical snapshots and may no longer reflect the repository.

## Goal

Finish and stabilize Piece 3: detached OpenCode farm controls in Gandalf.

Base commit: `8d6c624 feat(gandalf): add safe concurrent editing`.

Piece 3 is uncommitted and underwent a large lifecycle architecture refactor.
It must receive one bounded final audit before being considered complete.

## Strict Context Budget

- Do not read complete catalogs, generated reports, saved tool output, or full diffs.
- Do not run plain `git diff`; always select one file and, when possible, one function.
- Do not use subagents unless a concrete blocker cannot be resolved directly.
- Use `Glob`/`Grep`, then read at most 100-200 relevant lines around a match.
- Investigate and fix one invariant at a time. Re-run only its focused tests.
- Do not repeatedly run the full suite. Run it once after all focused checks pass.
- Keep progress messages and the final response concise.
- Never start the real translation farm during this audit.

## Safe First Commands

Run only:

```bash
git status --short
git diff --stat
git diff --check
```

Then inspect targeted functions in these files only:

- `tools/localization/opencode_farm.py`
- `tools/localization/agent_batch.py`
- `tools/localization/watch_progress.py`
- `gandalf.py`
- Relevant Piece 3 tests in `tests/test_localization_tools.py`

Do not inspect unrelated files unless a failing focused test points to one.

## Known State

- Last observed suite: 90 tests passed.
- Last observed structural validation: 0 errors, 65 historical duplicate-ID warnings.
- Last observed translation validation: 0 errors.
- Last observed queue: 10,090 incomplete, 0 reserved, no active batches.
- Last observed farm state: stopped, no supervisor, no leases.
- `py_compile`, GUI smoke, and `git diff --check` passed at that point.
- No commit or push was made for Piece 3.

Modified files last observed:

```text
README.md
catalogs/spanish_9770_work.json
config/gandalf.example.json
docs/gandalf-roadmap.md
docs/workflow.md
gandalf.py
tests/test_localization_tools.py
tools/localization/agent_batch.py
tools/localization/opencode_farm.py
tools/localization/watch_progress.py
```

## Critical Catalog Warning

`catalogs/spanish_9770_work.json` contains a suspicious unrelated change:

```text
Color:Red -> ":skip\u001bOM:skip"
```

This looks like accidental terminal input, not a valid translation. Inspect only
that entry's diff. Do not read the catalog and do not restore or modify it without
first confirming with the user, because its origin is not proven.

Do not include this catalog change in a Piece 3 commit.

## Architecture Introduced

The unfinished refactor currently intends to provide:

- Detached `start`, structured `status`, `drain`, `resume`, and immediate `stop`.
- Lifecycle serialization using file locks.
- Runtime state/control anchoring under `.agent`.
- Recovery for an unreadable or deleted farm profile while a farm is active.
- Schema 3 state with supervisor process identity and coordinator tokens.
- Detection and safe stopping of orphaned coordinator process groups.
- Exact worker-label lease release instead of broad prefix release.
- Frozen project/catalog identity during a farm run.
- Atomic control claiming and acknowledged `drain`/`resume` commands.
- Asynchronous Gandalf queue polling and bounded asynchronous log reads.
- GUI reconnect behavior independent of Gandalf's lifetime.

## Final Audit Invariants

Check only these invariants, in order:

1. Two profiles sharing one state file cannot start two supervisors.
2. Editing profile runtime paths cannot hide or strand an active supervisor.
3. `stop` never signals a recycled or unverifiable PID/process group.
4. Schema 3 never falls back silently to weak legacy process matching.
5. Project/profile edits cannot redirect lease cleanup to another catalog.
6. Lease cleanup releases only exact workers owned by this farm.
7. `drain` finishes the current wave, starts no new wave, and confirms receipt.
8. `resume` either cancels drain or starts one detached supervisor after drain.
9. Failed detached startup cannot leave a supervisor, coordinator, state, or lease.
10. Invalid/deleted profiles still allow status and stop, but not a fresh start.
11. Gandalf never blocks Tk while reading the catalog or logs.
12. Gandalf enables `stop` for an orphaned wave and disables unsafe start/resume.

Prefer deleting complexity over adding another compatibility layer if an
invariant cannot be established simply. Preserve compatibility only for existing
schema 1/2 farm state needed to stop an already-running old supervisor.

## Focused Verification

Use test-name filtering or explicit test methods while fixing an invariant.
The most important existing test is the detached lifecycle smoke test, which is
intended to use a fake `opencode`, create a real temporary lease, test concurrent
starts, drain, resume, stop, and finish with zero leases.

After focused tests pass, run exactly once:

```bash
python3 -m unittest discover -s tests -p 'test*.py'
python3 -m py_compile gandalf.py tools/localization/opencode_farm.py \
  tools/localization/agent_batch.py tools/localization/watch_progress.py
python3 tools/localization/validate.py --project config/project.json
python3 tools/localization/validate_translation.py --project config/project.json
python3 tools/localization/agent_batch.py status \
  --project config/project.json --mode incomplete --json
python3 tools/localization/opencode_farm.py status \
  --config config/opencode_farm.json --json
git diff --check
```

Required final state:

- All tests pass.
- Both validators report 0 errors.
- Farm is stopped.
- Queue has 0 reserved entries and no active batches.
- No runtime test artifacts are tracked.
- Documentation matches actual behavior.
- The suspicious `Color:Red` change remains isolated pending user instruction.

## Git Rules

- Do not revert unrelated user changes.
- Do not stage the catalog corruption with Piece 3.
- Do not commit, amend, pull, rebase, or push unless the user explicitly requests it.

## Suggested New-Session Prompt

```text
Read docs/piece3-session-handoff.md and continue from it using the strict context
budget. Audit only the listed invariants, make the smallest fixes needed, and
complete focused plus final verification. Do not read full catalogs or full diffs.
```

This prompt is preserved as historical session context and must not be used to
resume current work.

## See Also

- [Project Status](STATUS.md) for current documented status.
- [Gandalf Roadmap](gandalf-roadmap.md) for Piece 3 completion state.
- [Workflow](workflow.md) for current farm operations.
