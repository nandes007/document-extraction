"""Turn an upload into the page images the model reads.

An image passes through as it is. A PDF is rendered page by page, so a total
on page 2 reaches the model in the same call as the items on page 1.
"""

from io import BytesIO

import pypdfium2 as pdfium

PDF = "application/pdf"

# Scale 2 is about 144 dpi (PDF units are 1/72 inch): small receipt print stays
# legible without sending a huge image per page.
RENDER_SCALE = 2

# Rejected, not truncated: a dropped last page loses the total, and a partial
# answer that looks complete is worse than an error.
MAX_PAGES = 5


class NotAPdf(ValueError):
    """Sent as a PDF, but pdfium cannot open it."""


class TooManyPages(ValueError):
    """More pages than one call is allowed to carry."""


def to_images(data: bytes, content_type: str) -> list[tuple[bytes, str]]:
    """Return (image bytes, content type) per page, in order."""
    if content_type != PDF:
        return [(data, content_type)]
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:  # a RuntimeError, which main maps to 500
        raise NotAPdf(f"not a valid PDF: {exc}") from exc
    try:
        if len(pdf) > MAX_PAGES:
            raise TooManyPages(
                f"PDF has {len(pdf)} pages; at most {MAX_PAGES} are accepted"
            )
        images = []
        for page in pdf:
            buffer = BytesIO()
            page.render(scale=RENDER_SCALE).to_pil().save(buffer, "PNG")
            images.append((buffer.getvalue(), "image/png"))
        return images
    finally:
        pdf.close()
