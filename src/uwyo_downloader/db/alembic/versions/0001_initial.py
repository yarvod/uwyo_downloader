from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("src", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soundings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(), nullable=False),
        sa.Column("station_name", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column(
            "downloaded_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            name="fk_soundings_station",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_id", "captured_at", name="uq_sounding_station_time"),
    )
    op.create_index("idx_stations_name", "stations", ["name"])
    op.create_index(
        "idx_soundings_station_time", "soundings", ["station_id", "captured_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_soundings_station_time", table_name="soundings")
    op.drop_index("idx_stations_name", table_name="stations")
    op.drop_table("soundings")
    op.drop_table("stations")
