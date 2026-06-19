"""Photo library tests — CRUD, scoping, IDOR, CSRF. Storage layer mocked."""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from tests.conftest import (
    csrf_token_for,
    make_owner,
    make_site,
)
from app.core.security import encode_session
from app.models.photo import Photo


def _make_jpeg_bytes(width=100, height=80) -> bytes:
    """Create minimal valid JPEG bytes."""
    buf = BytesIO()
    img = Image.new("RGB", (width, height), "red")
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes() -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (10, 10), "blue")
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _make_photo(db_session, site, filename="test.jpg", alt_text=None) -> Photo:
    """Insert a photo row directly (no S3)."""
    photo = Photo(
        site_id=site.site_id,
        s3_key=f"sites/{site.site_id}/photos/{uuid.uuid4()}.jpg",
        original_filename=filename,
        content_type="image/jpeg",
        width=100,
        height=80,
        alt_text=alt_text,
    )
    db_session.add(photo)
    await db_session.flush()
    return photo


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

class TestPhotoUpload:

    @patch("app.services.photo_service.storage.upload", new_callable=AsyncMock)
    async def test_upload_valid_jpeg(self, mock_upload, client, db_session):
        site = await make_site(db_session, slug="photo-upload")
        owner = await make_owner(db_session, site)
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        jpeg_data = _make_jpeg_bytes()

        resp = await client.post(
            "/admin/photos",
            cookies={"session": cookie},
            files={"file": ("dish.jpg", jpeg_data, "image/jpeg")},
            data={"csrf_token": token},
        )
        assert resp.status_code == 303
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        assert call_args[0][0] == jpeg_data  # data bytes
        assert call_args[0][2] == "image/jpeg"  # content_type

    @patch("app.services.photo_service.storage.upload", new_callable=AsyncMock)
    async def test_upload_disallowed_type_rejected(self, mock_upload, client, db_session):
        site = await make_site(db_session, slug="photo-badtype")
        owner = await make_owner(db_session, site)
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/photos",
            cookies={"session": cookie},
            files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"csrf_token": token},
        )
        # Should re-render with error, not redirect
        assert resp.status_code == 200
        assert "not allowed" in resp.text.lower()
        mock_upload.assert_not_called()

    async def test_upload_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="photo-nocsrf")
        owner = await make_owner(db_session, site)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/photos",
            cookies={"session": cookie},
            files={"file": ("dish.jpg", _make_jpeg_bytes(), "image/jpeg")},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Alt text tests
# ---------------------------------------------------------------------------

class TestPhotoAlt:

    async def test_update_alt_text(self, client, db_session):
        site = await make_site(db_session, slug="photo-alt")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            f"/admin/photos/{photo.photo_id}/alt",
            cookies={"session": cookie},
            data={"csrf_token": token, "alt_text": "A delicious pasta dish"},
        )
        assert resp.status_code == 200
        await db_session.refresh(photo)
        assert photo.alt_text == "A delicious pasta dish"

    async def test_update_alt_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="photo-alt-nocsrf")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            f"/admin/photos/{photo.photo_id}/alt",
            cookies={"session": cookie},
            data={"alt_text": "No CSRF"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------

class TestPhotoDelete:

    @patch("app.services.photo_service.storage.delete", new_callable=AsyncMock)
    async def test_delete_removes_row_and_calls_storage(self, mock_delete, client, db_session):
        site = await make_site(db_session, slug="photo-del")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        s3_key = photo.s3_key
        photo_id = photo.photo_id
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            f"/admin/photos/{photo_id}/delete",
            cookies={"session": cookie},
            data={"csrf_token": token},
        )
        assert resp.status_code == 200
        mock_delete.assert_called_once_with(s3_key)

        # Row should be gone
        from sqlalchemy import select
        result = await db_session.execute(
            select(Photo).where(Photo.photo_id == photo_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="photo-del-nocsrf")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            f"/admin/photos/{photo.photo_id}/delete",
            cookies={"session": cookie},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# IDOR tests
# ---------------------------------------------------------------------------

class TestPhotoIDOR:

    async def test_alt_foreign_photo_returns_404(self, client, db_session):
        """Owner A cannot update alt text on owner B's photo."""
        site_a = await make_site(db_session, slug="photo-idor-a")
        site_b = await make_site(db_session, slug="photo-idor-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b, alt_text="B original")

        token = csrf_token_for(owner_a)
        cookie = encode_session(owner_a.user_id)

        resp = await client.post(
            f"/admin/photos/{photo_b.photo_id}/alt",
            cookies={"session": cookie},
            data={"csrf_token": token, "alt_text": "Hijacked"},
        )
        assert resp.status_code == 404

        # B's photo untouched
        await db_session.refresh(photo_b)
        assert photo_b.alt_text == "B original"

    @patch("app.services.photo_service.storage.delete", new_callable=AsyncMock)
    async def test_delete_foreign_photo_returns_404(self, mock_delete, client, db_session):
        """Owner A cannot delete owner B's photo."""
        site_a = await make_site(db_session, slug="photo-idor-del-a")
        site_b = await make_site(db_session, slug="photo-idor-del-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b)

        token = csrf_token_for(owner_a)
        cookie = encode_session(owner_a.user_id)

        resp = await client.post(
            f"/admin/photos/{photo_b.photo_id}/delete",
            cookies={"session": cookie},
            data={"csrf_token": token},
        )
        assert resp.status_code == 404
        mock_delete.assert_not_called()

        # B's photo still exists
        from sqlalchemy import select
        result = await db_session.execute(
            select(Photo).where(Photo.photo_id == photo_b.photo_id)
        )
        assert result.scalar_one_or_none() is not None
