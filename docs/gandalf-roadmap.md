# Gandalf Translation Lifecycle Roadmap

This roadmap divides the agreed Gandalf expansion into independently testable
pieces. The existing ROTWK catalog remains compatible and is not migrated or
rewritten as part of this work.

Checkboxes record roadmap status, not fresh verification evidence. Current
documentation gaps are tracked in [`STATUS.md`](STATUS.md).

## Progress

- [x] Baseline checkpoint: `b96d5fa`.
- [x] Piece 1: project-bound farm.
- [x] Piece 2: safe manual editing.
- [x] Piece 3: farm controls in Gandalf.
- [ ] Piece 4: snapshot DEBUG packages.
- [ ] Piece 5: DEBUG installation.
- [ ] Piece 6: new multi-resource projects.
- [ ] Piece 7: source version updates.
- [ ] Piece 8: optional RELEASE.

## Product Rules

- A project may remain in progress indefinitely and produce DEBUG packages.
- Human review is optional and never blocks compilation by itself.
- RELEASE is optional and requires a complete queue, no active leases, strict
  validation, and a build without source fallback.
- Manual work and the farm may run together, but Gandalf must reject edits to
  reserved entries.
- Existing projects keep their current single-resource format.
- New projects may include every `.str` resource found in a source `.big`.
- Project profiles may target any language and select their own instructions,
  glossaries, and protected-token rules.

## Piece 1: Project-Bound Farm

Bind every supervised OpenCode process to the canonical project configuration
selected by Gandalf. Propagate the project path and revision digest below the LLM,
reject any tool invocation for another project, and pass the exact project to
coordinators and workers. Do not expose farm launch in Gandalf until the
wrong-project regression tests pass.

## Piece 2: Safe Manual Editing

Create one transactional edit backend for the Gandalf GUI and terminal editor.
Read user input without holding the catalog lock, then lock, reload, reject
reserved entries, compare the expected entry hash, validate tokens and hotkeys,
and update only the latest catalog state. Add explicit actions to keep
`needs_review`, mark reviewed, preserve source text intentionally, or return an
entry to the translation queue.

## Piece 3: Farm Controls In Gandalf

Load an existing project configuration as the source of truth and add a live
queue dashboard. Support start, reconnect, drain after the current wave,
immediate stop with lease release, resume, status, and logs. Farm processes stay
detached when Gandalf closes. Runtime model profiles remain local and separate
from portable project translation settings.

Implemented with a detached supervisor, atomic `drain`/`resume` control file,
structured status snapshots, automatic GUI reconnection, queue and coordinator
status, and direct access to per-coordinator logs. Immediate stop terminates the
verified process groups before releasing only the exact configured worker
leases. Runtime paths are anchored to the canonical profile under `.agent`, so
profile edits cannot bypass lifecycle locking or strand a running supervisor.

## Piece 4: Snapshot DEBUG Packages

Copy a coherent catalog snapshot while holding the shared lock briefly, then
release the lock before validation and packaging. DEBUG permits source fallback,
uses a separate output path, optionally inserts the configured visual marker,
updates one stable test package, and retains timestamped history plus a manifest.
Package publication must be atomic and preserve the previous valid artifact on
failure.

## Piece 5: DEBUG Installation

Allow an optional project-specific test installation path. Back up the existing
package before copying, verify the installed bytes, and provide an explicit
restore operation. External paths always require confirmation.

## Piece 6: New Multi-Resource Projects

For newly created projects, preserve each `.str` archive member as a separate
resource and assign opaque internal entry keys without modifying engine IDs.
Identity is resource plus ID plus occurrence, so equal IDs in different files do
not collide. Build every selected resource back to its original archive member
and package them together. Legacy projects continue through the existing
single-resource adapter without catalog migration.

## Piece 7: Source Version Updates

This piece extends the documented basic single-resource `update.py` behavior
into the full Gandalf lifecycle. Stage and parse a new source archive before
modifying live data. Require a drained farm and zero leases to apply an update.
Preserve unchanged
translations, return changed sources to pending while retaining old text in
history, add new entries, retire removed entries, and restore reappearing
entries. Bind the update plan to the catalog and source hashes to reject stale
application.

## Piece 8: Optional RELEASE

Enable RELEASE only with zero incomplete entries and zero active leases. Run
both validators and a strict build without fallback, then publish atomically to
the configured release path. `needs_review` remains a warning, not a gate. Store
the catalog hash in the package manifest and mark the release stale after any
later correction.

## Required Regression Coverage

- A farm selected for project B cannot read, lease, apply, release, or validate
  project A.
- The current ROTWK catalog remains byte-compatible with its existing tools.
- Concurrent manual and farm updates to different entries are both preserved.
- Reserved and stale manual edits are rejected without catalog changes.
- DEBUG can be built during active translation and never overwrites RELEASE.
- Drain preserves the current wave; immediate stop returns its leases.
- Target-language context comes only from the selected project profile.
- Equal IDs in different `.str` resources do not collide in new projects.
- Source updates preserve unchanged manual corrections and are idempotent.
- RELEASE accepts translated entries carrying `needs_review`.
- DEBUG installation backup and restore reproduce the original bytes.

## See Also

- [Project Status](STATUS.md) for current capability maturity and open issues.
- [Architecture](ARCHITECTURE.md) for established boundaries.
- [Components](COMPONENTS.md) for established and planned components.
- [Dependencies](DEPENDENCIES.md) for runtime and build requirements.
- [Workflow](workflow.md) for current operational procedures.
