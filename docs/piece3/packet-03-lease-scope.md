# Packet 03: Frozen Identity And Lease Scope

Status: `blocked` until Packet 02 is done.

## Goal

Ensure profile/project edits cannot redirect cleanup and that cleanup releases
only exact workers owned by the farm.

## Invariants

1. Catalog identity and worker scope are frozen into run state.
2. Cleanup cannot be redirected to another catalog by later edits.
3. Lease release uses exact worker labels, never prefix matching.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 483-542, 658-670, 793-927.
- `tools/localization/agent_batch.py`: lines 646-695.
- `tests/test_localization_tools.py`: lines 1112-1468, 1884-1942,
  2045-2113, reading only named tests below.
- Packet 02 Result, queue files, and this packet.

Relevant symbols: `validate_state_identity`, `state_catalog`, `state_prefixes`,
`state_worker_count`, `coordinator_worker_names`, `release_farm_leases`,
`FarmSupervisor.state_payload`, `FarmSupervisor.close_finished_slot`,
`release_catalog_workers`.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_agent_batch_releases_only_exact_worker_labels \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_releases_frozen_catalog_and_prefixes \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_stop_uses_recorded_state_after_project_change \
tests.test_localization_tools.LocalizationToolTests.test_supervised_project_scope_rejects_other_or_changed_project
```

## Exit Criteria

- Focused tests pass.
- No broad prefix release remains in the farm cleanup path.
- Legacy fallback never selects a changed project/catalog.
- Update Result and unlock Packet 04.

## Result

Pass. Cleanup resolves the catalog, coordinator prefixes, and worker count from
the recorded state, so profile and project edits cannot redirect an active run.
Farm cleanup calls the exact worker-label release path; broad prefix release
remains outside the farm cleanup path for legacy tooling compatibility.

Focused verification passed:

```text
Ran 4 tests in 0.279s
OK
```
