# BFME Translation Rules & Glossary

## 1. Style and Tone
* **Tone:** Epic, medieval fantasy, faithful to J.R.R. Tolkien's literary work adapted into the cinematic universe of *The Lord of the Rings*.
* **Target Audience:** Latin American Spanish players of *The Battle for Middle-earth*. Use standard, neutral Latin American Spanish terms while preserving traditional community nomenclature.

---

## 2. Protected Formatting and Syntax
* **Variables and Placeholders:** Never translate or remove variables like `%d`, `%s`, or control codes like `\n`. They must stay in the exact position they occupy in the `source` string.
* **Proper Nouns:** Keep standard Spanish translations for established names (e.g., *Rivendel* instead of Rivendell, *La Comarca* for The Shire, *Minas Tirith*, *Mordor*).
* **Factions and Units:** Maintain recognized community terms for factions (e.g., *Men of the West* -> *Hombres del Oeste*, *Isengard*, *Mordor*, *Rohan*).

---

## 3. Error Prevention
* Do not introduce extra quotes or break JSON syntax.
* If a string is a single word or a UI button (e.g., "CANCEL", "OPTIONS"), use concise imperative forms in Spanish (*CANCELAR*, *OPCIONES*).
