from fastapi import FastAPI, HTTPException
import uvicorn
import httpx
import pandas as pd
from collector import get_prometheus_data
from preprocess import transform_to_prophet_df
from model import forecast_resource_usage, generate_llm_report, calculate_recovery_impact

app = FastAPI()

BACKEND_URL = "http://localhost:8000"

METRIC_LIST = {
    "cpu": "dummy_cpu_usage",
    "memory": "dummy_memory_usage",
    "requests": "dummy_request_count",
    "lt_memory": "infra_load_test_memory_mb",
    "lt_disk": "infra_load_test_disk_mb",
    "memory_leak": "infra_memory_leak_mb",
    "fd_ratio": "infra_fd_usage_ratio"
}

THRESHOLD_MAP = {
    "cpu": 85.0,
    "memory": 85.0,
    "lt_memory": 240.0,
    "lt_disk": 240.0,
    "memory_leak": 100.0,
    "fd_ratio": 0.8
}

async def get_recovery_events():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BACKEND_URL}/api/v1/recovery-actions", timeout=2.0)
            if response.status_code == 200:
                actions = response.json()
                if not actions:
                    return None

                events = pd.DataFrame([
                    {
                        'holiday': f"heal_{a['action_type']}",
                        'ds': pd.to_datetime(a['executed_at']),
                        'lower_window': 0,
                        'upper_window': 0.01
                    } for a in actions if a['status'] == 'success'
                ])
                if events.empty:
                    return None
                return events
    except Exception as e:
        print(f"[Warning] 복구 이력 로드 실패: {e}")
    return None

@app.get("/")
def read_root():
    return {"message": "AIOps 예측 서버가 실행 중입니다."}

@app.get("/predict/forecast/{type}")
async def get_forecast(type: str):
    if type not in METRIC_LIST:
        raise HTTPException(status_code=400, detail="지원하지 않는 메트릭 타입입니다.")

    target_metric = METRIC_LIST[type]
    threshold = THRESHOLD_MAP.get(type, 70.0)

    try:
        raw = get_prometheus_data(metric_name=target_metric, hours=24)
        if not raw:
            return {"message": "데이터가 부족합니다.", "llm_context": "데이터 부족으로 예측 불가"}

        heal_events = await get_recovery_events()
        clean_df = transform_to_prophet_df(raw)
        forecast_df = forecast_resource_usage(clean_df, periods=60, events=heal_events)

        peak_yhat = forecast_df['yhat'].max()
        breach_data = forecast_df[forecast_df['yhat'] >= threshold]
        expected_time = breach_data['ds'].iloc[0].strftime('%H:%M') if not breach_data.empty else None

        avg_spread = (forecast_df['yhat_upper'] - forecast_df['yhat_lower']).mean()
        confidence_score = max(0, 1 - (avg_spread / (peak_yhat if peak_yhat > 0 else 100)))

        impact_result = None
        if heal_events is not None:
            impact_result = calculate_recovery_impact(clean_df, heal_events)

        llm_message = generate_llm_report(
            metric_type=type,
            peak_value=peak_yhat,
            expected_time=expected_time,
            confidence=confidence_score,
            threshold=threshold,
            is_recovered=heal_events is not None,
            impact=impact_result
        )

        return {
            "metric": type,
            "prometheus_name": target_metric,
            "threshold": threshold,
            "peak_predicted": round(peak_yhat, 2),
            "expected_breach_time": expected_time,
            "llm_context": llm_message,
            "recovery_applied": heal_events is not None,
            "forecast_data": forecast_df.tail(10).to_dict(orient="records"),
            "recovery_impact": impact_result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
