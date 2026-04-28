from fastapi import FastAPI, HTTPException
import uvicorn
from collector import get_prometheus_data
from preprocess import transform_to_prophet_df
from model import forecast_resource_usage
from model import generate_llm_report

app = FastAPI()

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


@app.get("/")
def read_root():
    return {"message": "AIOps 예측 서버가 살아있습니다!"}


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

        clean_df = transform_to_prophet_df(raw)
        forecast_df = forecast_resource_usage(clean_df, periods=60)

        peak_yhat = forecast_df['yhat'].max()
        
        # 임계치 초과 시점 계산
        breach_data = forecast_df[forecast_df['yhat'] >= threshold]
        expected_time = breach_data['ds'].iloc[0].strftime('%H:%M') if not breach_data.empty else None

        # 신뢰도 계산 (예측폭 기준)
        avg_spread = (forecast_df['yhat_upper'] - forecast_df['yhat_lower']).mean()
        confidence_score = max(0, 1 - (avg_spread / (peak_yhat if peak_yhat > 0 else 100)))

        llm_message = generate_llm_report(
            metric_type=type,
            peak_value=peak_yhat,
            expected_time=expected_time,
            confidence=confidence_score,
            threshold=threshold
        )

        return {
            "metric": type,
            "prometheus_name": target_metric,
            "threshold": threshold,
            "peak_predicted": round(peak_yhat, 2),
            "expected_breach_time": expected_time,
            "llm_context": llm_message,
            "forecast_data": forecast_df.tail(10).to_dict(orient="records")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)