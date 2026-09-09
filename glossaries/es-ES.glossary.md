# Localization Glossary

This glossary defines the terminology used by the `lotr-spanish-translation`
project: the Spanish translation of *The Lord of the Rings: The Battle for
Middle-earth II: The Rise of the Witch-king* (ROTWK) Unofficial Patch 2.02.

It is written in the structure of the upstream
[Doble-K/BFME-Translation](https://github.com/Doble-K/BFME-Translation)
`GLOSSARY.md` so it can be proposed and merged there. The authoritative source
for this project's terminology is `.kiro/agents/game-tooltip-translator.md`;
this file mirrors that agent's decisions in glossary form.

> **Spanish variety note:** This glossary targets **European Spanish (Spain)**
> and follows the canonical Tolkien translations from Editorial Minotauro. The
> upstream BFME-Translation project targets **Latin American Spanish**. Merging
> requires an explicit decision on which variety governs. See
> `docs/GLOSSARY_MERGE_PROMPT.md` for the full list of divergences.

---

# Usage Rules

- Prefer the approved translation in this file over literal or inconsistent alternatives.
- Preserve Tolkien proper names per the Tolkien Names policy below.
- Do not translate IDs, URLs, format tokens, engine tags, or control strings.
- Keep the same term across menus, tooltips, subtitles, objectives, maps, and documentation.
- Use European Spanish (Spain) with Editorial Minotauro canonical names.
- Use the informal "tú" form for player-facing text (e.g., "Haz clic", not "Haga clic").
- Use the context note when the same English word has different meanings.
- Unit names, buildings, powers, abilities and upgrades use Title Case in Spanish.

---

# Terminology Status

| Status | Description |
|---------|-------------|
| **official** | Official EA localization. |
| **community** | Widely accepted community terminology. |
| **project** | Project decision when no official terminology exists. |
| **canonical** | Editorial Minotauro literary form for Tolkien names. |
| **pending** | Not yet approved. Do not use in bulk translation. |

---

# Approved RTS Terms

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Ability | Habilidad | project | Unit or hero action. |
| Active ability | Habilidad activa | project | |
| Passive ability | Habilidad pasiva | project | |
| Toggle ability | Habilidad alternante | project | |
| Armor | Armadura | project | Defense statistic. |
| Attack | Ataque | project | |
| Build Time | Tiempo de construcción | project | |
| Command Points | Puntos de mando | official/project | Army capacity statistic. |
| Cost | Coste | project | |
| Damage | Daño | project | Attack statistic. |
| Defense | Defensa | project | |
| Duration | Duración | project | |
| Experience | Experiencia | project | |
| Fear | Miedo | project | |
| Health | Salud | project | Unit statistic. |
| Heal | Curar | project | |
| Hero | Héroe | official/project | Hero unit. |
| Horde | Horda | project | SAGE group of units. See note: `OBJECT:Horde*` entries use the plural unit name only, never "Horda de...". |
| Leadership | Liderazgo | project | |
| Level | Nivel | project | |
| Power | Poder | project | Hero or faction power. |
| Radius | Radio | project | |
| Range | Alcance | project | |
| Recharge Time | Tiempo de recarga | project | |
| Recruit | Reclutar | project | Train or hire a unit. |
| Resources | Recursos | project | |
| Spell | Hechizo | project | |
| Speed | Velocidad | project | |
| Strong vs. | Fuerte contra | project | |
| Structure | Estructura | project | Generic constructible object. |
| Summon | Invocar | project | Temporary creation of a unit or object. |
| Train | Entrenar | project | |
| Upgrade | Mejora | project | Technology or unit upgrade. |
| Weak vs. | Débil contra | project | |
| Left click to activate | Clic izquierdo para activar | project | UI action string. |
| Right click to cancel | Clic derecho para cancelar | project | UI action string. |

---

# Damage / Armor Types

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Slash | Cortante | project | Damage type. |
| Pierce | Perforante | project | Damage type. |

---

# Unit Types

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Swordsmen | Espadachines | project | |
| Pikemen | Lanceros | project | |
| Archers | Arqueros | project | |
| Cavalry | Caballería | project | |
| Monsters | Monstruos | project | |
| Structures | Estructuras | project | |
| Battalion | Batallón | project | |
| Specialist | Especialista | project | |

---

# Buildings

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Fortress | Fortaleza | project | |
| Wall | Muralla | project | |
| Gate | Puerta | project | |
| Tower | Torre | project | |
| Camp | Campamento | project | |
| Siege Works | Fábrica de Máquinas de Asedio | project | |
| Mumak Pen | Corral de Mûmakil | project | |
| Mine Shaft | Zapa | project | |
| Hall of Warriors | Salón de los Guerreros | project | |
| Hearth | Horno | project | |

---

# Map / Neutral Terms

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Outpost | Enclave (pl. Enclaves) | project | |
| Signal Fire | Almenara (pl. Almenaras) | project | |
| Dead Marshes | Ciénaga de los Muertos | canonical | |
| Near Harad | Harad Cercano | project | |
| Far Downs | Colinas Lejanas | project | |
| North Wold | El Páramo del Norte | project | |
| Wold | Páramo | project | |
| Dale | Valle | canonical | |
| Brandywine | Brandivino | canonical | |
| Numenor | Númenor | canonical | |

---

# Mod-Specific Units, Upgrades and Powers

These terms are specific to the Unofficial Patch 2.02 mod content.

| English | Spanish | Status | Context |
|---------|----------|--------|---------|
| Troll | Trol | project | Castilianized form (pl. Troles). |
| Half-Troll / Half-Trolls | Semitrol / Semitroles | project | |
| Drummer Troll | Trol con Tambor | project | |
| Attack Troll | Trol de Ataque | project | |
| Mountain Troll | Trol de las Montañas | project | |
| Hill Troll / Hill Trolls | Trol de las Colinas / Trols de las Colinas | project | |
| Snow Troll / Snow Trolls | Trol de las Nieves / Trols de las Nieves | project | |
| Warg / Wargs | Huargo / Huargos | canonical | |
| Goblin / Goblins | Trasgo / Trasgos | canonical | |
| Easterlings | Orientales | project | |
| Mumak / Mumaks | Mûmak / Mûmakil | canonical | Mûmakil is the plural. |
| Oathbreakers | Rompejuramentos | project | |
| Deathbringers | Portadores de la Muerte | project | |
| Men of Dale | Hombres de Valle | project | |
| Zealots | Zelotes | project | |
| Bolts | Virotes | project | |
| Heavy Spiked Collars | Collares Pesados de Pinchos | project | |
| Stone Throwers | Lanzapiedras | project | |
| Trebuchet | Trabuco | project | |
| Ice Shot | Proyectiles Helados | project | |
| Silverthorn Arrows | Flechas Púa de Plata | project | |
| Goblin Spider Rider / Riders | Jinete / Jinetes de Araña Trasgo | project | |
| Wildmen Axe Throwers | Lanzadores de Hachas Salvajes | project | |
| Stationary Ent | Ent Vigilante | project | |
| Yeoman Archer / Archers | Arquero / Arqueros Campesino / Campesinos | project | |
| Greater Wight | Gran Tumulario | project | |
| Guardian Ent Ash | Ent Fresno Guardián | project | |
| Mithlond Sentry / Sentries | Guardia / Guardias de Mithlond | project | |
| Ithilien Ranger / Rangers | Explorador / Exploradores de Ithilien | project | |
| Dunedain Ranger / Rangers | Explorador / Exploradores Dúnedain | project | |
| Dark Ranger / Rangers | Explorador / Exploradores Oscuros | project | |
| Black Numenorean / Numenoreans | Numenóreano / Numenóreanos Negros | project | |
| Spiderling / Spiderlings | Arácnido / Arácnidos | project | |
| Drake / Drakes | Draco / Dracos | project | |
| Fire Drake | Draco de Fuego | project | |
| Drake Brood / Broods | Progenie / Progenies de Draco de Fuego | project | Horde context. |
| Fire Drake Broodling | Cría de Draco de Fuego | project | Individual unit (pl. Crías). |
| Death Masks / Deathmasks | Máscaras de la Muerte | project | |
| Battlewagon / Battlewagons | Carro de Batalla / Carros de Batalla | project | |
| Elite Tower Shield Guard | Guardia de Élite con Escudo | project | |
| Dire Wolf / Dire Wolves | Lobos Atroces | project | |
| Encasing Vines | Manto de Enredaderas | project | |
| Dwarven Industriousness | Riquezas Enanas | project | |
| Fire Stones | Proyectiles en Llamas | project | |
| Flaming Shot | Proyectiles en Llamas | project | |
| Masterwork Munitions | Municiones de Gran Calidad | project | |
| Scavenged Armor | Armadura de Carroñero | project | |
| Tier 1/2/3/4/5 Hero | Héroe de Rango 1/2/3/4/5 | project | |

---

# Do Not Translate

These terms are intentionally kept in English/original form.

| English | Reason |
|---------|--------|
| Debuff / Debuffs | Community gaming term. Never "debilitación". |
| Buff / Buffs | Community gaming term. Never "mejoras" in this context. |

---

# Command Style

Command buttons use the infinitive: Construir, Reclutar, Mejorar, Cancelar,
Atacar, Defender, Reparar. Avoid mixing infinitive and imperative forms.

### PurchaseTechnology entries

Button labels for researching/purchasing upgrades follow the format
**"Investigar [Upgrade Name]"** (verb + upgrade name in Title Case). Do not use
an "Investigación:" prefix and do not add a redundant "Mejora". Preserve the `&`
hotkey marker in its original position.

Exceptions:

- Angmar spell specializations (WellOfSouls, CorpseRain, SoulFreeze): keep just
  the spell name, no "Investigar".
- Upgrades purchased directly on units use **"Comprar"** instead of "Investigar":
  - `PurchaseTechnologyAngmarSpikedCollars` → "Comprar Collares de &Pinchos"
  - `PurchaseTechnologyAngmarDeathMasks` → "Comprar Máscaras de la Muerte"
- `PurchaseTechnologyAngmarIceArrowsForBattleTower`: keep just the upgrade name,
  no verb (tower-specific button).
- All other Angmar research entries (IceArrows, DarkIronBlades, IceShot,
  DarkIronMail) use **"Investigar"** (researched at the Dark Iron Forge).

### Conditional term: Blades

- Default: **Espadas**.
- If the entry name or English text contains `Dwarves`, `Dwarf`, `Dwarven`,
  `Axe` or `Axes` → translate "Blades" as **Hachas**.

---

# Title Case Rules

Unit names, proper nouns, powers, abilities and upgrades use Title Case in
Spanish (e.g., "Flechas de Fuego", not "Flechas de fuego").

Lowercase exceptions (Spanish articles/prepositions/conjunctions):
`de, del, la, las, los, el, a, con, en, por, para, y, e, o, al, un, una, sin`.

- `CONTROLBAR:Construct*` entries use Title Case (e.g., "Construir Campo de Tiro").
- `OBJECT:*` (unit/building names) use Title Case (e.g., "Jinete de Huargo").
- `OBJECT:Horde*` entries use the plural unit name only, never prefixed with
  "Horda de..." (e.g., "Dwarven Zealots" → "Zelotes Enanos", not "Horda de
  Zelotes Enanos").

---

# Protected Tokens

The following tokens must never be modified (do not translate, remove, reorder
or duplicate):

```text
%1  %2  %d  %s  %PLAYER%  <TOKEN>  <VALUE>  {TOKEN}  $PLAYER  %%%  <COL>
```

SAGE hotkeys use an ampersand followed by the shortcut letter. The v1 standard
places that token at the end, e.g. `&Aragorn` becomes `Aragorn [&A]`. The letter
must remain unchanged. Hotkey markers `[&X]` and `&X` are preserved exactly.

---

# Engine Tags

Never modify engine-specific identifiers such as:

```text
CONTROLBAR:  OBJECT:  SCIENCE:  SPECIALPOWER:  UPGRADE:  WEAPON:  ARMOR:
```

---

# Formatting Rules

Preserve punctuation, meaningful capitalization, escape sequences and required
line breaks. Preserve literal `\n`, `\r\n` and `\t` sequences exactly. Stat
values (numbers, percentages like 50%, +100, 200%) must not be altered.

> **Encoding note:** This project stores `.str` files in **Windows-1252
> (latin1)**, not UTF-8. Markdown documentation (including this glossary) is
> UTF-8. Any tool that writes `.str` output must use latin1 to preserve accented
> characters.

---

# Tolkien Names

Proper names follow this policy:

1. Use the Editorial Minotauro canonical Spanish literary form when available.
2. Otherwise use the official EA Spanish localization.
3. If neither exists, preserve the original English spelling.
4. Never invent localized names.

### Names kept in original form (do not translate)

Gandalf, Aragorn, Legolas, Gimli, Frodo, Sam, Merry, Pippin, Boromir, Faramir,
Théoden, Éomer, Éowyn, Denethor, Galadriel, Elrond, Haldir, Glorfindel, Saruman,
Sauron, Mouth of Sauron, Lurtz, Wormtongue, Shelob, Gothmog, Khamûl, Morgomir,
Rogash. Places: Mordor, Isengard, Gondor, Rohan, Rivendell, Lothlórien, Minas
Tirith, Minas Morgul, Helm's Deep, Osgiliath, Fangorn, Erebor, Mirkwood.
Races: Uruk-hai, Rohirrim, Nazgûl, Ent, Haradrim, Dúnedain, Balrog.

### Names with a canonical Spanish translation

| English | Spanish | Status |
|---------|----------|--------|
| Treebeard | Bárbol | canonical |
| Witch-king | Rey Brujo | project |
| Goblins | Trasgos | canonical |
| Wargs | Huargos | canonical |
| Orcs | Orcos | canonical |
| Dwarves | Enanos | canonical |
| Elves | Elfos | canonical |
| Men | Hombres | canonical |
| Middle-earth | Tierra Media | canonical |

---

# Localization Workflow Terms

This project tracks translation state directly in the `.str` file by keeping the
current English source as a commented line above the active Spanish line:

```text
TOOLTIP:Builder
//"Movement Speed: 60 \n Vision Range: 100"
"Velocidad de movimiento: 60 \n Rango de visión: 100"
END
```

The commented English line must always match the current English reference file.
No history accumulation is kept (exactly one commented English line and one
active Spanish line per entry).
