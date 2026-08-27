"""Initial SecureVista schema

Revision ID: 001
Revises:
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'operator', 'responder')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source_uri", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'offline', 'frozen', 'blackout', 'unknown')",
            name="ck_cameras_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("polygon_points", sa.Text(), nullable=False),
        sa.Column("zone_type", sa.String(), nullable=False),
        sa.Column("risk_level", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "zone_type IN ('restricted', 'monitored', 'safe')",
            name="ck_zones_zone_type",
        ),
        sa.CheckConstraint("risk_level BETWEEN 1 AND 5", name="ck_zones_risk_level"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("start_time", sa.String(), nullable=False),
        sa.Column("end_time", sa.String(), nullable=False),
        sa.Column("days_of_week", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("schema_version", sa.String(), nullable=True),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("raw_metadata", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ("
            "'restricted_zone_entry', 'after_hours_presence', 'loitering', "
            "'camera_offline', 'camera_frozen', 'camera_blackout')",
            name="ck_observations_event_type",
        ),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_observations_confidence"),
        sa.CheckConstraint("impact_score BETWEEN 0 AND 1", name="ck_observations_impact"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("dedup_hash", sa.String(), nullable=True),
        sa.Column("correlation_window_start", sa.DateTime(), nullable=True),
        sa.Column("correlation_window_end", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'investigating', 'escalated', 'resolved')",
            name="ck_incidents_status",
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("prev_hash", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "incident_observations",
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.PrimaryKeyConstraint("incident_id", "observation_id"),
    )
    op.create_table(
        "evidence_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("clip_path", sa.String(), nullable=False),
        sa.Column("manifest_hash", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_packages")
    op.drop_table("incident_observations")
    op.drop_table("audit_log")
    op.drop_table("incidents")
    op.drop_table("observations")
    op.drop_table("schedules")
    op.drop_table("zones")
    op.drop_table("cameras")
    op.drop_table("users")
