# Task 10: PDF and multi-page input

**Build order item:** brief, "later: multi-page PDF"
**Status:** done
**Depends on:** task 5

## Goal

`/extract` accepts a PDF as well as an image. Every page goes to the model in
one call, so a total on page 2 is read together with the items on page 1.

## Files

- `app/pages.py` — new. Turn an upload into a list of images: an image passes
  through, a PDF is rendered page by page.
- `app/extractor.py` — changed. Send one image part per page.
- `app/main.py` — changed. Accept `application/pdf`; errors for bad and
  oversized PDFs.
- `pyproject.toml`, `uv.lock` — `uv add pypdfium2`.
- `tests/test_pages.py` — new. `tests/test_extractor.py` — one new case.

## Steps

1. **Dependency.** `uv add pypdfium2`. Rebuild the image afterwards; the
   Dockerfile needs no change.
2. **Render.** `pypdfium2` at `RENDER_SCALE = 2` (about 144 dpi), each page
   saved as PNG with Pillow. Constants with a comment on why the scale was
   chosen.
3. **Page cap.** `MAX_PAGES = 5`. A longer PDF is rejected with 413 and a
   clear message, not truncated: a dropped last page loses the total, and a
   partial answer that looks complete is worse than an error.
4. **One call.** The user message gets one `image_url` part per page, in
   order. For more than one page, a short text part says "The document has N
   pages, in order." `PROMPT` itself is unchanged, so image results and the
   cache for images stay as they are.
5. **Cache key.** Still the hash of the uploaded file bytes, not the rendered
   pages.
6. **Errors.** A file that is not a valid PDF → 415 with a message. Content
   types other than images and PDF → 415 as now.
7. **Harness.** `.pdf` files in `data/documents/` are picked up as they are;
   check `mimetypes` gives `application/pdf`.
8. **Tests**, no network: build a two-page PDF with Pillow in a temp
   directory; it renders to two images; the fake client receives two image
   parts and the page note; a six-page PDF gives 413; random bytes with a PDF
   content type give 415; an image still gives one part and no note.

## Done when

- [x] `uv run pytest` passes and no test opens a network connection.
- [x] `PROMPT` and `PROMPT_VERSION` are unchanged.
- [ ] Checked by the user: one real multi-page PDF from the dataset returns a
      document through `/extract`.

## Out of scope

- PDFs with a text layer read as text. Everything goes through the vision
  model, the same as images.
- Downscaling pages to save tokens — task 14, if chosen.
- More than five pages.
