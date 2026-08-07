# Packet 06: Status And Recovery

Status: `blocked` until Packet 05 is done.

## Goal

Provide useful status and safe stop when the profile is invalid/deleted or the
supervisor exited while owned coordinator groups remain.

## Invariants

1. Invalid/deleted profiles allow status and stop, not fresh start.
2. Owned orphan coordinator groups keep farm status active and stoppable.
3. Project changes disable unsafe controls without redirecting cleanup.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 227-287 and 1223-1390.
- `tests/test_localization_tools.py`: lines 1638-1660, 1829-1865, 1944-1985,
  2073-2113.
- Packet 05 Result, queue files, and this packet.

Relevant symbols: `load_farm_config_with_runtime_fallback`, `active_state_process_groups`,
`stop_farm`, `resume_farm`, `farm_status`.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_status_returns_structured_queue \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_runtime_fallback_survives_deleted_profile \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_reports_orphaned_coordinators_as_active \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_stop_uses_recorded_state_after_project_change
```

## Exit Criteria

- Focused tests pass.
- Orphaned state is active but not reported safely controllable.
- Runtime fallback cannot authorize start/resume requiring a valid profile.
- Update Result and unlock Packet 07.

## Result

Pass. Runtime fallback preserves the anchored state for status and stop, marks
the profile unavailable, and blocks fresh starts and inactive resumes. Owned
orphan coordinator groups remain active in status and can be stopped, while
project changes use the recorded catalog and worker scope for cleanup.

Added an explicit fresh-start rejection for runtime fallback configurations;
`--dry-run` remains non-mutating.

Focused verification passed:

```text
Ran 4 tests in 0.059s
OK
```
