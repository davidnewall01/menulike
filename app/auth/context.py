"""AuthContext — the resolved identity for admin requests."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: uuid.UUID
    email: str
    role: str
    site_id: uuid.UUID | None
    # Set ONLY for internal_admin via the signed act-as cookie.
    # Owners NEVER populate this field — see scoped_site_id below.
    acting_site_id: uuid.UUID | None = None

    @property
    def is_internal_admin(self) -> bool:
        return self.role == "internal_admin"

    @property
    def scoped_site_id(self) -> uuid.UUID | None:
        """The site this request is scoped to.

        ╔══════════════════════════════════════════════════════════════╗
        ║  SECURITY CONTRACT — this branch order is LOAD-BEARING.    ║
        ║                                                            ║
        ║  1. Branch on role FIRST.                                  ║
        ║  2. Owners ALWAYS return User.site_id from the DB.         ║
        ║     The acting_site_id field is NEVER read for owners —    ║
        ║     not "read and rejected", but never read at all.        ║
        ║  3. Only internal_admin returns acting_site_id.             ║
        ║  4. role is loaded FRESH from the DB every request, so a   ║
        ║     demoted admin's token is harmless — role=owner in DB   ║
        ║     means the owner branch runs, acting_site_id ignored.   ║
        ║                                                            ║
        ║  DO NOT reorder these branches. DO NOT add an "or" that    ║
        ║  lets owners reach acting_site_id. The next dev won't      ║
        ║  have the audit — this comment IS the audit.               ║
        ╚══════════════════════════════════════════════════════════════╝
        """
        if not self.is_internal_admin:
            # OWNER PATH — User.site_id from DB, always. acting_site_id
            # is structurally unreachable here regardless of token contents.
            return self.site_id

        # ADMIN PATH — return the acting site from the signed cookie,
        # or None if the admin hasn't picked a site (→ NoSiteInScope).
        return self.acting_site_id

    def can(self, action: str) -> bool:
        """Capability check — NOT YET IMPLEMENTED. Raises to fail closed."""
        raise NotImplementedError(
            "Capability catalogue not yet built. "
            "Do not call .can() until it is wired up."
        )
