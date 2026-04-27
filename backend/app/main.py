# backend/app/main.py
from contextlib import asynccontextmanager  # 표준 라이브러리
import importlib

from fastapi import FastAPI  # 서드파티
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    alert_events,
    alerts,
    incidents,
    metrics,
    predictions,
    actions,
)  # 로컬
from app.core.config import settings
from app.scheduler import create_scheduler

importlib.import_module("app.models.schema")  # noqa: F401 — ORM 모델 registry 등록용


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="AIOps AutoHealing API",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_V1_PREFIX = settings.API_V1_STR

app.include_router(alerts.router, prefix=API_V1_PREFIX, tags=["Alerts"])
app.include_router(incidents.router, prefix=API_V1_PREFIX, tags=["Incidents"])
app.include_router(predictions.router, prefix=API_V1_PREFIX, tags=["Predictions"])
app.include_router(alert_events.router, prefix=API_V1_PREFIX, tags=["Alert Events"])
app.include_router(metrics.router, prefix=API_V1_PREFIX, tags=["Metrics"])
app.include_router(actions.router, prefix=API_V1_PREFIX, tags=["Actions"])


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
