# Framework Migration Plan

Intended separation of the Generic AI Development System, Product Adapter,
and product-specific implementation layers.

**No extraction is being performed yet.** This document is a planning
artifact. All current work continues in the monorepo layout.

---

## Three-Layer Architecture

```
┌──────────────────────────────────────┐
│  Generic AI Development System       │
│  (agent orchestration, batch lease   │
│   protocol, validation pipeline,     │
│   build/pack abstraction, state      │
│   machine, model strategy)           │
├──────────────────────────────────────┤
│  Product Adapter                     │
│  (project config, catalog schema,    │
│   format mapping, packaging protocol,│
│   domain classification)             │
├──────────────────────────────────────┤
│  Product Implementation              │
│  (actual catalogs, STR files,        │
│   release packages, game-specific    │
│   terminology rules)                 │
└──────────────────────────────────────┘
```

## Generic vs Product-Specific Responsibilities

### Generic AI Development System

- Agent role definitions (Director, Planner, Architect, Explorer, Worker, Builder, Git Director).
- Batch export / lease / apply protocol (identity, concurrency, expiry).
- Validation pipeline (schema, token, encoding checks).
- Build abstraction (compile source → output, package output → artifact).
- Work-unit state machine (proposed → approved → in_progress → completed/rejected).
- Model selection policy (independent of product domain).
- Approval and state-transition policy.
- Git workflow conventions.

### Product Adapter

- Maps generic concepts to product-specific formats and tools.
- Defines what "catalog", "string file", and "release package" mean for
  a given product.
- Provides the product identity, config location, and documentation
  entry points.
- Declares safety boundaries (protected tokens, encoding, game engine
  constraints).
- Lists product-specific agents or tools that extend the generic set.
- Identifies generated artifacts and their validation entry points.

### Product Implementation

- The actual translation data (catalogs, string files).
- The compiled output (release packages, .big archives).
- Game-specific glossary and terminology rules.
- Maps, campaigns, subtitles, and all domain content.

## Product State vs AI System State

| Document | Scope | Content |
|---|---|---|
| `DEVELOPMENT_STATE.md` | Product Implementation | Milestones, tasks, blockers, verification criteria for the active product. |
| `AI_SYSTEM_STATE.md` | Generic Framework | Framework version, status, agents, model strategy, migration readiness. |

These must never be merged. Product state is about *what* the product
needs. AI system state is about *how* the framework operates.

## Domain Classification

Every file, tool, and documentation entry belongs to one layer:

| Layer | Classification Rule |
|---|---|
| Generic | No product name, format, or domain term appears in the code or text. |
| Product Adapter | References the product identity but contains no actual product data. |
| Product Implementation | Contains actual product data, domain rules, or game-specific content. |

Ambiguous items default to the most specific layer that applies.

## Migration Phases

### Phase A — Separate state (current)

Define the three-layer architecture, the Product Adapter Contract, and
classify all existing files. This phase is documentation-only and
prepares state separation. No extraction, movement, or behavior change
occurs.

### Phase B — Identify product-specific references

Catalog all product-specific references in generic tools, agent
instructions, and documentation. Produce a map of what must be
abstracted before extraction.

### Phase C — Introduce Product Adapter

Define the Product Adapter interface and implement the adapter layer
for the BFME product. Generic tools begin routing product-specific
requests through the adapter.

### Phase D — Make agent prompts generic

Remove product-specific knowledge from agent role definitions. Agents
receive product context through the adapter, not through hardcoded
logic or product-specific instructions.

### Phase E — Extract reusable framework

Extract the generic AI development system into a self-contained
module or package. The product repository consumes it as a dependency.

### Phase F — Consume framework from BFME-Localization

BFME-Localization imports and configures the extracted generic
framework. New products onboard by implementing a new Product Adapter
without modifying the generic framework.

## Constraints

- No phase may break the active product workflow.
- Each phase produces a testable artifact (documentation, interface
  definition, or working code with tests).
- Phases require explicit user approval before execution.
- The existing product pipeline remains functional throughout
  all phases.
