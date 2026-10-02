# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring

- **`CONTEXT.md`** at the repo root.

If the file does not exist, proceed silently. The `/domain-modeling` skill creates domain documentation lazily when terms are resolved.

## File structure

This is a single-context repository:

/
├── CONTEXT.md
└── src/

## Use the glossary's vocabulary

When output names a domain concept—in an issue title, refactor proposal, hypothesis, or test name—use the term defined in `CONTEXT.md`. Do not drift to synonyms that the glossary explicitly avoids.

If a needed concept is absent, reconsider whether it belongs to the project language or note the gap for `/domain-modeling`.
