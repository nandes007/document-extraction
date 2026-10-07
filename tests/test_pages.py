from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.pages import MAX_PAGES, NotAPdf, TooManyPages, to_images


def make_pdf(pages: int) -> bytes:
    """A real PDF, built with Pillow: one blank page per image."""
    images = [Image.new("RGB", (200, 300), "white") for _ in range(pages)]
    buffer = BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_image_passes_through():
    assert to_images(b"jpeg bytes", "image/jpeg") == [(b"jpeg bytes", "image/jpeg")]


def test_two_page_pdf_renders_two_pngs():
    images = to_images(make_pdf(2), "application/pdf")
    assert [kind for _, kind in images] == ["image/png", "image/png"]
    assert Image.open(BytesIO(images[0][0])).format == "PNG"


def test_too_many_pages_is_rejected():
    with pytest.raises(TooManyPages):
        to_images(make_pdf(MAX_PAGES + 1), "application/pdf")


def test_random_bytes_are_not_a_pdf():
    with pytest.raises(NotAPdf):
        to_images(b"\x00not a pdf at all", "application/pdf")


# --- the API surface; both errors happen before any provider call --------

client = TestClient(app)


def test_api_rejects_six_pages_with_413():
    pdf = make_pdf(MAX_PAGES + 1)
    response = client.post("/extract", files={"file": ("a.pdf", pdf, "application/pdf")})
    assert response.status_code == 413
    assert "pages" in response.json()["detail"]


def test_api_rejects_invalid_pdf_with_415():
    response = client.post(
        "/extract", files={"file": ("a.pdf", b"garbage", "application/pdf")}
    )
    assert response.status_code == 415
