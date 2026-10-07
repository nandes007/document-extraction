# `eval-compare` skill usage log

The project's custom coding-agent extension is the Claude Code skill in
`.claude/skills/eval-compare/SKILL.md`. It compares two saved eval runs,
reports regressions and fixes by field and failure kind, and stops on a
regression. Every use is logged here, newest last.

### 2026-10-07 — 20261007-051452 vs 20261007-083154

- **Why:** noise measurement (same model `dots-3-note-preview:free`, prompt v1)
- **Found:** REGRESSION by the gate (merchant_name accuracy dropped); value fields 44/48 -> 44/48. One flip each way: food_receipts03 merchant_name correct -> wrong_value (branch appended), fuel_receipts02 subtotal missed -> correct.
- **Next:** pending
