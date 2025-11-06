from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
import random
import string
from typing import Tuple, Optional, List
from backend.tools.availability_tool import _load_doctors

from backend.models.schemas import BookingRequest, BookingResponse, BookingDetails
from backend.tools.availability_tool import (
    _is_overlapping,
    _get_doctor_by_id,
    _get_doctor_duration,
    _get_doctor_hours,
    _doctor_booked_slots,
    _suggest_next_slots,
    get_availability,
    _normalize_date_str,
)


def _persist_booking_to_schedule_json(
    date_str: str,
    start: str,
    end: str,
    doctor_id: Optional[int],
    appointment_type: str,
) -> None:
    """Persist the booking into data/doctor_schedule.json under the doctor's booked_slots.

    Only persists when doctor_id is provided. Appends an object with start, end, and appointment_type.
    """
    if doctor_id is None:
        return

    path = os.path.join("data", "doctor_schedule.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    doctors = data.get("doctors", [])
    for doc in doctors:
        if doc.get("doctor_id") == doctor_id:
            booked = doc.setdefault("booked_slots", {})
            normalized_date = _normalize_date_str(date_str)
            day_list = booked.setdefault(normalized_date, [])

            if day_list and isinstance(day_list[0], str):

                converted: List[dict] = []
                for i in range(0, len(day_list), 2):
                    if i + 1 < len(day_list):
                        converted.append({
                            "start": day_list[i],
                            "end": day_list[i + 1],
                            "appointment_type": appointment_type,
                        })
                booked[normalized_date] = converted
                day_list = booked[normalized_date]

            day_list.append({
                "start": start,
                "end": end,
                "appointment_type": appointment_type,
            })
            break

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _compute_end_time(start: str, minutes: int) -> str:
    fmt = "%H:%M"
    start_dt = datetime.strptime(start, fmt)
    end_dt = start_dt + timedelta(minutes=minutes)
    return end_dt.strftime(fmt)


def _generate_booking_id(date_str: str) -> str:

    seq = int(os.environ.get("_BOOKING_SEQ", "0")) + 1
    os.environ["_BOOKING_SEQ"] = str(seq)
    year = date_str.split("-")[0]
    return f"APPT-{year}-{seq:03d}"


def _generate_confirmation_code(length: int = 6) -> str:
    letters = string.ascii_uppercase + string.digits
    return "".join(random.choice(letters) for _ in range(length))


def _get_duration_for_booking(payload: BookingRequest) -> int:
    """Get appointment duration based on doctor or default"""
    if payload.doctor_id is not None:
        doctor = _get_doctor_by_id(payload.doctor_id)
        if doctor:
            duration = _get_doctor_duration(doctor, payload.appointment_type)
            if duration:
                return duration
    
    default_durations = {
        "consultation": 30,
        "followup": 20,
        "physical": 45,
        "special": 60,
    }
    return default_durations.get(payload.appointment_type, 30)


def _bookings_for_date(date_str: str, doctor_id: Optional[int] = None) -> List[Tuple[str, str]]:
    """Get all bookings for a date, optionally filtered by doctor"""
    blocks: List[Tuple[str, str]] = []
    
    norm_date = _normalize_date_str(date_str)
    if doctor_id is not None:

        doctor = _get_doctor_by_id(doctor_id)
        if doctor:
            blocks.extend(_doctor_booked_slots(doctor, norm_date))
    else:

        doctors = _load_doctors()
        for doctor in doctors:
            blocks.extend(_doctor_booked_slots(doctor, norm_date))
        
    return blocks


def create_booking(payload: BookingRequest) -> Tuple[bool, BookingResponse]:
    """Create a booking and return (success, response)"""
    duration = _get_duration_for_booking(payload)
    end_time = _compute_end_time(payload.start_time, duration)
    
    try:
        request_date = datetime.fromisoformat(payload.date).date()
        now_dt = datetime.now()
        start_dt = datetime.combine(request_date, datetime.strptime(payload.start_time, "%H:%M").time())
        if start_dt <= now_dt:
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=payload.doctor_id,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, payload.doctor_id, now_dt.strftime("%H:%M")),
            )
            return False, resp
    except ValueError:

        now_hhmm = datetime.now().strftime("%H:%M")
        resp = BookingResponse(
            booking_id="",
            status="rejected",
            confirmation_code="",
            details=BookingDetails(
                appointment_type=payload.appointment_type,
                date=payload.date,
                start_time=payload.start_time,
                end_time=end_time,
                patient=payload.patient,
                reason=payload.reason,
                doctor_id=payload.doctor_id,
            ),
            suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, payload.doctor_id, now_hhmm),
        )
        return False, resp


    if payload.doctor_id is not None:
        doctor = _get_doctor_by_id(payload.doctor_id)
        if not doctor:
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=payload.doctor_id,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, None, payload.start_time),
            )
            return False, resp

        start_h, end_h = _get_doctor_hours(doctor)
        if not start_h or not end_h or not (start_h <= payload.start_time < end_h and start_h < end_time <= end_h):
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=payload.doctor_id,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, payload.doctor_id, payload.start_time),
            )
            return False, resp


        available_slots = get_availability(payload.date, payload.appointment_type, payload.doctor_id)
        match = next((s for s in available_slots if s.available and s.start_time == payload.start_time), None)
        if match is None:
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=payload.doctor_id,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, payload.doctor_id, payload.start_time),
            )
            return False, resp


    if payload.doctor_id is None:
        day_slots = get_availability(payload.date, payload.appointment_type, None)
        match = next((s for s in day_slots if s.available and s.start_time == payload.start_time), None)
        if not match:
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=None,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, None, payload.start_time),
            )
            return False, resp


    blocks = _bookings_for_date(_normalize_date_str(payload.date), payload.doctor_id)
    for b_start, b_end in blocks:
        if _is_overlapping(payload.start_time, end_time, b_start, b_end):
            resp = BookingResponse(
                booking_id="",
                status="rejected",
                confirmation_code="",
                details=BookingDetails(
                    appointment_type=payload.appointment_type,
                    date=payload.date,
                    start_time=payload.start_time,
                    end_time=end_time,
                    patient=payload.patient,
                    reason=payload.reason,
                    doctor_id=payload.doctor_id,
                ),
                suggested_slots=_suggest_next_slots(payload.date, payload.appointment_type, payload.doctor_id, b_end),
            )
            return False, resp
    
    booking_id = _generate_booking_id(payload.date)
    code = _generate_confirmation_code()
    try:
        _persist_booking_to_schedule_json(
            payload.date,
            payload.start_time,
            end_time,
            payload.doctor_id,
            payload.appointment_type,
        )
    except Exception as e:
        print(f"Failed to persist booking to schedule JSON: {e}")
    
    resp = BookingResponse(
        booking_id=booking_id,
        status="confirmed",
        confirmation_code=code,
        details=BookingDetails(
            appointment_type=payload.appointment_type,
            date=payload.date,
            start_time=payload.start_time,
            end_time=end_time,
            patient=payload.patient,
            reason=payload.reason,
            doctor_id=payload.doctor_id,
        ),
    )
    return True, resp
