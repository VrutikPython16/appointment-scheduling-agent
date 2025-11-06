from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import os
from backend.models.schemas import AvailabilitySlot, AppointmentType


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_doctors() -> List[dict]:
    """Load doctor data from doctor_schedule.json"""
    path = os.path.join("data", "doctor_schedule.json")
    data = _load_json(path)
    return data.get("doctors", [])


def _normalize_date_str(date_str: str) -> str:
    """Normalize date string to YYYY-MM-DD regardless of zero padding in source."""
    try:

        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        parts = date_str.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            y = parts[0]
            m = parts[1].zfill(2)
            d = parts[2].zfill(2)
            return f"{y}-{m}-{d}"
        return date_str


def _get_doctor_by_id(doctor_id: int) -> Optional[dict]:
    """Get doctor by ID"""
    doctors = _load_doctors()
    for doc in doctors:
        if doc.get("doctor_id") == doctor_id:
            return doc
    return None


def _clinic_hours_for_date(date_str: str) -> Tuple[str, str]:
    """Get clinic hours for a given date (fallback if no doctor specified)"""
    base_path = os.path.join("data", "clinic_info.json")
    data = _load_json(base_path)
    weekday = datetime.fromisoformat(date_str).strftime("%A").lower()
    hours = data.get("hours", {}).get(weekday, {"open": None, "close": None})
    return hours.get("open"), hours.get("close")


def _get_doctor_hours(doctor: dict) -> Tuple[str, str]:
    """Get working hours for a doctor"""
    wh = doctor.get("working_hours", {})
    return wh.get("start"), wh.get("end")


def _get_doctor_duration(doctor: dict, appointment_type: AppointmentType) -> Optional[int]:
    """Get appointment duration for a doctor's appointment type"""
    apt_types = doctor.get("appointment_types", {})
    return apt_types.get(appointment_type)


def _doctor_booked_slots(doctor: dict, date_str: str) -> List[Tuple[str, str]]:
    """Get booked slots for a doctor on a specific date.

    Supports two formats for backward-compatibility:
    - Old: ["09:00", "09:30", "10:00", "10:30"]
    - New: [{"start": "09:00", "end": "09:30", "appointment_type": "consultation"}, ...]
    """
    booked_map = doctor.get("booked_slots", {})
    target = _normalize_date_str(date_str)
    slots: List[Tuple[str, str]] = []
    for k, v in booked_map.items():
        if _normalize_date_str(k) != target:
            continue
        booked = v
        if isinstance(booked, list) and booked and isinstance(booked[0], dict):
            for item in booked:
                start = item.get("start")
                end = item.get("end")
                if start and end:
                    slots.append((start, end))
        elif isinstance(booked, list) and (not booked or isinstance(booked[0], str)):
            for i in range(0, len(booked), 2):
                if i + 1 < len(booked):
                    slots.append((booked[i], booked[i + 1]))
    return slots


def _is_overlapping(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return not (a_end <= b_start or a_start >= b_end)


def _generate_time_range(open_time: str, close_time: str, step_min: int) -> List[str]:
    """Generate start times between open and close, stepping by step_min."""
    fmt = "%H:%M"
    start_dt = datetime.strptime(open_time, fmt)
    end_dt = datetime.strptime(close_time, fmt)
    starts: List[str] = []
    cur = start_dt
    while cur <= end_dt:
        starts.append(cur.strftime(fmt))
        cur = cur + timedelta(minutes=step_min)
    return starts


def _suggest_next_slots(
    date_str: str,
    appointment_type: AppointmentType,
    doctor_id: Optional[int],
    from_time: str,
    limit: int = 3,
) -> List[AvailabilitySlot]:
    """Suggest next available slots on the same day after from_time."""
    slots = get_availability(date_str, appointment_type, doctor_id)
    suggestions: List[AvailabilitySlot] = []
    for slot in slots:
        if slot.available and slot.start_time >= from_time:
            suggestions.append(slot)
        if len(suggestions) >= limit:
            break
    return suggestions

def get_availability(
    date_str: str, 
    appointment_type: AppointmentType,
    doctor_id: Optional[int] = None
) -> List[AvailabilitySlot]:
    """
    Get availability for a date and appointment type.
    If doctor_id is provided, only show that doctor's availability.
    If not provided, aggregate availability across all doctors.
    """

    now_time: Optional[str] = None
    now_dt: Optional[datetime] = None
    try:
        if datetime.fromisoformat(date_str).date() == datetime.now().date():
            now_dt = datetime.now()
            now_time = now_dt.strftime("%H:%M")
    except ValueError:

        now_dt = None
        now_time = None

    if doctor_id is not None:
        doctor = _get_doctor_by_id(doctor_id)
        if not doctor:
            return []
        
        open_time, close_time = _get_doctor_hours(doctor)
        if not open_time or not close_time:
            return []
        
        duration = _get_doctor_duration(doctor, appointment_type)
        if not duration:
            return []
        

        starts = _generate_time_range(open_time, close_time, duration)

        blocks = _doctor_booked_slots(doctor, date_str)
        
        slots: List[AvailabilitySlot] = []
        for start in starts:

            end = (datetime.strptime(start, "%H:%M") + timedelta(minutes=duration)).strftime("%H:%M")

            if end > close_time:
                continue
            if now_dt is not None:

                start_dt = datetime.combine(now_dt.date(), datetime.strptime(start, "%H:%M").time())
                if start_dt <= now_dt:
                    continue
            available = True
            for b_start, b_end in blocks:
                if _is_overlapping(start, end, b_start, b_end):
                    available = False
                    break
            if available:
                slots.append(AvailabilitySlot(start_time=start, end_time=end, available=True))
        return slots
    else:
        open_time, close_time = _clinic_hours_for_date(date_str)
        if not open_time or not close_time:
            return []
        
        default_durations: Dict[AppointmentType, int] = {
            "consultation": 30,
            "followup": 20,
            "physical": 45,
            "special": 60,
        }
        duration = default_durations.get(appointment_type, 30)


        starts = _generate_time_range(open_time, close_time, duration)
        
        doctors = _load_doctors()
        blocks: List[Tuple[str, str]] = []
        for doctor in doctors:
            blocks.extend(_doctor_booked_slots(doctor, date_str))
                
        slots: List[AvailabilitySlot] = []
        for start in starts:
            end = (datetime.strptime(start, "%H:%M") + timedelta(minutes=duration)).strftime("%H:%M")
            if end > close_time:
                continue
            if now_dt is not None:
                start_dt = datetime.combine(now_dt.date(), datetime.strptime(start, "%H:%M").time())
                if start_dt <= now_dt:
                    continue
            available = True
            for b_start, b_end in blocks:
                if _is_overlapping(start, end, b_start, b_end):
                    available = False
                    break
            if available:
                slots.append(AvailabilitySlot(start_time=start, end_time=end, available=True))
        return slots
