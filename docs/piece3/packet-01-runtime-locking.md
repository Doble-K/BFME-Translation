# Packet 01: Runtime Locking

Status: `ready`

## Goal

Establish that profiles sharing runtime state cannot launch duplicate supervisors,
that profile path edits cannot hide an active supervisor, and that deleted/invalid
profiles allow recovery but never authorize a fresh start.

## Invariants

1. Two profiles sharing one state file cannot start two supervisors.
2. Editing runtime paths cannot hide or strand an active supervisor.
3. Runtime fallback supports status/stop only, not fresh start.

## Allowed Context

- `tools/localization/opencode_farm.py`: lines 43-287, 545-615, 1101-1221.
- `tests/test_localization_tools.py`: lines 1760-1865 and the concurrent-start
  portion of lines 2176-2321.
- `docs/piece3/README.md`, `QUEUE.md`, and this packet.

Relevant symbols: `profile_runtime_root`, `runtime_anchor_path`,
`validate_runtime_paths`, `load_runtime_anchor`, `load_farm_runtime`,
`load_farm_config_with_runtime_fallback`, `bind_runtime_paths`,
`exclusive_file_lock`, `farm_lifecycle_lock`, `prepare_start_locked`, `start_farm`.

Do not inspect process termination, lease cleanup, controls, Gandalf, or catalogs.

## Work

Audit the invariants against existing code and tests. Add or change only the
smallest code/test needed. In particular, verify that exclusion is keyed strongly
enough when two different profiles point at the same state.

## Focused Verification

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_runtime_paths_survive_profile_edits \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_rejects_unsafe_or_aliased_runtime_paths \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_runtime_fallback_survives_deleted_profile
```

Also run only the concurrent-start test if it exists independently. Do not run the
entire detached lifecycle smoke test merely to test this packet.

## Exit Criteria

- Focused tests pass.
- Fresh start still requires a valid current profile.
- No real farm was started and no runtime artifact remains.
- Update Result and unlock Packet 02.

## Result

Pass. Audited runtime anchoring and lifecycle locking. Profile-specific locks
are followed by a lock derived from the anchored, resolved state file, so
profiles sharing state cannot launch duplicate supervisors. Runtime fallback
continues to recover status/stop data without authorizing a fresh start.

Focused verification passed:

```text
Ran 3 tests in 0.059s
OK
```

No code change was required. No real farm was started and no runtime artifact
was left behind. No independent concurrent-start test exists in the permitted
test range.
