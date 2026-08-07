# Product Adapter Contract

Conceptual contract defining the minimum information a Product Adapter must
provide to the Generic AI Development System. This is not an implementation;
it specifies the interface boundary.

---

## Contract Definition

A Product Adapter is the layer that translates between the generic AI
framework and a specific product domain. It answers every question the
generic system might have about *what* it is operating on, without the
generic system needing product-specific knowledge.

## Required Information

### 1. Product Identity

A stable, unique identifier for the product.

```
product.name:        string    (stable unique identifier)
product.version:     string    (optional, free-form)
```

The generic system uses `product.name` for lease namespacing, batch IDs,
and logging. It never interprets the value.

### 2. Product-State Location

Where the product keeps its current progress and status documents.

```
product-state.development:   path   (milestones, tasks, blockers)
product-state.reference:     path   (approved terminology or domain rules)
product-state.rules:         path   (formatting and operational rules)
```

The generic system may read these for context but never writes to them
without explicit user approval.

### 3. Architecture / Status Documentation Entry Points

Links to documents the generic system should consult for product context.

```
docs.architecture:    path   (product architecture or overview)
docs.status:          path   (current development state)
docs.agents:          path   (agent instructions for this product)
```

### 4. Product Operational Interface

The set of operations the adapter exposes to the generic system.

| Operation | Purpose |
|---|---|
| `inspect` | Extract a bounded set of work items from product data. |
| `commit` | Write processed work items back to product data. |
| `validate` | Run product-specific validation checks. |
| `build` | Compile source data into distributable artifacts. |
| `publish` | Assemble built artifacts into release format. |
| `status` | Report aggregate progress without exposing source content. |

Each operation must:
- Accept generic parameters (batch ID, count, mode, worker name).
- Delegate product-specific logic internally.
- Return a generic result structure (success, errors, metadata).

### 5. Product-Specific Tools and Agents

Any tools or agents that extend the generic set for this product.

```
product.tools[]:       list of tool paths or names
product.agents[]:      list of agent role definitions
```

The generic system does not invoke these directly. The adapter routes
requests to them as needed.

### 6. Safety Boundaries

Rules the generic system must enforce but does not define.

| Boundary | Description |
|---|---|
| Protected tokens | Tokens that must never be modified, removed, or reordered. |
| Encoding constraints | Required character encoding for output files. |
| Format constraints | Reserved characters, line endings, escape sequences. |
| System identifiers | Engine or system identifiers that must remain unmodified. |

The adapter declares these boundaries. The generic system enforces them
through the validation pipeline.

### 7. Validation Entry Points

Where the generic system triggers product-specific checks.

```
validation.pre_apply:     path   (validate before committing a batch)
validation.post_build:    path   (validate after compilation)
validation.release:       path   (validate before packaging)
```

Each entry point is a command the generic system invokes. It returns
a pass/fail result with error details.

### 8. Generated Artifacts

What the product produces and where the generic system finds them.

```
artifacts.working:       path   (working data for the current cycle)
artifacts.compiled:      path   (compiled output from build)
artifacts.release:       path   (final package for distribution)
```

The generic system tracks these paths for staging and commit guidance.
It never interprets the artifact format.

### 9. Special-Approval Operations

Operations that require explicit user approval before execution.

Typical candidates:
- Modifying protected tokens or system-preserved entries.
- Changing encoding or format constraints.
- Altering the packaging protocol.
- Running bulk migrations on product data.
- Updating the Product Adapter Contract itself.

The adapter lists these operations. The generic system gates them behind
approval checks.

---

## BFME-Localization Example Mapping (Non-Normative)

The following maps the generic contract to the concrete BFME localization
project. This section is product-specific and does not constrain other
products.

| Contract Field | BFME-Localization Value |
|---|---|
| `product.name` | `bfme2-rotwk-2.02` |
| `product.version` | `2.02` |
| `product-state.development` | `docs/DEVELOPMENT_STATE.md` |
| `product-state.reference` | `GLOSSARY.md` |
| `product-state.rules` | `rules/translation_rules.md` |
| `docs.architecture` | `README.md` |
| `docs.status` | `docs/DEVELOPMENT_STATE.md` |
| `docs.agents` | `AGENTS.md` |
| `product.tools[]` | `tools/localization/agent_batch.py`, `tools/localization/validate.py`, `tools/localization/validate_translation.py`, `tools/localization/build.py`, `tools/localization/pack.py` |
| `product.agents[]` | Director, Planner, Architect, Explorer, Worker, Builder, Git Director |
| `validation.pre_apply` | `python3 tools/localization/validate.py` |
| `validation.post_build` | `python3 tools/localization/validate_translation.py` |
| `validation.release` | `python3 tools/localization/build.py && python3 tools/localization/pack.py` |
| `artifacts.working` | `catalogs/spanish_9770_work.json` |
| `artifacts.compiled` | `translations/spanish/data/lotr.str` |
| `artifacts.release` | `releases/spanishpatch202.big` |
| `special-approval[]` | Modifying protected tokens, changing STR encoding, altering .big packaging, bulk catalog migration |

**Note:** Gandalf (`gandalf.py`), Translation Farm concepts, catalog
internal formats (STR parsing), and RotWK-specific game mechanics are
product implementation details. They are not part of the generic contract.
They appear here only because the BFME example mapping references the
concrete product.

---

## Compliance

A Product Adapter is compliant with this contract when:

1. All nine required information sections are defined.
2. Every operation can be invoked through a generic interface.
3. Safety boundaries are declared and enforceable.
4. Validation entry points return structured pass/fail results.
5. Special-approval operations are explicitly listed.

The generic system does not inspect adapter internals. It relies on the
contract interface only.
