# Architecture

This document records the repository architecture supported by project
documentation inspected through August 7, 2026. It describes system boundaries
and data flow, not implementation details. Where the documentation conflicts or
describes planned work, that uncertainty is stated explicitly.

## System Purpose

BFME-Translation is a multilingual localization toolkit for games built on the
SAGE engine. Its current production target is Latin American Spanish for *The
Lord of the Rings: The Battle for Middle-earth II: The Rise of the Witch-king*
(ROTWK) 2.02, using the English 9.7.7 build 9770 as its reference.

The toolkit supports this lifecycle:

```text
SAGE .big archive
    -> extracted .str resource
    -> source JSON catalog
    -> editable work catalog
    -> bounded translation and review operations
    -> validation
    -> generated .str resource
    -> packaged .big archive
    -> manual in-game testing
```

The same workflow is intended to support other languages and SAGE projects.
The documented current project uses a single string resource; multi-resource
projects are roadmap work and are not part of the established architecture.
Logical and external dependencies are summarized in
[`DEPENDENCIES.md`](DEPENDENCIES.md).

## Architectural Boundaries

The system is divided into five major boundaries:

1. **Project setup and operation:** `gandalf.py` creates or opens localization
   projects and exposes graphical or terminal workflows.
2. **Localization pipeline:** scripts under `tools/localization/` extract,
   initialize, update, edit, validate, compare, build, and package localization
   data.
3. **Translation execution:** humans or external agents translate bounded work
   units. Agents exchange data only through `agent_batch.py` batch files.
4. **Project data and policy:** project configuration selects paths and language
   settings; catalogs hold localization state; glossary and rule files define
   translation policy and protected syntax.
5. **SAGE archive integration:** `big4f` lists, extracts, and packages `.big`
   archives. Generated packages still require manual testing in the game.

These boundaries are coordinated through files and command-line interfaces.
The documentation does not describe a persistent service or database.

## Source Of Truth

The editable JSON work catalog is the localization source of truth. Extracted
source files and source catalogs provide reference input. Generated `.str` and
`.big` files are build artifacts and must not be edited as authoritative data.

`config/project.json` identifies the current project's source archive and string
files, work catalog, generated outputs, target language, encoding, and output
header. The current documented target encoding is Windows-1252 (`cp1252`) for
SAGE compatibility.

Catalog records follow the active v1 state model:

```text
pending -> translated

preserved
```

`needs_review` is a flag on translated work rather than a separate status.
`preserved` records intentionally retain source text for engine or system
compatibility. The documented `suggested`, `rejected`, and `reviewed` states
belong to an experimental or future proposal workflow and are not required by
v1.

## Project Setup And Source Ingestion

Gandalf is the primary project entry point. It can detect `.big` files, list
their contents, select a string resource, and create a work catalog and project
configuration. Direct command-line ingestion remains available.

The documented ingestion stages are:

1. `big4f` verifies and extracts the selected `.str` archive member.
2. `extract.py` converts the encoded `.str` resource into a source JSON catalog.
3. Gandalf initializes the editable work catalog and project configuration.
4. `preprocess.py` preserves documented system entries such as `LETTER:*`,
   `NUMBER:*`, and `Version:*`.
5. Structural and protected-token validators establish a valid baseline.

When a reference source changes, `update.py` synchronizes it into the existing
work catalog. Documented update behavior preserves unchanged translations,
invalidates translations whose source changed, records duplicate metadata, and
retires missing entries rather than deleting them.

## Translation Execution

Manual translation is available through the terminal editor and Gandalf. Both
are documented as sharing a transactional per-entry editing backend. A save
reloads current catalog state under a shared lock, rejects reserved entries, and
rejects stale revisions instead of overwriting concurrent work.

External agents must not read a complete catalog. `agent_batch.py` is the only
documented exchange boundary for agent translation:

```text
work catalog
    -> export immutable bounded batch + editable response
    -> agent edits translation values only
    -> validated atomic apply
    -> work catalog
```

The default batch size is 20 entries and the documented maximum is 100. The
`incomplete` selection mode includes pending entries and exact source
placeholders recorded by the import pipeline. Application verifies batch
identity, lease ownership, immutable metadata, response completeness, entry
identity and revision, eligibility, non-empty translations, and protected
tokens before changing the catalog. Agent-applied translations receive the
`needs_review` flag; translated entries are not otherwise required to carry it.

Translation policy is supplied by `AGENTS.md`, `GLOSSARY.md`, and files under
`rules/`. Engine identifiers, format placeholders, control sequences, tags, and
hotkey letters form protected syntax and cannot be translated or silently
altered.

## Concurrency And Isolation

Concurrent agents sharing one checkout coordinate through leased reservations.
Each active worker requires a unique label, and disjoint leases prevent workers
from receiving overlapping IDs. Leases are local to the checkout; they do not
coordinate agents operating in separate clones or on separate machines.

Batch application and manual edits use catalog locking and stale-state checks to
avoid lost updates. This allows manual correction and agent translation to run
concurrently when they operate on different, unreserved records.

The unattended OpenCode farm adds a supervisor above bounded translation
workers. Its documented architecture includes:

- explicit model profiles in `config/opencode_farm.json`;
- detached supervisor lifecycle controls for start, status, drain, resume, and
  stop;
- runtime state, control, acknowledgement, and logs under `.agent`;
- a dedicated coordinator that cannot export or apply batches;
- exact worker-label scoping for lease operations;
- project and catalog identity frozen for the duration of a farm run;
- Gandalf polling the same state so its window does not own farm lifetime.

The roadmap marks Piece 3, farm controls in Gandalf, as complete. The earlier
`piece3-session-handoff.md` is retained as a historical pre-completion snapshot
and is not a current status source. Implementation was not inspected for this
documentation review; current verification evidence remains recorded in
[`STATUS.md`](STATUS.md).

## Validation Boundary

Validation is a mandatory gate after each translation batch and before a final
build:

- `validate.py` checks catalog structure.
- `validate_translation.py` checks protected-token integrity.

Both validators must report zero errors. Historical duplicate or orphan
warnings may remain visible, but documentation does not treat every such warning
as a blocking error. Tool or schema changes additionally require the regression
test suite; tests do not replace either catalog validator.

Validation failures must be corrected rather than bypassed. A systematic format
or tooling limitation that makes translation unsafe must stop the affected batch
and be escalated instead of weakening validation or editing the full catalog.

## Build And Packaging

The strict release path converts the validated catalog to `.str` with
`build.py`, then packages it into `.big` with `pack.py`. Packaging verifies that
the output exists, is non-empty, and contains the expected string resource. The
documented current output is `releases/spanishpatch202.big`.

Source fallback is allowed only for an intentionally partial debug build. It is
not permitted for a release. Generated packages are not installed automatically
and require manual in-game verification.

The roadmap proposes a stronger distinction between atomic DEBUG snapshots and
optional RELEASE artifacts, including manifests, retained history, and install
or restore operations. Those capabilities are planned Pieces 4, 5, and 8 and
must not be treated as current architecture.

## Configuration And Policy

Project-specific runtime data is separated from translation policy:

- `config/project.json` defines the selected localization project and paths.
- `config/opencode_farm.json` defines the unattended farm's model matrix.
- `opencode.json` selects the project-local OpenCode agent, loads translation
  instructions, disables sharing, and limits retained tool output.
- `AGENTS.md` defines safe batch, validation, and synchronization procedures.
- `GLOSSARY.md` defines approved and pending terminology.
- `rules/translation_rules.md` defines target-language style and syntax rules.
- `rules/protected_tokens.json` enumerates protected token classes and patterns.

The architecture keeps catalogs out of agent context while allowing local
Python processes to parse them. Bounded response files are the intended context
interface for translation agents.

## Extensibility

The project configuration is intended to be the interface for additional SAGE
games, mods, languages, and string resources without hard-coded language
assumptions. Conditional tools support source updates, comparisons, hotkey
normalization, migration of old schemas, and experimental review operations.

The documented roadmap for new projects introduces separate identities for
multiple `.str` resources and entries based on resource, engine ID, and
occurrence. Existing projects are intended to retain their single-resource
format through an adapter rather than a catalog migration. This is future
architecture and is not documented as implemented.

## Security And Failure Model

The architecture protects localization integrity rather than providing a
general security sandbox. Its documented safeguards include:

- no full-catalog access for translation agents;
- a fixed localization command allowlist for translation workers;
- immutable batch manifests and atomic application;
- lease ownership and entry revision checks;
- shared locking for concurrent catalog writes;
- exact worker scoping during farm cleanup;
- validation of protected runtime syntax;
- atomic writes and retention of retired or duplicate history where documented.

The principal failure boundaries are stale batches, expired leases, modified
manifests, conflicting manual edits, invalid protected tokens, incomplete
translations, invalid source input, build failures, and package verification
failures. Documentation requires these failures to stop mutation or publication
rather than proceed with a fallback, except for explicitly requested partial
debug builds.

## Open Questions

Current documentation gaps and unresolved decisions are maintained in
[`STATUS.md`](STATUS.md) to avoid duplicating a changing issue list here.

## See Also

- [Components](COMPONENTS.md) for responsibilities and interfaces.
- [Dependencies](DEPENDENCIES.md) for logical, runtime, external, and build
  dependencies.
- [Conventions](CONVENTIONS.md) for established repository rules.
- [Workflow](workflow.md) for operational commands.
- [Project Status](STATUS.md) for current maturity and unresolved issues.
- [Gandalf Roadmap](gandalf-roadmap.md) for planned lifecycle work.
