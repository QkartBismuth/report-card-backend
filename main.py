import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401
from database import Base, engine
from routes import (
    admin as admin_router,
    analytics as analytics_router,
    auth as auth_router,
    export as export_router,
    groups as groups_router,
    ktc as ktc_router,
    push as push_router,
    schedule as schedule_router,
    sessions as sessions_router,
    students as students_router,
    subjects as subjects_router,
    upload as upload_router,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Рапортичка API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(groups_router.router)
app.include_router(students_router.router)
app.include_router(subjects_router.router)
app.include_router(sessions_router.router)
app.include_router(export_router.router)
app.include_router(upload_router.router)
app.include_router(admin_router.router)
app.include_router(analytics_router.router)
app.include_router(push_router.router)
app.include_router(ktc_router.router)
app.include_router(schedule_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=False)