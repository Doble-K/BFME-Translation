# AI Prompt: Reconcile Local Glossary with the Upstream BFME-Translation Project

## Purpose

This document is a self-contained prompt for an AI assistant. It describes every
known difference between two glossaries for the same game (*The Lord of the
Rings: The Battle for Middle-earth II: The Rise of the Witch-king*, ROTWK 2.02):

- **Local project** — `lotr-spanish-translation` (this repository). Authoritative
  terminology lives in `.kiro/agents/game-tooltip-translator.md`; a mirror is in
  `docs/GLOSSARY.md`. Target variety: **European Spanish (Spain)**, Editorial
  Minotauro canonical Tolkien names. Large, already-refined glossary (100+ terms).
- **Upstream project** — [Doble-K/BFME-Translation](https://github.com/Doble-K/BFME-Translation).
  Target variety: **Latin American Spanish**. Early-stage glossary (~13 RTS terms,
  many marked `pending`).

## Task for the AI

Read both glossaries and produce a reconciliation plan (a merge proposal /
issue / PR description) that:

1. Confirms the terms where both projects already agree.
2. Resolves each conflict listed below with a clear recommendation and rationale.
3. Flags every decision that requires a human choice (especially Spanish variety).
4. Preserves all protected tokens, engine tags and formatting conventions.
5. Never invents terminology; when unsure, mark the term `needs_review`.

Respond in **English** (project documentation standard), using the upstream
`GLOSSARY.md` table structure (`| English | Spanish | Status | Context |`).

---

## Background Difference (most important)

The core divergence is **not** term-by-term. It is:

1. **Spanish variety.** Upstream = Latin American Spanish. Local = European
   Spanish (Spain) with Editorial Minotauro names. This is a foundational
   decision that must be made **before** merging any terms. Every term below is
   only valid for the local project if the Spain + Minotauro variety is accepted.
2. **Maturity.** Upstream leaves most lore terms `pending` and defers to
   community review. Local has already decided them.
3. **State tracking mechanism.** Upstream uses catalog statuses
   (`pending / translated / preserved / needs_review`). Local comments the
   English source with `//` directly above the active Spanish line inside the
   `.str` file. Same goal (traceability), different mechanism.
4. **Encoding.** Local `.str` files are strictly **Windows-1252 (latin1)**;
   upstream assumes UTF-8/JSON. Markdown glossaries are UTF-8 in both, so the
   glossary merge itself is safe, but any pipeline crossing must convert encoding.

---

## 1. Terms Where Both Projects Agree

No conflict. Adopt as-is.

| English | Spanish |
|---------|----------|
| Summon | Invocar |
| Recruit | Reclutar |
| Upgrade | Mejora |
| Build Time | Tiempo de construcción |
| Command Points | Puntos de mando |
| Structure | Estructura |
| Damage | Daño |
| Armor | Armadura |
| Health | Salud |
| Hero | Héroe |

---

## 2. Direct Terminology Conflicts (same English, different or undecided Spanish)

| English | Upstream | Local | Recommendation / Note |
|---------|----------|-------|-----------------------|
| Power | Poder (`pending`) | Poder | Same term. Local can promote it from `pending` to approved. |
| Spell | Undecided ("Power vs Spell vs Ability" pending) | Hechizo | Local already resolved. Propose **Hechizo**. |
| Horde | Horda (`pending`) | Horda + rule: `OBJECT:Horde*` uses the plural unit name only, never "Horda de..." | Adopt **Horda** and add the local `OBJECT:Horde*` rule (more precise). |
| Rally Point | Punto de reunión | (not listed locally) | Adopt upstream term into local glossary. |
| Troll | (not defined in main glossary) | **Trol** (pl. Troles) | CONFLICT: local castilianizes to "Trol". Also note local `CONTEXT` file has an outdated "Trolls → Trolls" line that should be cleaned up. |

---

## 3. Proper Noun / Race Conflicts (biggest divergence)

Upstream leaves these `pending`; local has canonical decisions.

| English | Upstream | Local | Note |
|---------|----------|-------|------|
| Goblin/Goblins | `pending` | Trasgo/Trasgos | Local follows Minotauro. |
| Warg/Wargs | `pending` | Huargo/Huargos | Local follows Minotauro. |
| Orc | `pending` | Orco | Local follows Minotauro. |
| Uruk | `pending` | Uruk-hai (kept) | Not translated. |
| Witch-king | Not defined; upstream policy preserves Tolkien names | **Rey Brujo** | HARD CONFLICT: upstream would keep "Witch-king"; local translates to "Rey Brujo". Needs explicit decision. |
| Treebeard | (not listed) | Bárbol | Local has the canonical form. |
| Half-Troll | (not listed) | Semitrol/Semitroles | Local only. |

---

## 4. Terms That Exist Only Locally (net additions to upstream)

The local glossary contributes a large layer upstream lacks: damage types,
mod-specific units, and conditional rules.

- Damage types: `Slash → Cortante`, `Pierce → Perforante`.
- Do-not-translate gaming terms: `Debuff/Buff` (kept in English — see conflict 5).
- Ammo/upgrades/units: `Bolts → Virotes`, `Oathbreakers → Rompejuramentos`,
  `Signal Fire → Almenara`, `Outpost → Enclave`, `Mumak → Mûmak/Mûmakil`, and
  dozens of mod unit names (see `docs/GLOSSARY.md`, "Mod-Specific" section).
- Conditional rules upstream does not have:
  - **Blades → Espadas**, except in a Dwarven context (Dwarf/Dwarven/Axe/Axes)
    → **Hachas**.
  - **PurchaseTechnology** entries → "Investigar [Name]" / "Comprar" with the
    Angmar exceptions.
  - **Title Case** rules for unit/building names, with the lowercase exception
    list (`de, del, la, las, los, el, a, con, en, por, para, y, e, o, al, un,
    una, sin`).

Recommendation: these can be adopted upstream with **no conflict**, provided the
Spanish variety decision is settled. They only strengthen the shared glossary.

---

## 5. Convention Conflicts (not term-level)

| Topic | Upstream | Local | Note |
|-------|----------|-------|------|
| Debuff / Buff | General rule would flag as `needs_review` / never invent | Explicit decision: **do not translate** (keep "Debuff"/"Buff") | Propose adding an explicit "Do Not Translate" section upstream. |
| Hotkey convention | `&Aragorn` → `Aragorn [&A]` | `[&X]` / `&X` preserved exactly | Compatible. Local matches the upstream v1 standard. |
| State tracking | Catalog statuses | Commented `//` English line in `.str` | Different mechanism; document both, do not force one. |
| Encoding | UTF-8 / JSON | Windows-1252 (latin1) for `.str` | Glossary merge safe; flag for any pipeline integration. |

---

## Summary of Decisions the Human Must Make

1. **Spanish variety**: Latin American (upstream) vs. Spain + Minotauro (local).
   This gates everything else.
2. **Witch-king**: preserve the Tolkien name (upstream policy) vs. "Rey Brujo"
   (local).
3. **Troll**: castilianize to "Trol/Troles" (local) vs. leave undefined
   (upstream). Clean up the contradictory legacy "Trolls → Trolls" line in the
   local `CONTEXT` file either way.
4. **Debuff/Buff**: keep in English (local) vs. flag for review (upstream).
5. **Promote upstream `pending` terms** (Goblin, Warg, Orc, Horde, Power) using
   the local decisions — valid only if the Spain + Minotauro variety is accepted.

## Deliverable Format

Produce a single Markdown document containing:

- A short "Decisions required" section listing items 1–5 above with a
  recommended default and a one-line rationale each.
- A merged term table in upstream `| English | Spanish | Status | Context |`
  format, with a `Status` of `pending` for any term still blocked by decision 1.
- A "No conflict" appendix listing the agreed and net-new terms ready to adopt.
