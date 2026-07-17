from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.patient import Patient


class HospitalSource(Base):
    __tablename__ = "hospital_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False
    )
    facility_name: Mapped[str] = mapped_column(String(255), nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="hospital_sources")
