import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.pages import MAX_PAGES, NotAPdf, TooManyPages, to_images


def make_pdf(pages: int) -> bytes:
    """A PDF with `pages` blank pages, built with Pillow."""
    images = [Image.new("RGB", (100, 140), "white") for _ in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_image_passes_through():
    assert to_images(b"jpeg bytes", "image/jpeg") == [(b"jpeg bytes", "image/jpeg")]


def test_two_page_pdf_renders_to_two_pngs():
    pages = to_images(make_pdf(2), "application/pdf")
    assert len(pages) == 2
    for data, content_type in pages:
        assert content_type == "image/png"
        assert Image.open(io.BytesIO(data)).format == "PNG"


def test_too_many_pages_is_rejected():
    with pytest.raises(TooManyPages):
        to_images(make_pdf(MAX_PAGES + 1), "application/pdf")


def test_random_bytes_are_not_a_pdf():
    with pytest.raises(NotAPdf):
        to_images(b"definitely not a pdf", "application/pdf")


# --- the API surface: rejected before any provider configuration is read ---

client = TestClient(app)


def test_api_rejects_six_page_pdf_with_413():
    response = client.post(
        "/extract", files={"file": ("a.pdf", make_pdf(6), "application/pdf")}
    )
    assert response.status_code == 413
    assert "at most 5" in response.json()["detail"]


def test_api_rejects_invalid_pdf_with_415():
    response = client.post(
        "/extract", files={"file": ("a.pdf", b"garbage", "application/pdf")}
    )
    assert response.status_code == 415
