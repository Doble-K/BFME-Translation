---
name: gandalf
description: BFME-Localization Product Operations using Gandalf. Use this skill when performing translation batches, applying translations to catalogs, or running Gandalf CLI operations on the BFME-Localization project. This is for product operations, not generic AI framework work.
---

# Gandalf Skill

## What is Gandalf?

Gandalf is a **Python product tool**, not an AI agent or Task subagent. It is a translation management system for BFME-Localization.

## Entry Point

```bash
python3 gandalf.py --cli
```

## Required Configuration

- `config/project.json` — project configuration file

## Supported Operations

### `/translate-next` (Inside Gandalf CLI)

```bash
/translate-next <unique-worker> 20
```

- **<unique-worker>**: A unique worker name (must be unique per worker instance)
- **20**: Current default batch size

### Before Using `/translate-next`

1. Check active reservations first if Gandalf provides a supported mechanism
2. Never invent unsupported commands
3. Never invoke Translation Farm or translation agents directly

## Expected Effects

May create/update:
- Temporary `.agent/` state files
- Translations in `catalogs/spanish_9770_work.json`
- Run required translation validation

## Important Rules

1. **Human Approval Required**: Before any operation modifying product data, present the exact operation and obtain explicit human approval; execute only that operation; never automatically continue to another batch.

2. **Do Not Update Development State**: This tool must not update `docs/DEVELOPMENT_STATE.md` because localization operations do not advance product development state.

3. **Director Workflow**: Director executes Gandalf through its documented CLI interface; Gandalf owns its internal workflow.

## Context Efficiency

- Do not invoke Explorer just to rediscover Gandalf
- Do not read `.opencode/agent/*`
- Do not read AI framework migration docs
- Load only product files required for the specific operation

## Scope

BFME-Localization product-specific tool; not a generic AI framework component. Future Product Adapter may reference it.