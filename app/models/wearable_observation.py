from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base

if TYPE_CHECKING:
    from app.models.patient import Patient


class WearableObservation(Base):
    __tablename__ = "wearable_observations"
    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "fingerprint",
            name="uq_wearable_patient_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    hk_type: Mapped[str] = mapped_column(String(128), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value_raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    value_normalized: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    patient: Mapped["Patient"] = relationship(back_populates="wearable_observations")
