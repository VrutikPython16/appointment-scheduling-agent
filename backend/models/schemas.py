from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, EmailStr


AppointmentType = Literal["consultation", "followup", "physical", "special"]


class AvailabilitySlot(BaseModel):
    start_time: str = Field(description="HH:MM in clinic local time")
    end_time: str = Field(description="HH:MM in clinic local time")
    available: bool


class AvailabilityResponse(BaseModel):
    date: str
    appointment_type: AppointmentType
    doctor_id: Optional[int] = None
    available_slots: List[AvailabilitySlot]
    duration_minutes: Optional[int] = None
    interval_minutes: Optional[int] = None


class Patient(BaseModel):
    name: str
    email: EmailStr
    phone: str


class BookingRequest(BaseModel):
    appointment_type: AppointmentType
    date: str
    start_time: str
    patient: Patient
    reason: Optional[str] = None
    doctor_id: Optional[int] = None


class BookingDetails(BaseModel):
    appointment_type: AppointmentType
    date: str
    start_time: str
    end_time: str
    patient: Patient
    reason: Optional[str] = None
    doctor_id: Optional[int] = None


class BookingResponse(BaseModel):
    booking_id: str
    status: Literal["confirmed", "rejected"]
    confirmation_code: str
    details: BookingDetails
    suggested_slots: Optional[List[AvailabilitySlot]] = None


