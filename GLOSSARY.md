# Localization Glossary

This glossary defines the terminology for the project's first production
target: Latin American Spanish for ROTWK 2.02. It is also the shared context
for human translators and future AI-assisted localization.

The glossary is a living reference. A term is not considered final until it is
listed here with an agreed translation, status, and usage note.

---

# Usage Rules

- Prefer the approved translation in this file over literal or inconsistent alternatives.
- Preserve Tolkien proper names unless an explicit project decision says otherwise.
- Do not translate IDs, URLs, format tokens, engine tags, or control strings.
- Keep the same term across menus, tooltips, subtitles, objectives, maps, and documentation.
- Use Latin American Spanish, avoiding regionalisms that change the game meaning.
- Use the context note when the same English word has different meanings.
- New terms should be proposed here before being used in translation batches.

---

# Terminology Status

Every glossary entry should have one of the following statuses.

| Status | Description |
|---------|-------------|
| **official** | Official EA localization. |
| **community** | Widely accepted community terminology. |
| **project** | Project decision when no official terminology exists. |
| **pending** | Not yet approved. Do not use in bulk translation. |

---

# Approved RTS Terms

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Ability | Habilidad | project | Unit or hero action. |
| Armor | Armadura | project | Defense statistic. |
| Build | Construir | project | Command or action. Use **tiempo de construcción** for build time. |
| Building | Edificio | project | Constructible structure. |
| Command Points | Puntos de mando | official/project | Army capacity statistic. |
| Damage | Daño | project | Attack statistic. |
| Health | Salud | project | Unit statistic. |
| Hero | Héroe | official/project | Hero unit. |
| Horde | Horda | pending | SAGE group of units. |
| Power | Poder | pending | Hero or faction power. |
| Rally Point | Punto de reunión | project | Unit production destination. |
| Recruit | Reclutar | project | Train or hire a unit. |
| Structure | Estructura | project | Generic constructible object. |
| Summon | Invocar | project | Temporary creation of a unit or object. |
| Unit | Unidad | project | Single controllable game entity. |
| Upgrade | Mejora | project | Technology or unit upgrade. |

---

# Command Style

Command buttons should use the infinitive.

Examples:

- Construir
- Reclutar
- Mejorar
- Cancelar
- Atacar
- Defender
- Reparar

Avoid mixing infinitive and imperative forms.

---

# UI Constraints

User interface strings often have limited space.

Guidelines:

- Prefer concise wording.
- Avoid unnecessary expansion.
- Preserve readability.
- Keep terminology consistent across all screens.

---

# Protected Tokens

The following tokens must never be modified.

Examples:

```text
%1
%2
%PLAYER%
<TOKEN>
<VALUE>
{TOKEN}
$PLAYER
%%%
```

Do not:

- translate them;
- remove them;
- reorder them;
- duplicate them.

---

# Engine Tags

Never modify engine-specific identifiers.

Examples:

```text
CONTROLBAR:
OBJECT:
SCIENCE:
SPECIALPOWER:
UPGRADE:
WEAPON:
ARMOR:
```

These are internal engine references.

---

# Formatting Rules

Preserve:

- punctuation;
- capitalization when meaningful;
- escape sequences;
- line breaks when required.

Never normalize formatting unless it is clearly incorrect.

Preserve sequences such as:

```text
\n
\r\n
\t
```

---

# Tolkien Names

Proper names require an explicit decision before bulk translation.

Default policy:

1. Use the official EA Spanish localization whenever available.
2. Otherwise use the established Tolkien Spanish literary form.
3. If neither exists, preserve the original English spelling.
4. Never invent localized names.

Categories requiring review:

- Faction names
- Hero names
- Character names
- Places
- Maps
- Regions
- Campaign objectives
- Creatures
- Unique artifacts

---

# Pending Decisions

The following terminology requires community review before approval.

- Warg
- Uruk
- Orc
- Goblin
- Troll variants
- Power vs Spell vs Ability
- Horde vs Battalion
- Faction adjectives
- Capitalization of powers
- Capitalization of upgrades
- Capitalization of map names

---

# AI Translation Rules

AI-assisted translation must follow these rules.

- Prefer approved glossary terms exactly as written.
- Preserve all protected tokens.
- Preserve engine identifiers.
- Never invent terminology.
- Report glossary conflicts.
- Mark uncertain translations with `needs_review`.

If a glossary term does not exist:

1. Keep the original English term.
2. Mark the entry as `needs_review`.
3. Report the missing glossary entry.

Never silently guess terminology.

---

# Mod Extensions

Mods may extend this glossary.

Extension glossaries must:

- inherit the base glossary;
- override terminology only when necessary;
- document every overridden term;
- preserve compatibility with the base project.

A mod must never silently redefine an existing approved term.

---

# Change Process

1. Propose a new term.
2. Include source IDs and context.
3. Check official EA localization.
4. Check community usage.
5. Record the selected translation.
6. Assign a terminology status.
7. Add a short usage note.
8. Apply the change in a controlled translation batch.
9. Validate protected tokens.
10. Review the translated entries.

---

# Versioning

This glossary is versioned with the project.

Future localization tools, web interfaces, and translation platforms must use
this glossary as the single source of terminology.

Alternative terminology databases should not be created independently.

---

# Localization Workflow Terms

These terms describe the active v1 workflow and the possible v2 workflow.

| Term | Meaning | Version |
|------|---------|---------|
| `pending` | Entry still needs a translation. | V1 active |
| `translated` | Translation accepted for compilation; it may still need correction. | V1 active |
| `preserved` | Source text intentionally retained for engine/system compatibility. | V1 active |
| `needs_review` | Flag requiring human checking or correction. | V1 active |
| `suggested` | Proposal not yet accepted for compilation. | V2 reserved |
| `rejected` | Proposal declined but still recoverable. | V2 reserved |
| `reviewed` | Human formally completed review of an accepted translation. | V2 reserved |
| `system_preserved` | Flag for a preserved system entry; it does not specifically mean hotkey. | V1 active |
| `review.ai` | Machine review results, issues, suggestions, and confidence. | Future bulk AI |

The normal v1 path is:

```text
pending -> translated -> translated + needs_review -> translated
```

System entries use `preserved` and are excluded from normal translation batches.
The proposal states remain documented for a possible v2 and are not required to
complete the first translation release.
