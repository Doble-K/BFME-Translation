# Packet 05: Detached Startup Rollback

Status: `blocked` until Packet 04 is done.

## Goal

Treat detached startup as a transaction: failure leaves no owned process, state,
control/ack artifact, or lease.

## Invariant

A failed startup handshake or unexpected supervisor error is completely rolled
back without touching unverified processes or unrelated leases.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 1005-1221.
- `tests/test_localization_tools.py`: lines 1470-1507, 2128-2150, and only the
  startup/final-cleanup portions of lines 2176-2321.
- Packet 04 Result, queue files, and this packet.

Relevant symbols: `cleanup_failed_detached_start`, `start_detached_locked`,
`start_farm`, `FarmSupervisor.prepare`, `FarmSupervisor.cleanup`.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_cleans_up_after_unexpected_error \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_cleans_up_when_detached_handshake_fails
```

## Exit Criteria

- Focused tests pass.
- Cleanup never releases leases before owned process termination is verified.
- Temporary test runtime directories contain no surviving processes/artifacts.
- Update Result and unlock Packet 06.

## Result

Pass. Detached startup failures terminate the owned supervisor before recorded
coordinator groups are checked, leases are released, and state/control/ack
artifacts are removed. Unexpected supervisor errors use the same cleanup path
through `finally`; no unverified process is signaled.

Focused verification passed:

```text
Ran 2 tests in 0.002s
OK
```
