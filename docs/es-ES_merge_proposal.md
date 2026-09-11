# es-ES & es-419: Dual-Locale Configuration

## Overview

The project now supports two independent Spanish locales for *The Lord of the
Rings: The Battle for Middle-earth II: The Rise of the Witch-king* (ROTWK 2.02):

| Locale | Variety | Glossary | Project Config | Catalog |
|--------|---------|----------|----------------|---------|
| **es-ES** | European Spanish (Spain) | `glossaries/es-ES.glossary.md` | `config/project.json` (active) | `catalogs/spanish_es-ES_work.json` |
| **es-419** | Latin American Spanish | `GLOSSARY.md` (root) | `config/project_es-419.json` | `catalogs/spanish_9770_work.json` |

These are **not** mutually exclusive. They are independent locale configurations
sharing the same engine tooling, protected-token rules, and formatting
conventions.

---

## es-ES: Active Initial Locale

The es-ES locale is the project's **active initial translation target**. It
follows the European Spanish variety with Editorial Minotauro canonical Tolkien
names and a large, already-refined glossary (100+ terms).

To work on es-ES:

```bash
python3 tools/localization/agent_batch.py export \
  --project config/project_es-ES.json \
  --count 20 \
  --mode incomplete \
  --worker WORKER_NAME
```

Key configuration in `config/project_es-ES.json`:

- `language`: `"es-ES"`
- `glossary`: `"glossaries/es-ES.glossary.md"`
- `catalog`: `"catalogs/spanish_es-ES_work.json"`
- `output_package`: `"releases/spanishpatch202_es-ES.big"`
- Encoding: Windows-1252 (latin1) for `.str` output

---

## es-419: Independent Preserved Locale

The es-419 locale is an **independent, preserved configuration** for Latin
American Spanish. It remains fully functional and backward-compatible with
all existing tooling, the OpenCode farm, and the root `GLOSSARY.md`.

To work on es-419:

```bash
python3 tools/localization/agent_batch.py export \
  --project config/project_es-419.json \
  --count 20 \
  --mode incomplete \
  --worker WORKER_NAME
```

Key configuration in `config/project_es-419.json`:

- `language`: `"es-419"`
- `glossary`: `"GLOSSARY.md"` (root Latin American glossary)
- `catalog`: `"catalogs/spanish_9770_work.json"`
- `output_package`: `"releases/spanishpatch202.big"`

The `config/opencode_farm.json` references `config/project.json`
(es-ES) as the default farm target.

---

## Terminology Differences

The two locales diverge on Spanish variety and Tolkien proper-name policy.
The core differences are:

### Agreed Terms (no conflict)

| English | Spanish |
|---------|---------|
| Summon | Invocar |
| Recruit | Reclutar |
| Upgrade | Mejora |
| Build Time | Tiempo de construccion |
| Command Points | Puntos de mando |
| Structure | Estructura |
| Damage | Dano |
| Armor | Armadura |
| Health | Salud |
| Hero | Heroe |
| Power | Poder |
| Spell | Hechizo |
| Horde | Horda |

### Resolved Conflicts

| English | es-419 (LatAm) | es-ES (Spain) | Note |
|---------|----------------|---------------|------|
| Rally Point | Punto de reunion | Punto de reunion | Same term. |
| Debuff / Buff | (pending) | Kept in English | es-ES explicit decision. |
| Troll | (pending) | Trol (pl. Troles) | Castilianized form. |
| Goblins | (pending) | Trasgos | Editorial Minotauro. |
| Wargs | (pending) | Huargos | Editorial Minotauro. |
| Orcs | (pending) | Orcos | Editorial Minotauro. |
| Treebeard | (pending) | Barbol | Editorial Minotauro. |
| Witch-king | (pending) | Rey Brujo | Needs explicit decision if merging upstream. |

### es-ES Exclusive Additions

The es-ES glossary contributes terms the upstream lacks:

- Damage types: Slash -> Cortante, Pierce -> Perforante.
- Mod-specific units: 60+ entries (see `glossaries/es-ES.glossary.md`).
- Conditional rules: Blades -> Espadas/Hachas, PurchaseTechnology entries.
- Title Case rules for unit/building names.
- Command style: infinitive verbs for all buttons.

---

## Shared Conventions

Both locales share:

- **Protected tokens**: `%1`, `%2`, `%d`, `%s`, `%PLAYER%`, `<TOKEN>`, etc.
- **SAGE hotkeys**: `&Aragorn` -> `Aragorn [&A]` (letter preserved).
- **Engine tags**: `CONTROLBAR:`, `OBJECT:`, `SCIENCE:`, etc.
- **Encoding**: Windows-1252 (latin1) for `.str` files; UTF-8 for markdown.
- **State tracking**: Catalog statuses (`pending`, `translated`, `preserved`, etc.).
- **Command style**: Infinitive verbs (Construir, Reclutar, Mejorar).

---

## Future Extensibility

The dual-locale architecture is designed for extension:

1. **New Spanish varieties**: Add a `config/project_XX.json` with its own
   `language`, `glossary`, `catalog`, and `output_package` paths. The
   tooling resolves all paths from the project file.

2. **New games or mods**: Each game/mod gets its own project configuration
   and catalog. The glossary can be shared or overridden per locale.

3. **New languages**: Add a new `config/project_LL.json` with the target
   language code, a dedicated glossary, and isolated output paths. No
   changes to existing configurations are required.

4. **Glossary inheritance**: The `project.glossary` field resolves relative
   to the repository root. If omitted, the tool falls back to the root
   `GLOSSARY.md`. Locale-specific glossaries override only the terms they
   define.

---

## Glossary Merge Notes

This section documents the reconciliation between the upstream Latin American
glossary and the local European Spanish glossary.

### Conflicts Requiring Human Decision

1. **Spanish variety**: The project supports both independently. No forced
   merge is needed.
2. **Witch-king**: es-ES uses "Rey Brujo"; upstream preserves "Witch-king".
   Each locale follows its own convention.
3. **Troll**: es-ES castilianizes to "Trol/Troles"; es-419 leaves undefined.
4. **Debuff/Buff**: es-ES keeps in English; es-419 follows its own review
   process.
5. **Promoted pending terms**: es-ES resolves Goblin -> Trasgos, Warg ->
   Huargos, Orc -> Orco using Editorial Minotauro. es-419 retains its
   own pending review.

### Convention Differences

| Topic | es-419 | es-ES |
|-------|--------|-------|
| Glossary scope | ~13 RTS terms (early stage) | 100+ terms (refined) |
| State tracking | Catalog statuses | Catalog statuses (shared) |
| Encoding | UTF-8/JSON catalogs; cp1252 .str | Same |
| Hotkey convention | `[&X]` preserved | `[&X]` preserved |

### Action Items

- [ ] Resolve the "Witch-king" / "Rey Brujo" decision for each locale.
- [ ] Create `catalogs/spanish_es-ES_work.json` and import es-ES source
  entries (separate Gandalf operation).
- [ ] Promote es-419 pending terms (Goblin, Warg, Orc, Horde, Power) using
  community review.
- [ ] Consider adopting es-ES mod-specific units and conditional rules
  upstream for es-419.
