# `eval-compare` skill usage log

The project's custom coding-agent extension is the Claude Code skill in
`.claude/skills/eval-compare/SKILL.md`. It compares two saved eval runs,
reports regressions and fixes by field and failure kind, and stops on a
regression. Every use is logged here, newest last.

### 2026-10-07 — 20261007-051452 vs 20261007-083154

- **Why:** noise measurement (same model `dots-3-note-preview:free`, prompt v1)
- **Found:** REGRESSION by the gate (merchant_name accuracy dropped); value fields 44/48 -> 44/48. One flip each way: food_receipts03 merchant_name correct -> wrong_value (branch appended), fuel_receipts02 subtotal missed -> correct.
- **Next:** kept as the noise floor: one flip per field each way between identical runs is noise, not a change. No prompt change made from it; work moved on to PDF input and the larger dataset (tasks 10-11) before judging prompt v2.

### 2026-10-08 — v1-full vs v1-checks

- **Why:** abstention rule alone (task 12): same raw model answers (prompt v1, all candidate documents from cache), with arithmetic checks and the 0.9 confidence threshold applied
- **Found:** REGRESSION by the gate (subtotal, discount, tax, total accuracy dropped); value fields 119/144 -> 113/144, hallucinated 11 -> 6. 5 hallucinations fixed (service_charge x3, subtotal, discount); 11 correct values became misses, all from a failed `totals` or `line_items_sum` check abstaining every amount on service_receipts01, test_food_receipts04, test_service_note02, test_service_note07.
- **Next:** accepted the trade-off (fewer hallucinations, more misses); runs committed, then recalibrated the threshold on v2-full dev

### 2026-10-08 — v1-checks vs v2-full

- **Why:** prompt v2 (2026-10-07 labelling rules: subtotal, payment method, document type), same checks and threshold
- **Found:** REGRESSION by the gate (merchant_name, service_charge accuracy dropped); value fields 113/144 -> 119/144, hallucinated 6 -> 3. 17 fixes (subtotal, total, tax, discount, payment_method card rule); 9 regressions: payment_method qris -> other x3, subtotal missed x3, merchant_name, service_charge hallucinated, tax missed. Line items precision 0.931 -> 0.821. service_receipts01 took 737 s and 74k completion tokens over 2 attempts.
- **Next:** accepted the trade-off (fewer hallucinations, more misses); runs committed, then recalibrated the threshold on v2-full dev
