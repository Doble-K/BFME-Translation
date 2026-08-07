# Dependencies

This document records dependencies visible in the project documentation. It is
not a package manifest and does not infer versions or platform support that the
documentation does not specify.

## Logical Dependencies

```text
project configuration + translation policy
                    |
source archive -> ingestion -> work catalog -> translation -> validation
                                                    |             |
                                                    +-------------+
                                                                  |
                                                        build -> package
                                                                  |
                                                        in-game verification
```

- Gandalf and localization commands depend on `config/project.json` for the
  selected project, paths, language settings, encoding, and outputs.
- Translation depends on the editable work catalog and the policy in
  `AGENTS.md`, `GLOSSARY.md`, and `rules/`.
- External agents depend on `agent_batch.py`; they do not access the complete
  work catalog directly.
- Agent concurrency depends on local leases and shared catalog locking. Leases
  coordinate only processes using the same checkout.
- Validation depends on a structurally valid catalog and unchanged protected
  syntax. Build and packaging depend on both mandatory validators reporting zero
  errors.
- Packaging depends on a generated `.str` resource. Manual in-game verification
  depends on the packaged `.big` archive and remains outside automated checks.
- The unattended farm depends on the batch gateway, a project-bound farm
  profile, detached process supervision, and runtime state under `.agent`.

## External Tools

| Dependency | Role | Documented assumptions |
| --- | --- | --- |
| Python 3 | Runs Gandalf, localization tools, validation, tests, build, and packaging workflows. | Exact supported versions are not documented. |
| `big4f` | Lists and extracts SAGE `.big` archives and supports package creation and verification. | A Linux binary path is shown in the workflow; support for other operating systems is not documented. |
| OpenCode | Executes bounded automated translation workflows and the optional unattended farm. | Provider and model may be user-selected; farm profiles define an explicit model matrix. |
| SAGE-compatible game runtime | Performs final behavioral verification of the generated package. | Installation is manual; supported game installation layouts are not documented. |

Ollama is not a dependency of the active Gandalf/OpenCode workflow. It is
mentioned only in connection with the legacy `ai_translate.py` provider.

## Runtime Assumptions

- The current production target uses English ROTWK 2.02 build 9.7.7 (9770) as
  reference input and Latin American Spanish as the target language. The
  operational workflow names the source archive
  `sources/englishpatch202_v9.7.7.big`.
- Generated string resources use Windows-1252 (`cp1252`) for SAGE compatibility.
- The established project format contains one selected `.str` resource.
- Concurrent workers that rely on leases share one checkout. Separate clones or
  machines require repository synchronization or an external shared queue.
- Generated packages are not installed automatically and require manual
  in-game testing.

## Build Dependencies

- `tools/localization/validate.py` and
  `tools/localization/validate_translation.py` are mandatory gates.
- `tools/localization/build.py` generates the configured `.str` resource from
  the validated work catalog.
- `tools/localization/pack.py` and `big4f` produce and verify the `.big` archive.
- Strict release builds cannot use source fallback. Source fallback is limited
  to explicitly requested partial debug builds.

Exact dependency versions, supported operating systems, installation
prerequisites, and environment setup remain undocumented.

## See Also

- [Architecture](ARCHITECTURE.md) for system boundaries and data flow.
- [Components](COMPONENTS.md) for component responsibilities and interfaces.
- [Workflow](workflow.md) for operational commands and sequencing.
- [Project Status](STATUS.md) for current limitations and unresolved issues.
