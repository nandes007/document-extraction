"""Turn an upload into the page images the model sees.

An image passes through untouched. A PDF is rendered page by page; any text
layer is ignored, so PDFs go through the same vision path as photos.
"""

import io

import pypdfium2 as pdfium

# PDF points are 1/72 inch, so scale 2 is about 144 dpi: small receipt print
# stays legible without sending a huge image per page.
RENDER_SCALE = 2

# Rejected, not truncated: a dropped last page usually holds the total, and a
# partial answer that looks complete is worse than an error.
MAX_PAGES = 5


class NotAPdf(Exception):
    """The upload claims to be a PDF but cannot be opened as one."""


class TooManyPages(Exception):
    """The PDF has more pages than one model call accepts."""


def to_images(data: bytes, content_type: str) -> list[tuple[bytes, str]]:
    """Return (image bytes, content type) per page, in order."""
    if content_type != "application/pdf":
        return [(data, content_type)]
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise NotAPdf(f"not a valid PDF: {exc}") from exc
    try:
        if len(pdf) > MAX_PAGES:
            raise TooManyPages(
                f"PDF has {len(pdf)} pages; at most {MAX_PAGES} are accepted"
            )
        pages = []
        for page in pdf:
            buffer = io.BytesIO()
            page.render(scale=RENDER_SCALE).to_pil().save(buffer, format="PNG")
            pages.append((buffer.getvalue(), "image/png"))
        return pages
    finally:
        pdf.close()
