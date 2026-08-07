# AI System State

Current-state snapshot of the generic AI development framework. No product milestones or tasks.

## Framework Version

**v0.9-pre-extraction**

Development is pre-migration. The generic AI system lives interleaved with
product-specific code in the same repository. Formal extraction into
separate layers has not begun.

## Status

Operational in monorepo mode. All orchestration, tooling, agents, and
documentation coexist with the product implementation.

## Active Generic Agents

| Agent Role | Purpose |
|---|---|
| Director | Overall orchestration and task delegation |
| Planner | Task sequencing and dependency management |
| Architect | System design and interface definition |
| Explorer | Codebase analysis and context gathering |
| Worker Small | Bounded implementation tasks (model: mimo-v2.5) |
| Worker Medium | Complex implementation tasks (model: deepseek-v4-flash) |
| Worker Large | Exceptional implementation tasks (model: gpt-5.6-luna) |
| Worker | Legacy alias for Worker Small |
| Builder | Compilation and packaging of artifacts for distribution |
| Git Director | Commit, staging, and synchronization operations |

All agents currently carry product-specific knowledge embedded in their
instructions. None are purely generic yet.

## Model Strategy

Worker-based model selection. The Director routes tasks to the appropriate
worker by capability class:

- **Worker Small** (`opencode-go/mimo-v2.5`): Default for bounded implementation,
  routine tasks, validation, exploration.
- **Worker Medium** (`opencode-go/deepseek-v4-flash`): Used when task complexity
  justifies deeper reasoning (multi-step validation, cross-file analysis).
- **Worker Large** (`opencode-go/gpt-5.6-luna`): Requires explicit human
  authorization. Reserved for exceptional tasks exceeding Small/Medium capability.

Model selection is independent of product domain. No automatic escalation.

## Approval Policy

Human approval is the general rule for all changes, product operations,
state updates, destructive actions, and escalations. Validation may
inform a recommendation but does not auto-approve any action.

Everything else requires explicit user approval before execution.

## State-Transition Policy

Generic state transitions: `proposed → approved → in_progress → completed/rejected`.
State snapshots are updated only after approval. Product-specific state
machines may add intermediate states but must conform to this skeleton.

## Git Policy

- Agents must not commit directly; staging and push are human or
  Git Director performed.
- Commits use conventional messages with a scope prefix.
- Branch strategy: single main line unless explicitly configured otherwise.
- `git pull --rebase` before every push. No force pushes.

## Domain Classification

| Layer | Description |
|---|---|
| **Generic Framework** | Agent orchestration, batch lease protocol, validation pipeline, build/pack abstraction, state machine for work units. |
| **Product Adapter** | Project config, data schema, format mapping, packaging protocol, product-specific rules. |
| **Product Implementation** | Actual product data, domain-specific content, terminology rules, release artifacts. |

Currently all three layers share the same codebase and documentation
without formal boundaries.

## Known Orchestration Issues

1. **No lease coordination across machines.** Local lease files only
   coordinate agents sharing the same checkout. Concurrent clones require
   an external shared queue.
2. **Batch identity coupling.** The batch tool embeds product-specific
   logic (encoding rules, token rules) inside a nominally reusable
   tool. Extraction into a product adapter would resolve this.
3. **Documentation entanglement.** `docs/DEVELOPMENT_STATE.md` is
   product-state documentation. It does not contain framework state.
   Separation is pending at the framework level.
4. **Agent product knowledge.** All agents currently carry
   product-specific knowledge embedded in their instructions. None are
   purely generic yet. Extraction into a product adapter would resolve this.

## Current Framework Objective

Prepare the codebase for clean separation between the generic AI
development system and the product adapter, without breaking the
active product workflow.

## Next Framework Improvement

Define the Product Adapter Contract (see `PRODUCT_ADAPTER_CONTRACT.md`)
and validate that the existing product tooling can satisfy it without
modification. This is a documentation-only step; no extraction is
performed yet.

## Migration Readiness

| Criterion | Status |
|---|---|
| Generic agents identified | Yes |
| Product adapter boundary documented | In progress (this file set) |
| Product adapter contract defined | In progress |
| Model-aware routing implemented | Yes (worker-small/medium/large) |
| Framework code extracted | No |
| Product-specific code isolated | No |
| Dual-layer tests exist | No |
| Migration plan approved | Not yet proposed |

The framework is ready to begin the documentation phase of migration.
Code extraction requires user approval and a validated contract before
proceeding.
