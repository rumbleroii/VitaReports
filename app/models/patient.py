from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base

if TYPE_CHECKING:
    from app.models.allergy import Allergy
    from app.models.care_team import CareTeamMember
    from app.models.condition import Condition
    from app.models.lab_report import LabReport
    from app.models.manual_entry import ManualEntry
    from app.models.medication import Medication
    from app.models.wearable_observation import WearableObservation


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(64), nullable=False)
    blood_type: Mapped[str] = mapped_column(String(16), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    bmi: Mapped[float] = mapped_column(Float, nullable=False)
    national_id: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    emergency_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emergency_contact_relation: Mapped[str] = mapped_column(String(128), nullable=False)
    emergency_contact_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    hospital_records_sources: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    lab_records_sources: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    conditions: Mapped[list["Condition"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    medications: Mapped[list["Medication"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    allergies: Mapped[list["Allergy"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    care_team_members: Mapped[list["CareTeamMember"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    manual_entries: Mapped[list["ManualEntry"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    lab_reports: Mapped[list["LabReport"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    wearable_observations: Mapped[list["WearableObservation"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
