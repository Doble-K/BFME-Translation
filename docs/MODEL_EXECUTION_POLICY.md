# Model Execution Policy

This is the canonical repository policy for selecting and using AI models. Its
default objective is to minimize context usage and model cost while maintaining
development quality.

## Cost First

- Prefer existing documentation over exploring source code.
- Never reload repository knowledge that is already documented.
- Use the smallest context and model capable of completing the task.

## Documentation First

Before reading source code, agents should consult documentation in this order:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `COMPONENTS.md`
4. `STATUS.md`
5. `CONVENTIONS.md`
6. Specific documentation for the task
7. Source code, only when necessary and permitted

## Model Hierarchy

### Architect Small

The default architect. Use it for local architectural decisions,
documentation updates, and clarification of existing architecture.

### Architect Medium

Use it for cross-module architectural work, design refinements, feature
decomposition, and documentation consolidation.

### Architect Large

Reserve it for exceptional architectural work, repository-wide redesigns,
major migrations, and deep architectural reviews. Architect Large is never
selected automatically. Only the repository owner may explicitly authorize it.

## Escalation Policy

Always attempt the smallest capable model first:

```text
Small
  -> Medium
  -> Stop
```

Models must not automatically escalate to a larger model. When blocked, the
current model must explain:

- why it is blocked;
- what information is missing; and
- what decision cannot be made.

The user decides whether escalation is necessary.

## Context Budget

Agents should minimize context by preferring targeted file reads, summaries,
and existing documentation. They should avoid reading entire repositories,
repeating previous exploration, or loading unrelated modules.

## Human Authority

Only the repository owner may authorize Architect Large, redefine repository
architecture, approve large migrations, or change repository-wide policies.
Agents must stop rather than make those decisions themselves.

## Long-Term Workflow

The intended future pipeline is:

```text
Director
  -> Planner
  -> Architect
  -> Explorer
  -> Worker
  -> Reviewer
```

This workflow is not yet implemented. The current priority is reducing token
consumption and improving reusable documentation.
