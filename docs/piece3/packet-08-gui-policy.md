# Packet 08: Gandalf Button Policy

Status: `blocked` until Packet 07 is done.

## Goal

Make farm-control enablement a small, directly tested policy, especially for
orphaned and changed-profile states.

## Invariant

An orphaned wave enables only stop. Unsafe start/resume/drain remain disabled,
while stopped valid profiles can start or resume.

## Allowed Context

- `gandalf.py`: lines 1379-1415.
- `tests/test_localization_tools.py`: lines 1944-1985 and 2498-2536.
- Packet 07 Result, queue files, and this packet.

Relevant symbol: `set_farm_buttons`. A small module-level pure helper is allowed
if it reduces nested GUI logic and makes the contract directly testable.

## Required Cases

- Orphaned active wave: only stop enabled.
- Stopped valid profile: start and resume enabled.
- Draining active supervisor: resume and stop enabled.
- Changed project: no drain/resume; stop remains enabled.
- Missing profile while active: stop remains enabled.
- Action running or globally disabled: all controls disabled.

## Focused Verification

Add one focused policy test, then run it together with:

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_opencode_farm_reports_orphaned_coordinators_as_active
python3 -m py_compile gandalf.py
```

## Exit Criteria

- All required cases are directly tested.
- Tk widgets are only adapters over the policy.
- Update Result and unlock Packet 09.

## Result

Pass. Extracted the farm button policy into the pure `farm_button_states`
helper; the Tk callback now only applies its returned states to widgets. The
focused test covers orphaned, stopped-valid, draining, changed-project,
missing-profile, and globally-disabled/action-running states.

Focused verification passed:

```text
Ran 2 tests in 0.001s
OK
```

`python3 -m py_compile gandalf.py` also passed.
