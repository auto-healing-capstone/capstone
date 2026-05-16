import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from collector import get_prometheus_data, COLLECTION_HOURS
from preprocess import transform_to_prophet_df, validate_dataframe
from model import forecast_metric, FORECAST_PERIODS
from anomaly_detector import detect_anomaly
from calibrator import schedule_calibration, get_calibration_status, METRIC_NAME_MAP
import cache as forecast_cache

logger = logging.getLogger(__name__)

app = FastAPI()

METRIC_LIST: dict[str, str] = {
    "cpu": "dummy_cpu_usage",
    "memory": "dummy_memory_usage",
    "lt_memory": "infra_load_test_memory_mb",
    "lt_disk": "infra_load_test_disk_mb",
    # Group A
    "memory_leak": "infra_memory_leak_mb",
    "fd_ratio": "infra_fd_usage_ratio",
}

THRESHOLD_MAP: dict[str, float] = {
    "cpu": 85.0,
    "memory": 85.0,
    "lt_memory": 240.0,
    "lt_disk": 240.0,
    "memory_leak": 100.0,
    "fd_ratio": 0.8,
}


@app.get("/")
def read_root():
    return {"message": "AIOps 예측 서버가 실행 중입니다."}


@app.get("/predict/forecast/{type}")
async def get_forecast(type: str):
    if type not in METRIC_LIST:
        raise HTTPException(status_code=400, detail="지원하지 않는 메트릭 타입입니다.")

    # §2 캐시 HIT → 연산 없이 즉시 반환 (비동기 파이프라인)
    cache_key = f"forecast:{type}"
    cached = forecast_cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache HIT for %s", type)
        return cached

    target_metric = METRIC_LIST[type]
    threshold = THRESHOLD_MAP.get(type, 70.0)
    hours = COLLECTION_HOURS.get(type, 24)
    periods = FORECAST_PERIODS.get(type, 60)

    try:
        raw = get_prometheus_data(metric_name=target_metric, hours=hours)
        if not raw:
            return {
                "metric": type,
                "anomaly_level": "UNKNOWN",
                "message": "데이터가 부족합니다.",
                "llm_context": "데이터 부족으로 예측 불가",
            }

        clean_df = transform_to_prophet_df(raw)
        if not validate_dataframe(clean_df):
            return {
                "metric": type,
                "anomaly_level": "UNKNOWN",
                "message": "유효 데이터 포인트 부족",
                "llm_context": "데이터 부족으로 예측 불가",
            }

        forecast_df = forecast_metric(clean_df, metric_type=type, periods=periods)
        result = detect_anomaly(forecast_df, metric_type=type, threshold=threshold)

        forecast_points = [
            {
                "ds": row["ds"].isoformat(),
                "yhat": round(float(row["yhat"]), 4),
                "yhat_lower": round(float(row["yhat_lower"]), 4),
                "yhat_upper": round(float(row["yhat_upper"]), 4),
            }
            for _, row in forecast_df.iterrows()
        ]

        response = {
            "metric": type,
            "full_name": target_metric,
            "threshold": threshold,
            "anomaly_level": result["anomaly_level"],
            "anomaly_score": result["anomaly_score"],
            "reason": result["reason"],
            "breach_time": result["breach_time"],
            "breach_duration_min": result["breach_duration_min"],
            "recommended_action": result["recommended_action"],
            "peak_predicted": result["peak_predicted"],
            "forecast": forecast_points,
            "llm_context": None,
        }

        # §2 캐시 MISS → 결과 저장 (5분 TTL)
        forecast_cache.set(cache_key, response)
        logger.debug("Cache SET for %s (TTL=300s)", type)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CalibrateRequest(BaseModel):
    recovered_at: str  # ISO8601 형식 ("2024-01-01T12:00:00")
    action_type: str = "unknown"


@app.post("/calibrate/{type}")
async def calibrate(type: str, body: CalibrateRequest):
    if type not in METRIC_NAME_MAP:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 메트릭: {type}")

    try:
        recovered_at = datetime.fromisoformat(body.recovered_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="recovered_at은 ISO8601 형식이어야 합니다."
        )

    # §2 캐시 무효화 — 복구 완료 시점에 오래된 예측값이 반환되지 않도록
    forecast_cache.invalidate(f"forecast:{type}")
    logger.info("Cache invalidated for %s (calibration triggered)", type)

    scheduled = schedule_calibration(type, recovered_at)
    return {
        "status": "scheduled" if scheduled else "skipped",
        "metric": type,
        "recovered_at": body.recovered_at,
        "window_minutes": 15,
    }


@app.get("/calibrate/status")
async def calibrate_status():
    return get_calibration_status()


@app.get("/cache/stats")
async def cache_stats():
    """§2 캐시 진단 — 각 메트릭의 캐시 잔여 TTL 조회."""
    return forecast_cache.stats()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "models_supported": list(METRIC_NAME_MAP.keys()),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
