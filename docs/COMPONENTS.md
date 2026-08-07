# Components

This document identifies the repository's documented architectural components,
their responsibilities, and their interfaces. It intentionally describes
component boundaries rather than implementation details.

## Component Map

```text
                         translation policy
                                  |
                                  v
SAGE archive -> ingestion -> editable work catalog -> translation and review
                    |                 |                       |
                    |                 v                       |
                    |             validation <---------------+
                    |                 |
                    |                 v
                    +-----------> build and package -> SAGE archive
                                           |
                                           v
                                  manual in-game testing
```

`config/project.json` supplies project-specific paths and language settings
across the pipeline. The editable work catalog is the source of truth; extracted
resources and generated packages are inputs and artifacts, respectively.

## Gandalf Project Interface

**Entry point:** `gandalf.py`

Gandalf is the primary project setup and operation interface. It creates or
opens localization projects, detects SAGE archives, supports resource selection,
and exposes graphical or terminal workflows. It also provides access to manual
translation operations.

Gandalf coordinates other components through files and command-line tools. It
does not replace the work catalog as the source of truth, and its window does
not own the lifetime of an unattended translation farm.

The exact boundary between currently available Gandalf features and several
roadmap features remains unresolved in the project documentation.

## Project Configuration

**Primary file:** `config/project.json`

Project configuration identifies the selected source archive and string
resource, source and work catalogs, generated outputs, source and target
languages, output encoding, and output header. The documented production target
uses Windows-1252 (`cp1252`) output for SAGE compatibility.

Configuration is the intended extension interface for additional games, mods,
and languages. The established architecture supports one string resource per
project; multi-resource identity and compatibility adapters are planned work.

## SAGE Archive Adapter

**Tool:** `big4f`

The archive adapter provides the boundary between repository workflows and SAGE
`.big` archives. It lists archive contents, extracts the selected `.str`
resource during ingestion, and packages generated resources for release.

Packaging must verify that the resulting archive exists, is non-empty, and
contains the expected string resource. Installation and restoration are not
established responsibilities of this component.

## Source Ingestion Pipeline

**Tools:** `extract.py`, `preprocess.py`, and `update.py` under
`tools/localization/`

The ingestion pipeline converts an extracted, encoded `.str` resource into a
source JSON catalog and initializes localization state. Preprocessing preserves
documented system entries that must remain unchanged.

When reference text changes, the update component synchronizes it into an
existing work catalog. Its documented contract is to preserve unchanged
translations, invalidate translations whose source changed, record duplicate
metadata, and retire missing entries rather than delete them.

The source catalog is reference input and is not the editable localization
source of truth.

## Work Catalog

The editable JSON work catalog is the central state component and the source of
truth for localization. Records use the active v1 state model:

```text
pending -> translated

preserved
```

`needs_review` is a flag on translated work. `preserved` identifies source text
retained for engine or system compatibility. Proposal states such as
`suggested`, `rejected`, and `reviewed` are experimental or future workflow
concepts and are not required by v1.

All mutations must preserve entry identity, protected syntax, revision safety,
and catalog validity. Generated `.str` and `.big` files must not be edited as
authoritative localization data.

## Manual Translation Backend

**Interfaces:** Gandalf and the terminal editor

Manual translation interfaces share a documented transactional per-entry
editing boundary. A save reloads current catalog state under a shared lock and
rejects reserved records or stale revisions rather than overwriting concurrent
work.

This component may operate concurrently with agent translation when the edits
address different, unreserved records.

## Agent Batch Gateway

**Tool:** `tools/localization/agent_batch.py`

The batch gateway is the only documented catalog exchange boundary for external
translation agents. Agents must not read or edit the complete work catalog.

Export creates an immutable bounded batch, a minimal editable response, a unique
batch identity, and a leased reservation. Agents edit only translation values in
the response. Apply validates the response and updates the catalog atomically.

The default batch contains 20 entries and the documented maximum is 100. Apply
checks batch and project identity, lease ownership, immutable metadata, response
completeness, entry identity and revision, current eligibility, non-empty
translations, and protected-token integrity. Applied agent translations receive
the `needs_review` flag.

The gateway also provides lease renewal, release, and aggregate status
operations. Leases coordinate workers only within a shared checkout; separate
clones require repository synchronization or an external shared queue.

## Translation Policy

**Files:** `AGENTS.md`, `GLOSSARY.md`, and files under `rules/`

Policy files define target-language style, approved terminology, protected
syntax, batch procedures, validation requirements, and synchronization rules.
They are inputs to human and agent translation rather than localization data.

Engine identifiers, placeholders, control sequences, tags, and hotkey letters
are protected and cannot be translated or silently altered. A systematic policy
or format limitation must stop the affected batch and be escalated instead of
being bypassed.

## Validation Gate

**Tools:** `tools/localization/validate.py` and
`tools/localization/validate_translation.py`

Validation is a mandatory boundary after each translation batch and before a
final build. The structural validator checks catalog integrity, while the
translation validator checks protected-token integrity. Both must report zero
errors before localized data can proceed.

Regression tests are additionally required for tool or schema changes, but they
do not replace either catalog validator. Validation failures block mutation or
publication and must be corrected rather than ignored.

## Build Component

**Tool:** `tools/localization/build.py`

The build component converts a validated work catalog into the encoded `.str`
resource selected by project configuration. Strict release builds may not use
source fallback. Fallback is permitted only for an explicitly requested partial
debug build.

The generated resource is a build artifact and requires packaging before it can
be tested in the game.

## Packaging Component

**Tool:** `tools/localization/pack.py`

The packaging component uses the SAGE archive adapter to place the generated
`.str` resource into a `.big` archive and verifies the package. The documented
production output is `releases/spanishpatch202.big`.

Packaging does not establish correctness in the game. The output still requires
manual in-game testing and is not installed automatically.

## Unattended Translation Farm

**Configuration:** `config/opencode_farm.json`

The documented farm places a detached supervisor above bounded translation
workers. It defines explicit model profiles, lifecycle controls, runtime state
under `.agent`, worker-label scoping, and frozen project and catalog identity for
the duration of a run. A dedicated coordinator supervises the run but cannot
export or apply translation batches; workers continue to use the batch gateway.

The documented lifecycle includes start, status, drain, resume, and stop. The
roadmap marks Gandalf farm controls complete; current verification evidence is
tracked separately in `STATUS.md`.

## External Translation Workers

Human translators and automated agents are external execution components. They
receive policy plus bounded work, produce translations, and return those results
through an approved interface. They do not own catalog storage, validation,
builds, or publication.

OpenCode translation workers must not perform Git operations. Repository
synchronization and commits remain coordinator or human responsibilities.

## Manual Game Verification

Manual in-game testing is the final external verification component. It consumes
the packaged `.big` archive and checks behavior that structural, token, build,
and package validation cannot establish. No documented automated component
installs the package or replaces this verification step.

## Planned Components

The following capabilities are documented as roadmap work and must not be
treated as established components:

- atomic DEBUG snapshots with manifests and retained history;
- optional RELEASE artifact management;
- package installation and restoration;
- native multi-resource project identity and processing;
- broader new-project and source-update workflows where documentation marks
  them as incomplete.

Existing single-resource projects are intended to remain compatible through an
adapter rather than a catalog migration, but that design is future architecture.

## See Also

- [Architecture](ARCHITECTURE.md) for system boundaries and data flow.
- [Dependencies](DEPENDENCIES.md) for relationships and external requirements.
- [Workflow](workflow.md) for component operation.
- [Project Status](STATUS.md) for capability maturity and documentation gaps.
- [Gandalf Roadmap](gandalf-roadmap.md) for planned components.
