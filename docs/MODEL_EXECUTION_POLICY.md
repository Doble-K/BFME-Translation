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

## Worker Hierarchy

The Director selects workers by capability class. Each worker is a registered
subagent with a fixed model configuration.

### Worker Small

- **Model:** `opencode-go/mimo-v2.5`
- **Agent file:** `.opencode/agent/worker-small.md`
- **Use for:** Bounded implementation tasks, straightforward code changes,
  validation, exploration, routine orchestration.

### Worker Medium

- **Model:** `opencode-go/deepseek-v4-flash`
- **Agent file:** `.opencode/agent/worker-medium.md`
- **Use for:** Complex implementation requiring deeper reasoning, cross-file
  analysis, multi-step validation, architect-level work.

### Worker Large (Luna)

- **Model:** `opencode-go/gpt-5.6-luna`
- **Agent file:** `.opencode/agent/worker-large.md`
- **Use for:** Exceptional tasks requiring maximum capability: repository-wide
  redesigns, major migrations, deep architectural reviews.
- **Authorization:** Never selected automatically. Only the repository owner
  may explicitly authorize it for a specific task.

## Escalation Policy

Always attempt the smallest capable worker first:

```text
worker-small
  -> worker-medium
  -> Stop (escalate to human)
```

Workers must not automatically escalate to a larger model. When blocked, the
current worker must explain:

- why it is blocked;
- what information is missing; and
- what decision cannot be made.

The user decides whether escalation is necessary. Worker Large requires
explicit human authorization before activation.

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
  -> Worker (small/medium/large)
  -> Reviewer
```

This workflow is not yet implemented. The current priority is reducing token
consumption and improving reusable documentation.
