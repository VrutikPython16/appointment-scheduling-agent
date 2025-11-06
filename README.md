Appointment Scheduling Agent (Backend Mock)

This project provides a mock backend for a medical clinic scheduling agent. It exposes Calendly-like endpoints using FastAPI and simulates availability and booking logic for multiple appointment types.

1) Install dependencies

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

2) Run the server

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

3) Test endpoints

See API Endpoints section below for detailed documentation.

API Endpoints

Health Check

- **GET** `/health`
  - Returns server health status
  - Response: `{"status": "ok"}`

Availability

- **GET** `/api/calendly/availability`
  - Returns available slots for a date and appointment type
  - Query Parameters:
    - `date` (required): YYYY-MM-DD
    - `appointment_type` (required): `consultation` | `followup` | `physical` | `special`
    - `doctor_id` (required): positive integer doctor ID
  - Behavior:
    - Uses the doctor’s working hours and appointment-type duration to generate slot starts.
    - For today, slots with start_time <= now are hidden.
    - Overlapping slots are omitted (list only shows free slots).
    - Dates are normalized (e.g., `2025-11-7` == `2025-11-07`).
  - Response fields:
    - `available_slots`: array of `{ start_time, end_time }` for free slots only
    - `duration_minutes`: duration used for the type
    - `interval_minutes`: interval used to step starts (same as duration)
  - Example:
    ```bash
    curl "curl --location 'http://127.0.0.1:8000/api/calendly/availability?date=2025-11-07&appointment_type=physical&doctor_id=1'"
    ```

Booking

- **POST** `/api/calendly/book`
  - Creates a new booking if the slot is valid and free
  - Request Body: `BookingRequest`
  - Validation rules:
    - Date format must be `YYYY-MM-DD`; past dates rejected (400).
    - For today, past times rejected.
    - `doctor_id` must exist; request time must lie within doctor working hours.
    - Start time must match an available slot from the availability endpoint.
    - Conflicts are rejected with `suggested_slots` (next 3 free options).
  - Status Codes:
    - `200`: confirmed
    - `409`: rejected with `suggested_slots`
  - Example:
    ```bash
      curl --location 'http://127.0.0.1:8000/api/calendly/book' \
      --header 'Content-Type: application/json' \
      --data-raw '{
          "appointment_type": "consultation",
          "date": "2025-11-07",
          "start_time": "12:00",
          "patient": {
              "name": "Vishal Raj",
              "email": "testbook@gmail.com",
              "phone": "+63521353526"
          },
          "reason": "Checkup",
          "doctor_id": 1
      }'
    ```

Appointment Types and Durations

- `consultation`: 30 minutes (default) or doctor-specific
- `followup`: 20 minutes (default) or doctor-specific
- `physical`: 45 minutes (default) or doctor-specific
- `special`: 60 minutes (default) or doctor-specific

Notes:
- Slot interval equals the appointment-type duration (starts step by duration).
- If you want 15-minute starts with 30/45/60-minute durations, this can be adjusted.

Doctor Data & Persistence

- Each doctor defines `working_hours` and `appointment_types` in `data/doctor_schedule.json`.
- Bookings are persisted to `data/doctor_schedule.json` under the doctor’s `booked_slots`.
- `booked_slots` format per date: array of objects `{ start, end, appointment_type }`.
- Dates are normalized to `YYYY-MM-DD` on read/write.

Example with doctor:

```bash
curl --location 'http://127.0.0.1:8000/api/calendly/availability?date=2025-11-07&appointment_type=physical&doctor_id=1'
```