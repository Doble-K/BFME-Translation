# Localization Glossary

This glossary defines the terminology for the project's first production
target: Latin American Spanish for ROTWK 2.02. It is also the shared context
for human translators and future bulk AI processing.

The glossary is a living reference. A term is not considered final until it is
listed here with an agreed translation and usage note.

## Usage Rules

- Prefer the approved translation in this file over literal or inconsistent
  alternatives.
- Preserve Tolkien proper names unless an explicit project decision says
  otherwise.
- Do not translate IDs, URLs, format tokens, engine tags, or control strings.
- Keep the same term across menus, tooltips, subtitles, objectives, and maps.
- Use Latin American Spanish, avoiding regionalisms that change the game
  meaning.
- Use the context note when the same English word has different meanings.
- New terms should be proposed here before being used broadly in a batch.

## Approved RTS Terms

| English | Spanish | Context |
|---|---|---|
| Ability | Habilidad | Unit or hero action. |
| Armor | Armadura | Defense statistic. |
| Build | Construir | Command or action. Use `tiempo de construcción` for build time. |
| Building | Edificio | Constructible structure. |
| Command Points | Puntos de mando | Army capacity statistic. |
| Damage | Daño | Attack statistic. |
| Hero | Héroe | Hero unit. |
| Horde | Horda | SAGE group of units. |
| Health | Salud | Unit statistic. |
| Power | Poder | Faction or hero power. |
| Rally Point | Punto de reunión | Unit production destination. |
| Recruit | Reclutar | Training or hiring a unit. |
| Structure | Estructura | Generic building or constructible object. |
| Summon | Invocar | Creating a unit or object temporarily. |
| Unit | Unidad | Single controllable game entity. |
| Upgrade | Mejora | Technology or unit upgrade. |

## Tolkien Names

Proper names require an explicit decision before bulk translation. The default
policy is to preserve the source spelling and capitalization. Do not invent a
localized form because a literal translation seems possible.

Decisions to complete with community or reference material:

- Faction names and faction adjectives.
- Character and hero names.
- Places, regions, maps, and campaign objectives.
- Creature names and Tolkien-specific terms.
- Names that have an established Spanish literary or game localization.

## Pending Decisions

Each entry should be resolved with a source ID or category before being applied
to a translation batch:

- Official versus community Spanish forms for Tolkien proper names.
- `Warg`, `Uruk`, `Orc`, `Goblin`, and related creature terminology.
- `Power`, `Spell`, and `Ability` when they appear in the same UI context.
- `Horde`, `Battalion`, and other SAGE group terminology.
- Capitalization of faction names, powers, upgrades, and map names.

## AI Bulk Context

Bulk translation and AI review should receive this file as terminology context.
The AI must:

- Prefer approved terms exactly as written.
- Preserve protected tokens and engine tags.
- Report a glossary conflict instead of silently inventing a new term.
- Mark uncertain output with `needs_review`.
- Never modify this glossary automatically.

## Change Process

1. Propose a term with source IDs and context.
2. Check for existing official or community usage.
3. Record the chosen form and a short usage note.
4. Apply it in a controlled translation batch.
5. Validate tokens and review affected entries.

The glossary is versioned with the project. External translation platforms, if
added in a future version, must import and export these decisions without
creating a second uncontrolled terminology source.
