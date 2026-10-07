# Task 11: Dataset, about 14 more documents and a test split

**Build order item:** brief, "sample documents and ground truth are shipped"
**Status:** todo
**Owner:** user. The agent writes only the label checker.

## Goal

About 20 labelled documents, roughly 8 `dev` and 12 `test`, covering all four
document types, handwriting and multi-page PDFs. The source of every document
is recorded.

Why now: six `dev` documents cannot show whether a prompt change generalises.
The `test` split has to exist, untouched, before prompt v2 is tuned on `dev`.

## Files

- `data/documents/`, `data/ground_truth/` — new files, by the user.
- `docs/dataset.md` — new, by the user. One row per document.
- `evals/check_labels.py` — new, by the agent. Validates ground truth files;
  never writes them.
- `tests/test_check_labels.py` — new, by the agent.

## Steps

1. **Collect** (user): own scans and photos first; handwritten notes,
   vehicle service notes, two or three multi-page PDFs. Fill the gaps in
   `vehicle_service` and `retail`.
2. **Personal data** (user): cover or crop names, phone numbers, card numbers
   and plates before committing. Keep the `contains_personal_data` tag on
   documents that had any.
3. **Assign the split before labelling** (user), spread across document
   types. A `test` document is never shown to the model while the prompt is
   being changed: run once for the baseline, once for the final version.
4. **Label** (user) by `docs/labeling-guide.md`, from the image. `test` labels
   are not drafted with the model under evaluation.
5. **`docs/dataset.md`** (user): file, document type, split, source (own
   photo, public dataset with its licence, received from someone), what was
   redacted.
6. **Label checker** (agent), `uv run python evals/check_labels.py`:
   - every document has a ground truth file and the other way round
   - `file` matches the document name; `split` is `dev` or `test`
   - statuses are valid; `value` is null unless `present`
   - dates parse as ISO; amounts are integers; `payment_method` and
     `document_type` are allowed values
   - prints a count by type and split; exits 1 on any problem, naming the
     file and field
7. **Tests** for the checker, using a temp directory; never the real
   `data/ground_truth/`.

## Done when

- [ ] About 20 documents, at least 10 in `test`, every document type present.
- [ ] `uv run python evals/check_labels.py` exits 0.
- [ ] `docs/dataset.md` has a row for every document.
- [ ] No unredacted personal data in committed images.
- [ ] `uv run pytest` passes.

## Out of scope

- The agent writing or correcting labels. It may report what the checker
  finds; the user fixes it.
- Synthetic or generated receipts presented as real ones.
