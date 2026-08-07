# Packet 04: Drain And Resume Protocol

Status: `blocked` until Packet 03 is done.

## Goal

Make drain/resume commands atomic, attributable to one supervisor, and explicitly
acknowledged.

## Invariants

1. Drain finishes the current wave and starts no new wave.
2. Receipt is confirmed for the exact command and supervisor.
3. Resume cancels drain or starts exactly one detached supervisor after drain.
4. Claiming one command cannot delete a newer command.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 599-699, 828-846, 1018-1088,
  1279-1329.
- `tests/test_localization_tools.py`: lines 1543-1636 and 1987-2043.
- Packet 03 Result, queue files, and this packet.

Relevant symbols: `save_control`, `load_control`, `wait_for_control_ack`,
`FarmSupervisor.apply_control`, `FarmSupervisor.run`, `drain_farm`, `resume_farm`.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_drain_and_resume_write_control \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_draining_does_not_launch_new_cycles \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_resume_restarts_inactive_supervisor \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_control_claim_does_not_delete_newer_command \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_acknowledges_control_in_state
```

## Exit Criteria

- Focused tests pass.
- Ack binds both control ID and supervisor PID.
- Inactive resume remains serialized by the lifecycle lock.
- Update Result and unlock Packet 05.

## Result

Pass. Drain and resume commands are claimed with an atomic rename, validated
against the exact supervisor and project revision, and acknowledged by both
control ID and supervisor PID. A newer command remains queued when an older
claimed command is processed. Inactive resume remains inside the lifecycle
lock.

Focused verification passed:

```text
Ran 5 tests in 0.005s
OK
```
