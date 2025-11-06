from __future__ import annotations

from fastapi import FastAPI

from backend.api.calendly_integration import router as calendly_router


app = FastAPI(title="Appointment Scheduling Agent (Mock)")
app.include_router(calendly_router)


@app.get("/health")
def health():
    return {"status": "ok"}



