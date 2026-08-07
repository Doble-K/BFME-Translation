---
description: Manage the OpenCode translation farm supervisor from opencode.
agent: director
---

Manage the detached translation farm through the same supervisor that
`gandalf.py` invokes. Interpret `$ARGUMENTS` as `ACTION`, where ACTION is one
of `start`, `status`, `drain`, `resume`, `stop`, or `clean`. For `start` you
may append `--detach` to run detached or `--dry-run` to preview without
launching processes.

The farm is launched by `gandalf.py`, which calls
`tools/localization/opencode_farm.py --config config/opencode_farm.json`.
Execute the same supervisor command from the repository root, for example:

- `/farm start --dry-run`
  -> `python3 tools/localization/opencode_farm.py start --config config/opencode_farm.json --dry-run`
- `/farm start --detach`
  -> `python3 tools/localization/opencode_farm.py start --config config/opencode_farm.json --detach`
- `/farm status`
  -> `python3 tools/localization/opencode_farm.py status --config config/opencode_farm.json`
- `/farm drain`, `/farm resume`, `/farm stop`, `/farm clean` follow the same
  pattern.

This command only supervises the farm. Never translate entries, never export
or apply batches yourself, never open `config/opencode_farm.json` for other
purposes, and never commit. Report the supervisor output and farm state to the
user.
