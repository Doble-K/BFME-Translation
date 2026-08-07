# Packet 02: Process Identity

Status: `blocked` until Packet 01 is done.

## Goal

Make all schema 3 status and stop decisions depend on strong process identity and
ownership tokens. Preserve weak legacy matching only for schema 1/2 safe shutdown.

## Invariants

1. Stop never signals a recycled or unverifiable PID/process group.
2. Schema 3 never silently falls back to command-line matching.
3. A process-group leader exiting does not hide still-running owned children.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 312-469, 708-768, 894-1003,
  1223-1253.
- `tests/test_localization_tools.py`: lines 1509-1541, 1661-1758, 1867-1882,
  2115-2126.
- Packet 01 Result, queue files, and this packet.

Relevant symbols: `process_identity`, `legacy_supervisor_matches`,
`supervisor_is_alive`, `process_group_has_token`, `owned_process_group_is_alive`,
`slot_process_group_is_alive`, `active_state_process_groups`,
`terminate_recorded_process_groups`, `stop_farm`.

## Work

Audit fail-closed behavior. Do not improve compatibility by weakening schema 3.
Never send a signal unless identity/token evidence establishes ownership.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_does_not_signal_reused_supervisor_pid \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_requires_identity_and_tokens_in_current_state \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_keeps_exited_leader_until_group_finishes \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_stop_keeps_leases_if_supervisor_will_not_exit
```

## Exit Criteria

- Focused tests pass.
- `/proc` uncertainty fails closed for schema 3.
- Legacy handling remains limited to stopping schema 1/2 state.
- Update Result and unlock Packet 03.

## Result

Pass. Schema 3 status and stop paths remain fail-closed for missing or recycled
process identities and unverifiable coordinator ownership tokens. Legacy
command matching remains limited to schema 1/2 shutdown. Fixed the post-SIGTERM
wait path so an unverifiable `/proc` identity keeps leases unreleased instead of
being treated as a successful exit.

Focused verification passed:

```text
Ran 4 tests in 0.003s
OK
```
