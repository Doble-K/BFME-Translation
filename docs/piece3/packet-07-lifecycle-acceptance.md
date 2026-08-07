# Packet 07: Lifecycle Acceptance

Status: `blocked` until Packet 06 is done.

## Goal

Run one end-to-end acceptance test for backend lifecycle integration.

## Allowed Context

- `tests/test_localization_tools.py`: lines 2176-2321.
- Production functions may be read only when a failure names them; read at most
  200 lines around that function.
- Results from Packets 01-06, queue files, and this packet.

Do not redesign the lifecycle or broaden timeouts to hide races.

## Work

Run the smoke test first. If it passes, make no production change. If it fails,
identify the first causal failure, change the smallest implicated function, and
rerun this test. Do not run the full suite.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_detached_lifecycle_smoke
```

The test must use only its fake temporary `opencode`. Confirm it ends with zero
leases and no supervisor/coordinator process.

## Exit Criteria

- Smoke test passes without arbitrary sleep inflation.
- No temporary process or lease survives.
- Update Result and unlock Packet 08.

## Result

Pass. The fake temporary `opencode` completed the detached start, concurrent
start exclusion, drain, resume, and stop lifecycle. The smoke test finished
with no reserved leases or surviving supervisor/coordinator processes.

Focused verification passed:

```text
Ran 1 test in 3.452s
OK
```
