"""AuthContext — the resolved identity for admin requests."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: uuid.UUID
    role: str
    site_id: uuid.UUID | None

    @property
    def is_internal_admin(self) -> bool:
        return self.role == "internal_admin"

    @property
    def scoped_site_id(self) -> uuid.UUID | None:
        """The site this user is scoped to (None for internal_admin)."""
        return self.site_id

    def can(self, action: str) -> bool:
        """Capability stub — always True for now. Real catalogue deferred."""
        return True
