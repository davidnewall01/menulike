"""029 -- Add variant S3 keys to photos.

Image optimisation pipeline: on upload, generate resized WebP variants
(original_webp, large, medium, thumb) alongside the raw original.  s3_key
is repurposed to point at the capped original WebP; s3_key_raw holds the
untouched upload.

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("s3_key_raw", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("s3_key_large", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("s3_key_medium", sa.String(), nullable=True))
    op.add_column("photos", sa.Column("s3_key_thumb", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "s3_key_thumb")
    op.drop_column("photos", "s3_key_medium")
    op.drop_column("photos", "s3_key_large")
    op.drop_column("photos", "s3_key_raw")
