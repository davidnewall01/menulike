"""Content-block service tests — CRUD, IDOR, empty-block rejection."""

import uuid

import pytest
from sqlalchemy import select

from app.auth.context import AuthContext
from app.models.content_block import ContentBlock
from app.models.photo import Photo
from app.services import content_block_service
from app.services.exceptions import ContentBlockNotFound, EmptyBlock, NoSiteInScope, PhotoNotFound
from tests.conftest import make_owner, make_site


PAGE_KEY = "our_story"


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


async def _make_photo(db_session, site, filename="test.jpg") -> Photo:
    photo = Photo(
        site_id=site.site_id,
        s3_key=f"sites/{site.site_id}/photos/{uuid.uuid4()}.jpg",
        original_filename=filename,
        content_type="image/jpeg",
        width=800,
        height=600,
    )
    db_session.add(photo)
    await db_session.flush()
    return photo


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreateBlock:

    async def test_create_with_heading(self, db_session):
        site = await make_site(db_session, slug="cb-create")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(
            db_session, auth, PAGE_KEY, "Our History", None
        )
        assert block.heading == "Our History"
        assert block.body is None
        assert block.position == 0
        assert block.page_key == PAGE_KEY

    async def test_create_with_body(self, db_session):
        site = await make_site(db_session, slug="cb-create-body")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(
            db_session, auth, PAGE_KEY, None, "Some story text."
        )
        assert block.heading is None
        assert block.body == "Some story text."

    async def test_create_positions_increment(self, db_session):
        site = await make_site(db_session, slug="cb-pos")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        b1 = await content_block_service.create_block(db_session, auth, PAGE_KEY, "A", None)
        b2 = await content_block_service.create_block(db_session, auth, PAGE_KEY, "B", None)
        assert b1.position == 0
        assert b2.position == 1

    async def test_create_empty_rejected(self, db_session):
        site = await make_site(db_session, slug="cb-empty")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        with pytest.raises(EmptyBlock):
            await content_block_service.create_block(db_session, auth, PAGE_KEY, None, None)

    async def test_create_whitespace_only_rejected(self, db_session):
        site = await make_site(db_session, slug="cb-ws")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        with pytest.raises(EmptyBlock):
            await content_block_service.create_block(db_session, auth, PAGE_KEY, "  ", "  ")


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdateBlock:

    async def test_update_heading_and_body(self, db_session):
        site = await make_site(db_session, slug="cb-update")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Old", "Old body")
        updated = await content_block_service.update_block(db_session, auth, block.block_id, "New", "New body")
        assert updated.heading == "New"
        assert updated.body == "New body"

    async def test_update_to_empty_rejected(self, db_session):
        """Cannot update a block to be fully empty (no heading, no body, no image)."""
        site = await make_site(db_session, slug="cb-update-empty")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)
        with pytest.raises(EmptyBlock):
            await content_block_service.update_block(db_session, auth, block.block_id, None, None)

    async def test_update_text_to_empty_ok_if_image_set(self, db_session):
        """If a block has an image, clearing heading+body is allowed."""
        site = await make_site(db_session, slug="cb-update-img-ok")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)
        await content_block_service.set_block_image(db_session, auth, block.block_id, photo.photo_id)
        updated = await content_block_service.update_block(db_session, auth, block.block_id, None, None)
        assert updated.heading is None
        assert updated.body is None
        assert updated.image_photo_id == photo.photo_id


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDeleteBlock:

    async def test_delete_removes_block(self, db_session):
        site = await make_site(db_session, slug="cb-delete")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Gone", None)
        await content_block_service.delete_block(db_session, auth, block.block_id)

        result = await db_session.execute(
            select(ContentBlock).where(ContentBlock.block_id == block.block_id)
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Set / clear image
# ---------------------------------------------------------------------------

class TestBlockImage:

    async def test_set_image(self, db_session):
        site = await make_site(db_session, slug="cb-img")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)
        updated = await content_block_service.set_block_image(db_session, auth, block.block_id, photo.photo_id)
        assert updated.image_photo_id == photo.photo_id

    async def test_clear_image(self, db_session):
        site = await make_site(db_session, slug="cb-img-clear")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)
        await content_block_service.set_block_image(db_session, auth, block.block_id, photo.photo_id)
        cleared = await content_block_service.clear_block_image(db_session, auth, block.block_id)
        assert cleared.image_photo_id is None

    async def test_clear_image_rejected_if_block_empty(self, db_session):
        """Cannot clear image if block has no heading or body (would be fully empty)."""
        site = await make_site(db_session, slug="cb-img-clear-empty")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        # Create block with heading, set image, then clear heading
        block = await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)
        await content_block_service.set_block_image(db_session, auth, block.block_id, photo.photo_id)
        await content_block_service.update_block(db_session, auth, block.block_id, None, None)

        # Now block is image-only — clearing image would make it empty
        with pytest.raises(EmptyBlock):
            await content_block_service.clear_block_image(db_session, auth, block.block_id)


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

class TestReorderBlocks:

    async def test_reorder_reverses(self, db_session):
        site = await make_site(db_session, slug="cb-reorder")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        blocks = []
        for i in range(3):
            b = await content_block_service.create_block(db_session, auth, PAGE_KEY, f"Block {i}", None)
            blocks.append(b)

        reversed_ids = [b.block_id for b in reversed(blocks)]
        await content_block_service.reorder_blocks(db_session, auth, PAGE_KEY, reversed_ids)

        result = await db_session.execute(
            select(ContentBlock)
            .where(ContentBlock.site_id == site.site_id, ContentBlock.page_key == PAGE_KEY)
            .order_by(ContentBlock.position)
        )
        rows = list(result.scalars().all())
        assert [r.block_id for r in rows] == reversed_ids


# ---------------------------------------------------------------------------
# IDOR — foreign block_id / foreign photo_id
# ---------------------------------------------------------------------------

class TestIDOR:

    async def test_update_foreign_block_rejected(self, db_session):
        site_a = await make_site(db_session, slug="cb-idor-a")
        site_b = await make_site(db_session, slug="cb-idor-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        block_b = await content_block_service.create_block(db_session, auth_b, PAGE_KEY, "B's block", None)

        with pytest.raises(ContentBlockNotFound):
            await content_block_service.update_block(db_session, auth_a, block_b.block_id, "Hacked", None)

    async def test_delete_foreign_block_rejected(self, db_session):
        site_a = await make_site(db_session, slug="cb-idor-del-a")
        site_b = await make_site(db_session, slug="cb-idor-del-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        block_b = await content_block_service.create_block(db_session, auth_b, PAGE_KEY, "B's block", None)

        with pytest.raises(ContentBlockNotFound):
            await content_block_service.delete_block(db_session, auth_a, block_b.block_id)

    async def test_set_image_foreign_block_rejected(self, db_session):
        """Foreign block_id → ContentBlockNotFound."""
        site_a = await make_site(db_session, slug="cb-idor-img-a")
        site_b = await make_site(db_session, slug="cb-idor-img-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        photo_a = await _make_photo(db_session, site_a)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        block_b = await content_block_service.create_block(db_session, auth_b, PAGE_KEY, "B's block", None)

        with pytest.raises(ContentBlockNotFound):
            await content_block_service.set_block_image(db_session, auth_a, block_b.block_id, photo_a.photo_id)

    async def test_set_image_foreign_photo_rejected(self, db_session):
        """Foreign photo_id → PhotoNotFound."""
        site_a = await make_site(db_session, slug="cb-idor-photo-a")
        site_b = await make_site(db_session, slug="cb-idor-photo-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)

        block_a = await content_block_service.create_block(db_session, auth_a, PAGE_KEY, "A's block", None)

        with pytest.raises(PhotoNotFound):
            await content_block_service.set_block_image(db_session, auth_a, block_a.block_id, photo_b.photo_id)

    async def test_list_only_returns_own_site(self, db_session):
        site_a = await make_site(db_session, slug="cb-idor-list-a")
        site_b = await make_site(db_session, slug="cb-idor-list-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await content_block_service.create_block(db_session, auth_b, PAGE_KEY, "B's block", None)

        blocks_a = await content_block_service.list_blocks(db_session, auth_a, PAGE_KEY)
        assert blocks_a == []


# ---------------------------------------------------------------------------
# No scope
# ---------------------------------------------------------------------------

class TestNoScope:

    async def test_create_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)
        with pytest.raises(NoSiteInScope):
            await content_block_service.create_block(db_session, auth, PAGE_KEY, "Title", None)

    async def test_list_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)
        with pytest.raises(NoSiteInScope):
            await content_block_service.list_blocks(db_session, auth, PAGE_KEY)
