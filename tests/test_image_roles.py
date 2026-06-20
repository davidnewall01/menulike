"""Image role assignment tests — service-level, scoping, IDOR, reassign."""

import uuid

import pytest
from sqlalchemy import select

from app.auth.context import AuthContext
from app.models.photo import Photo
from app.models.site_image_role import SiteImageRole
from app.services import image_role_service
from app.services.exceptions import InvalidRole, PhotoNotFound, NoSiteInScope
from tests.conftest import make_owner, make_site


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_photo(db_session, site, filename="test.jpg") -> Photo:
    """Insert a photo row directly (no S3)."""
    photo = Photo(
        site_id=site.site_id,
        s3_key=f"sites/{site.site_id}/photos/{uuid.uuid4()}.jpg",
        original_filename=filename,
        content_type="image/jpeg",
        width=100,
        height=80,
    )
    db_session.add(photo)
    await db_session.flush()
    return photo


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


# ---------------------------------------------------------------------------
# Assign happy path
# ---------------------------------------------------------------------------

class TestAssign:

    async def test_assign_hero(self, db_session):
        site = await make_site(db_session, slug="role-assign")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        assignment = await image_role_service.assign(db_session, auth, "feature_images", photo.photo_id)
        assert assignment.role == "feature_images"
        assert assignment.photo_id == photo.photo_id
        assert assignment.site_id == site.site_id
        assert assignment.position == 0

    async def test_assign_logo(self, db_session):
        site = await make_site(db_session, slug="role-logo")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        assignment = await image_role_service.assign(db_session, auth, "logo", photo.photo_id)
        assert assignment.role == "logo"
        assert assignment.photo_id == photo.photo_id


# ---------------------------------------------------------------------------
# Reassign — must replace cleanly, leaving exactly one row
# ---------------------------------------------------------------------------

class TestReassign:

    async def test_reassign_replaces_existing(self, db_session):
        """Reassigning a role replaces the old row — exactly one row remains."""
        site = await make_site(db_session, slug="role-reassign")
        owner = await make_owner(db_session, site)
        photo_a = await _make_photo(db_session, site, "a.jpg")
        photo_b = await _make_photo(db_session, site, "b.jpg")
        auth = _auth(owner)

        await image_role_service.assign(db_session, auth, "feature_images", photo_a.photo_id)
        await image_role_service.assign(db_session, auth, "feature_images", photo_b.photo_id)

        result = await db_session.execute(
            select(SiteImageRole).where(
                SiteImageRole.site_id == site.site_id,
                SiteImageRole.role == "feature_images",
            )
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].photo_id == photo_b.photo_id

    async def test_reassign_twice_leaves_one_row(self, db_session):
        """Three successive assigns → exactly one row, pointing to the last photo."""
        site = await make_site(db_session, slug="role-reassign-3x")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.assign(db_session, auth, "logo", p.photo_id)

        result = await db_session.execute(
            select(SiteImageRole).where(
                SiteImageRole.site_id == site.site_id,
                SiteImageRole.role == "logo",
            )
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].photo_id == photos[-1].photo_id


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:

    async def test_clear_removes_assignment(self, db_session):
        site = await make_site(db_session, slug="role-clear")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        await image_role_service.assign(db_session, auth, "feature_images", photo.photo_id)
        await image_role_service.clear(db_session, auth, "feature_images")

        result = await db_session.execute(
            select(SiteImageRole).where(
                SiteImageRole.site_id == site.site_id,
                SiteImageRole.role == "feature_images",
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_clear_nonexistent_role_is_noop(self, db_session):
        """Clearing a role with no assignment doesn't error."""
        site = await make_site(db_session, slug="role-clear-noop")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        # Should not raise
        await image_role_service.clear(db_session, auth, "logo")


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListRoles:

    async def test_list_returns_assignments(self, db_session):
        site = await make_site(db_session, slug="role-list")
        owner = await make_owner(db_session, site)
        photo_h = await _make_photo(db_session, site, "hero.jpg")
        photo_l = await _make_photo(db_session, site, "logo.png")
        auth = _auth(owner)

        await image_role_service.assign(db_session, auth, "feature_images", photo_h.photo_id)
        await image_role_service.assign(db_session, auth, "logo", photo_l.photo_id)

        roles = await image_role_service.list_roles(db_session, auth)
        assert len(roles) == 2
        role_names = {r.role for r in roles}
        assert role_names == {"feature_images", "logo"}

    async def test_list_empty_site(self, db_session):
        site = await make_site(db_session, slug="role-list-empty")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        roles = await image_role_service.list_roles(db_session, auth)
        assert roles == []


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

class TestLoadRoleImages:

    async def test_load_returns_photo_dict(self, db_session):
        site = await make_site(db_session, slug="role-load")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        await image_role_service.assign(db_session, auth, "feature_images", photo.photo_id)

        images = await image_role_service.load_role_images(db_session, site.site_id)
        assert "feature_images" in images
        assert len(images["feature_images"]) == 1
        assert images["feature_images"][0].photo_id == photo.photo_id

    async def test_load_empty_site(self, db_session):
        site = await make_site(db_session, slug="role-load-empty")

        images = await image_role_service.load_role_images(db_session, site.site_id)
        assert images == {}


# ---------------------------------------------------------------------------
# IDOR — foreign photo / foreign site
# ---------------------------------------------------------------------------

class TestIDOR:

    async def test_assign_foreign_photo_rejected(self, db_session):
        """Owner A cannot assign a photo belonging to site B."""
        site_a = await make_site(db_session, slug="role-idor-a")
        site_b = await make_site(db_session, slug="role-idor-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)

        with pytest.raises(PhotoNotFound):
            await image_role_service.assign(db_session, auth_a, "feature_images", photo_b.photo_id)

        # No assignment should exist
        result = await db_session.execute(
            select(SiteImageRole).where(SiteImageRole.site_id == site_a.site_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_clear_only_affects_own_site(self, db_session):
        """Clearing a role on site A does not touch site B's assignments."""
        site_a = await make_site(db_session, slug="role-idor-clear-a")
        site_b = await make_site(db_session, slug="role-idor-clear-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await image_role_service.assign(db_session, auth_b, "feature_images", photo_b.photo_id)
        await image_role_service.clear(db_session, auth_a, "feature_images")

        # B's assignment should still exist
        result = await db_session.execute(
            select(SiteImageRole).where(
                SiteImageRole.site_id == site_b.site_id,
                SiteImageRole.role == "feature_images",
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_list_only_returns_own_site(self, db_session):
        """List roles for site A does not include site B's assignments."""
        site_a = await make_site(db_session, slug="role-idor-list-a")
        site_b = await make_site(db_session, slug="role-idor-list-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await image_role_service.assign(db_session, auth_b, "feature_images", photo_b.photo_id)

        roles_a = await image_role_service.list_roles(db_session, auth_a)
        assert roles_a == []


# ---------------------------------------------------------------------------
# Unknown role key
# ---------------------------------------------------------------------------

class TestInvalidRole:

    async def test_assign_unknown_role_rejected(self, db_session):
        site = await make_site(db_session, slug="role-bad-key")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        with pytest.raises(InvalidRole):
            await image_role_service.assign(db_session, auth, "banner", photo.photo_id)

    async def test_clear_unknown_role_rejected(self, db_session):
        site = await make_site(db_session, slug="role-bad-clear")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        with pytest.raises(InvalidRole):
            await image_role_service.clear(db_session, auth, "about_image")


# ---------------------------------------------------------------------------
# No site in scope
# ---------------------------------------------------------------------------

class TestNoScope:

    async def test_assign_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)

        with pytest.raises(NoSiteInScope):
            await image_role_service.assign(db_session, auth, "logo", uuid.uuid4())

    async def test_list_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)

        with pytest.raises(NoSiteInScope):
            await image_role_service.list_roles(db_session, auth)

    async def test_clear_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)

        with pytest.raises(NoSiteInScope):
            await image_role_service.clear(db_session, auth, "logo")


# ---------------------------------------------------------------------------
# Multi-image: add_to_role
# ---------------------------------------------------------------------------

class TestAddToRole:

    async def test_add_appends_at_next_position(self, db_session):
        site = await make_site(db_session, slug="multi-add")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "feature_images", p.photo_id)

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "feature_images")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 3
        assert [r.photo_id for r in rows] == [p.photo_id for p in photos]
        assert [r.position for r in rows] == [0, 1, 2]

    async def test_add_foreign_photo_rejected(self, db_session):
        """Adding a photo from another site raises PhotoNotFound."""
        site_a = await make_site(db_session, slug="multi-add-idor-a")
        site_b = await make_site(db_session, slug="multi-add-idor-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)

        with pytest.raises(PhotoNotFound):
            await image_role_service.add_to_role(db_session, auth_a, "feature_images", photo_b.photo_id)

        # No row should exist
        result = await db_session.execute(
            select(SiteImageRole).where(SiteImageRole.site_id == site_a.site_id)
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Multi-image: remove_from_role
# ---------------------------------------------------------------------------

class TestRemoveFromRole:

    async def test_remove_specific_photo(self, db_session):
        site = await make_site(db_session, slug="multi-rm")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "feature_images", p.photo_id)

        # Remove the middle one
        await image_role_service.remove_from_role(db_session, auth, "feature_images", photos[1].photo_id)

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "feature_images")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 2
        assert [r.photo_id for r in rows] == [photos[0].photo_id, photos[2].photo_id]

    async def test_remove_nonexistent_is_noop(self, db_session):
        """Removing a photo_id not in the role doesn't error."""
        site = await make_site(db_session, slug="multi-rm-noop")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site)
        auth = _auth(owner)

        await image_role_service.add_to_role(db_session, auth, "feature_images", photo.photo_id)

        # Remove a random UUID that's not assigned
        await image_role_service.remove_from_role(db_session, auth, "feature_images", uuid.uuid4())

        result = await db_session.execute(
            select(SiteImageRole).where(SiteImageRole.site_id == site.site_id)
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Multi-image: reorder_role
# ---------------------------------------------------------------------------

class TestReorderRole:

    async def test_reorder_reverses(self, db_session):
        site = await make_site(db_session, slug="multi-reorder")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "feature_images", p.photo_id)

        # Reverse order
        reversed_ids = [p.photo_id for p in reversed(photos)]
        await image_role_service.reorder_role(db_session, auth, "feature_images", reversed_ids)

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "feature_images")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        assert [r.photo_id for r in rows] == reversed_ids

    async def test_reorder_preserves_set(self, db_session):
        """Reorder with a subset keeps unmentioned members at the end."""
        site = await make_site(db_session, slug="multi-reorder-subset")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "feature_images", p.photo_id)

        # Submit only photos[2] — photos[0] and [1] should trail
        await image_role_service.reorder_role(
            db_session, auth, "feature_images", [photos[2].photo_id]
        )

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "feature_images")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 3
        assert rows[0].photo_id == photos[2].photo_id

    async def test_reorder_foreign_id_ignored(self, db_session):
        """A non-member photo_id in the reorder list is silently ignored."""
        site_a = await make_site(db_session, slug="multi-reorder-foreign-a")
        site_b = await make_site(db_session, slug="multi-reorder-foreign-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        photo_a = await _make_photo(db_session, site_a, "a.jpg")
        photo_b = await _make_photo(db_session, site_b, "b.jpg")
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await image_role_service.add_to_role(db_session, auth_a, "feature_images", photo_a.photo_id)
        await image_role_service.add_to_role(db_session, auth_b, "feature_images", photo_b.photo_id)

        # Try to sneak B's photo into A's reorder — should be ignored
        await image_role_service.reorder_role(
            db_session, auth_a, "feature_images",
            [photo_b.photo_id, photo_a.photo_id],
        )

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site_a.site_id, SiteImageRole.role == "feature_images")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        # Only photo_a should remain — photo_b was silently filtered out
        assert len(rows) == 1
        assert rows[0].photo_id == photo_a.photo_id

        # B's assignment untouched
        result_b = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site_b.site_id, SiteImageRole.role == "feature_images")
        )
        assert result_b.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Gallery role — confirm it works through the generic multi-image path
# ---------------------------------------------------------------------------

class TestGalleryRole:

    async def test_gallery_add_and_order(self, db_session):
        """Gallery role uses add_to_role — appends at sequential positions."""
        site = await make_site(db_session, slug="gallery-add")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"g{i}.jpg") for i in range(3)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "gallery", p.photo_id)

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "gallery")
            .order_by(SiteImageRole.position)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 3
        assert [r.photo_id for r in rows] == [p.photo_id for p in photos]
        assert [r.position for r in rows] == [0, 1, 2]

    async def test_gallery_foreign_photo_rejected(self, db_session):
        """Adding a photo from another site to gallery raises PhotoNotFound."""
        site_a = await make_site(db_session, slug="gallery-idor-a")
        site_b = await make_site(db_session, slug="gallery-idor-b")
        owner_a = await make_owner(db_session, site_a)
        photo_b = await _make_photo(db_session, site_b)
        auth_a = _auth(owner_a)

        with pytest.raises(PhotoNotFound):
            await image_role_service.add_to_role(db_session, auth_a, "gallery", photo_b.photo_id)

    async def test_gallery_remove(self, db_session):
        site = await make_site(db_session, slug="gallery-rm")
        owner = await make_owner(db_session, site)
        photos = [await _make_photo(db_session, site, f"g{i}.jpg") for i in range(2)]
        auth = _auth(owner)

        for p in photos:
            await image_role_service.add_to_role(db_session, auth, "gallery", p.photo_id)

        await image_role_service.remove_from_role(db_session, auth, "gallery", photos[0].photo_id)

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "gallery")
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].photo_id == photos[1].photo_id

    async def test_gallery_reorder_rejects_non_member(self, db_session):
        """A non-member photo_id in gallery reorder is silently ignored."""
        site = await make_site(db_session, slug="gallery-reorder-foreign")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site, "g.jpg")
        auth = _auth(owner)

        await image_role_service.add_to_role(db_session, auth, "gallery", photo.photo_id)

        # Try to sneak a random UUID into the reorder — should be ignored
        fake_id = uuid.uuid4()
        await image_role_service.reorder_role(
            db_session, auth, "gallery", [fake_id, photo.photo_id]
        )

        result = await db_session.execute(
            select(SiteImageRole)
            .where(SiteImageRole.site_id == site.site_id, SiteImageRole.role == "gallery")
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].photo_id == photo.photo_id

    async def test_gallery_in_load_role_images(self, db_session):
        """load_role_images returns gallery photos alongside other roles."""
        site = await make_site(db_session, slug="gallery-load")
        owner = await make_owner(db_session, site)
        photo = await _make_photo(db_session, site, "g.jpg")
        auth = _auth(owner)

        await image_role_service.add_to_role(db_session, auth, "gallery", photo.photo_id)

        images = await image_role_service.load_role_images(db_session, site.site_id)
        assert "gallery" in images
        assert len(images["gallery"]) == 1
        assert images["gallery"][0].photo_id == photo.photo_id
