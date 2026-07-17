from app.models.allergy import Allergy
from app.models.care_team import CareTeamMember
from app.models.condition import Condition
from app.models.hospital_source import HospitalSource
from app.models.lab_source import LabSource
from app.models.medication import Medication
from app.models.patient import Patient
from app.schemas.profile import PatientProfileCreate, PatientProfileOut


def profile_to_patient(payload: PatientProfileCreate) -> Patient:
    demo = payload.demographics
    contact = demo.emergency_contact
    return Patient(
        patient_id=payload.patient_id,
        name=demo.name,
        date_of_birth=demo.date_of_birth,
        gender=demo.gender,
        blood_type=demo.blood_type,
        height_cm=demo.height_cm,
        weight_kg=demo.weight_kg,
        bmi=demo.bmi,
        national_id=demo.national_id,
        city=demo.city,
        emergency_contact_name=contact.name,
        emergency_contact_relation=contact.relation,
        emergency_contact_phone=contact.phone,
        conditions=[
            Condition(
                icd10=c.icd10,
                name=c.name,
                diagnosed=c.diagnosed,
                status=c.status,
                severity=c.severity,
                managing_facility=c.managing_facility,
            )
            for c in payload.conditions
        ],
        medications=[
            Medication(
                name=m.name,
                dose=m.dose,
                frequency=m.frequency,
                scheduled_time=m.scheduled_time,
                indication=m.indication,
                prescriber=m.prescriber,
                start_date=m.start_date,
            )
            for m in payload.medications
        ],
        allergies=[
            Allergy(
                substance=a.substance,
                reaction=a.reaction,
                severity=a.severity,
                note=a.note,
            )
            for a in payload.allergies
        ],
        care_team_members=[
            CareTeamMember(
                name=m.name,
                specialty=m.specialty,
                facility=m.facility,
                last_visit=m.last_visit,
                next_appointment=m.next_appointment,
            )
            for m in payload.care_team
        ],
        hospital_sources=[
            HospitalSource(facility_name=name) for name in payload.hospital_records_sources
        ],
        lab_sources=[LabSource(facility_name=name) for name in payload.lab_records_sources],
    )


def patient_to_profile(patient: Patient) -> PatientProfileOut:
    return PatientProfileOut(
        patient_id=patient.patient_id,
        demographics={
            "name": patient.name,
            "date_of_birth": patient.date_of_birth,
            "gender": patient.gender,
            "blood_type": patient.blood_type,
            "height_cm": patient.height_cm,
            "weight_kg": patient.weight_kg,
            "bmi": patient.bmi,
            "national_id": patient.national_id,
            "city": patient.city,
            "emergency_contact": {
                "name": patient.emergency_contact_name,
                "relation": patient.emergency_contact_relation,
                "phone": patient.emergency_contact_phone,
            },
        },
        conditions=[
            {
                "icd10": c.icd10,
                "name": c.name,
                "diagnosed": c.diagnosed,
                "status": c.status,
                "severity": c.severity,
                "managing_facility": c.managing_facility,
            }
            for c in patient.conditions
        ],
        medications=[
            {
                "name": m.name,
                "dose": m.dose,
                "frequency": m.frequency,
                "scheduled_time": m.scheduled_time,
                "indication": m.indication,
                "prescriber": m.prescriber,
                "start_date": m.start_date,
            }
            for m in patient.medications
        ],
        allergies=[
            {
                "substance": a.substance,
                "reaction": a.reaction,
                "severity": a.severity,
                "note": a.note,
            }
            for a in patient.allergies
        ],
        care_team=[
            {
                "name": m.name,
                "specialty": m.specialty,
                "facility": m.facility,
                "last_visit": m.last_visit,
                "next_appointment": m.next_appointment,
            }
            for m in patient.care_team_members
        ],
        hospital_records_sources=[s.facility_name for s in patient.hospital_sources],
        lab_records_sources=[s.facility_name for s in patient.lab_sources],
    )
