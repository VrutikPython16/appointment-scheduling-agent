from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, date as _date
from typing import Optional

from backend.models.schemas import (
    AvailabilityResponse,
    BookingRequest,
)
from backend.tools.availability_tool import get_availability, _get_doctor_by_id, _get_doctor_duration
from backend.tools.booking_tool import create_booking


router = APIRouter(prefix="/api/calendly", tags=["calendly"])


@router.get("/availability", response_model=AvailabilityResponse)
def availability(
    date: str = Query(..., description="YYYY-MM-DD"),
    appointment_type: str = Query(..., description="consultation|followup|physical|special"),
    doctor_id: Optional[int] = Query(..., description="doctor ID to filter availability"),
):
    appointment_type_l = appointment_type.lower()
    if appointment_type_l not in {"consultation", "followup", "physical", "special"}:
        raise HTTPException(status_code=400, detail="Invalid appointment_type")


    try:
        requested_date = datetime.fromisoformat(date).date()
    except ValueError:
        raise HTTPException(status_code=400, detail={
            "message": "Invalid date format. Use YYYY-MM-DD.",
        })
    if requested_date < _date.today():
        raise HTTPException(status_code=400, detail={
            "message": "Date is in the past. Choose today or a future date.",
        })


    if doctor_id is not None:
        if _get_doctor_by_id(doctor_id) is None:
            raise HTTPException(status_code=404, detail={
                "message": "Doctor not found",
                "doctor_id": doctor_id,
            })
    slots = get_availability(date, appointment_type_l, doctor_id)

    duration_minutes = None
    if doctor_id is not None:
        doc = _get_doctor_by_id(doctor_id)
        if doc:
            duration_minutes = _get_doctor_duration(doc, appointment_type_l) or None
    if duration_minutes is None:
        default_durations = {"consultation": 30, "followup": 20, "physical": 45, "special": 60}
        duration_minutes = default_durations.get(appointment_type_l, 30)

    return AvailabilityResponse(
        date=date,
        appointment_type=appointment_type_l, 
        doctor_id=doctor_id,
        available_slots=slots,
        duration_minutes=duration_minutes,
        interval_minutes=duration_minutes,
    )


@router.post("/book")
def book(payload: BookingRequest):

    try:
        requested_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail={
            "message": "Invalid date format. Use YYYY-MM-DD.",
        })
    if requested_date < _date.today():
        raise HTTPException(status_code=400, detail={
            "message": "Date is in the past. Choose today or a future date.",
        })

    if requested_date == _date.today():
        try:
            start_dt = datetime.combine(requested_date, datetime.strptime(payload.start_time, "%H:%M").time())
        except ValueError:
            raise HTTPException(status_code=400, detail={
                "message": "Invalid start_time format. Use HH:MM.",
            })
        if start_dt <= datetime.now():
            raise HTTPException(status_code=409, detail={
                "message": "Requested time is in the past.",
            })

    ok, resp = create_booking(payload)
    if not ok:
        raise HTTPException(status_code=409, detail=resp.model_dump())
    return resp