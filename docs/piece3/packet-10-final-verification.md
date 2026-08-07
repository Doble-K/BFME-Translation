# Packet 10: Final Verification

Status: `blocked` until Packet 09 is done.

## Goal

Run final verification exactly once, make only failure-driven corrections, and
confirm documentation matches behavior.

## Allowed Context

- Results from Packets 01-09.
- Files named by a failing command, limited to the relevant function/test.
- `README.md`, `config/gandalf.example.json`, `docs/gandalf-roadmap.md`, and
  `docs/workflow.md` only for behavior/documentation consistency.
- Queue files and this packet.

Do not inspect complete catalogs or full diffs. Validators may parse catalogs
internally; that does not authorize opening them.

## Verification

Run once after `git diff --check` passes:

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

If one command fails, fix only the direct cause, rerun that command, then rerun
the complete sequence once after all individual commands pass.

## Required Final State

- All tests and compilation pass.
- Both validators report 0 errors; historical duplicate-ID warnings are acceptable.
- Farm reports stopped with no supervisor or leases.
- Queue reports zero reserved entries and no active batches.
- No runtime test artifact is tracked.
- Documentation matches implemented commands and safety behavior.
- `Color:Red` remains untouched and excluded.

## Exit Criteria

Fill Result with exact pass counts and status summaries. Mark Packet 10 `done`.
Do not commit or push unless explicitly requested.

## Result

Status: done
Changed: docs/piece3/QUEUE.md, docs/piece3/packet-10-final-verification.md: final verification result
Behavior: Final lifecycle, farm, queue, catalog, and documentation checks are consistent.
Tests: unittest 92 passed; py_compile passed; validate.py 0 errors; validate_translation.py 0 errors; queue reserved 0 and active batches 0; farm stopped; git diff --check passed
Risks: 65 historical duplicate-ID warnings remain; no validation errors.
Next: none
