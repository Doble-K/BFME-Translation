# Conventions

This document defines repository conventions derived from the documented
architecture, component boundaries, project status, and agent workflow as of
August 7, 2026. It records established practice only; unresolved and planned
capabilities must not be presented as current behavior.

## Architectural Conventions

- Treat the editable JSON work catalog as the localization source of truth.
- Treat extracted resources and source catalogs as reference inputs.
- Treat generated `.str` and `.big` files as build artifacts, never as
  authoritative localization data.
- Coordinate components through documented files and command-line interfaces.
  Do not assume a persistent service or database.
- Keep project-specific paths and language settings in `config/project.json`.
- Preserve the established single-resource project model until documented
  multi-resource support is implemented.
- Extend existing projects through compatible interfaces rather than requiring
  catalog migration.

## Component Boundaries

- Use Gandalf as the primary project setup and operation interface without
  making it the owner of catalog state or unattended-farm lifetime.
- Use `big4f` only at the SAGE archive boundary for listing, extraction, and
  packaging.
- Keep ingestion, translation, validation, build, packaging, and manual game
  verification as distinct stages.
- Require external translators and agents to return work through approved
  interfaces. They do not own catalog storage, builds, or publication.
- Do not assign installation or restoration responsibilities to packaging;
  those capabilities remain planned work.
- Do not treat roadmap components as established architecture.

## Catalog And State Conventions

- Preserve entry identity, revision safety, protected syntax, and catalog
  validity for every mutation.
- Use the active v1 states `pending`, `translated`, and `preserved`.
- Treat `needs_review` as a flag on translated work, not as a status.
- Reserve `preserved` for source text intentionally retained for engine or
  system compatibility.
- Treat `suggested`, `rejected`, and `reviewed` as experimental or future
  workflow concepts unless their schema contract is explicitly resolved.
- On source updates, preserve unchanged translations, invalidate translations
  whose source changed, record duplicate metadata, and retire missing entries
  rather than deleting them.
- Reject stale revisions and reserved records instead of overwriting concurrent
  work.

## Translation Work Conventions

- Follow an explicit user request or assigned task lane before selecting work
  from the generic queue.
- Process agent translations only through
  `tools/localization/agent_batch.py`.
- Never expose or edit a complete work catalog in an external translation
  agent's context.
- Use bounded batches with 20 entries by default and no more than 100 entries.
- Treat exported batch manifests as immutable. Edit only translation values in
  the response file.
- Use a unique worker label for every concurrently active agent in a shared
  checkout.
- Renew leases before expiration and release them when abandoning work.
- Do not assume local leases coordinate separate clones or machines; use
  repository synchronization or an external shared queue for that boundary.
- Preserve entry IDs, placeholders, control sequences, engine tags, hotkey
  letters, and all other protected syntax exactly.
- Mark agent-applied translations with `needs_review`; the flag does not block
  compilation by itself.
- Stop and escalate systematic policy, tooling, or format limitations instead
  of weakening validation or editing the full catalog.

## Validation Conventions

- Validate immediately after every translation batch and before every final
  build.
- Run both mandatory validators:

  ```bash
  python3 tools/localization/validate.py --project config/project.json
  python3 tools/localization/validate_translation.py --project config/project.json
  ```

- Require both validators to report zero errors before localized data proceeds.
- Correct validation failures; never bypass checks or ignore protected-token
  mismatches.
- Run regression tests for tool or schema changes in addition to, not instead
  of, the catalog validators.
- Revert only the affected translation modification when a batch cannot be
  validated.

## Build And Release Conventions

- Build only from a validated work catalog.
- Generate the configured `.str` resource with
  `tools/localization/build.py`, then package it with
  `tools/localization/pack.py`.
- Do not use source fallback for strict releases. Allow it only for an
  explicitly requested partial debug build.
- Verify that a packaged archive exists, is non-empty, and contains the expected
  string resource.
- Treat `releases/spanishpatch202.big` as the documented production output.
- Require manual in-game verification after packaging; package verification is
  not proof of correct game behavior.

## Change And Git Conventions

- Keep translation changes small, verified, and easy to rebase.
- Stage only files belonging to the verified unit. Do not use `git add .` or
  `git add -A`.
- Use conventional commit messages, such as
  `feat(localization): translate batch 01`.
- Synchronize translation work by rebasing before work, then rebasing, pushing,
  and pulling after a verified commit.
- OpenCode translation workers must not perform Git operations; a coordinator
  or human owns synchronization and commits for their batches.

## Documentation Conventions

- Distinguish established behavior, planned work, and unresolved questions.
- Do not infer implementation maturity when the documentation conflicts.
- Preserve documented unknowns until an authoritative decision resolves them.
- Record compatibility and migration impact when proposing architectural or
  schema changes.
- A tooling escalation must identify the reproducible problem, blocking impact,
  smallest reusable solution, compatibility impact, and required verification.
- Obtain approval before changes that alter catalog semantics, perform bulk
  migration, remove data, change generated package contents, or add an external
  service or dependency.

## Unresolved Conventions

Do not silently decide questions listed under **Missing Documentation** in
[`STATUS.md`](STATUS.md). That document is the canonical issue list.

## See Also

- [Architecture](ARCHITECTURE.md) for the boundaries these conventions protect.
- [Components](COMPONENTS.md) for component ownership.
- [Dependencies](DEPENDENCIES.md) for documented runtime and build assumptions.
- [Workflow](workflow.md) for executable procedures.
- [Project Status](STATUS.md) for unresolved decisions.
