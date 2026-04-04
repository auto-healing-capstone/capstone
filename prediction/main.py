from fastapi import FastAPI
import uvicorn
from collector import get_prometheus_data
from preprocess import transform_to_prophet_df
from model import forecast_resource_usage

app = FastAPI()

METRIC_LIST = {
    "cpu": "dummy_cpu_usage",
    "memory": "dummy_memory_usage",
    "requests": "dummy_request_count"
}

@app.get("/")
def read_root():
    return {"message": "AIOps 예측 서버가 살아있습니다!"}

@app.get("/predict/forecast/{type}")
async def get_forecast(type: str):
    if type not in METRIC_LIST:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 타입입니다. 목록: {list(METRIC_LIST.keys())}")

    target_metric = METRIC_LIST[type]

    try:
        raw = get_prometheus_data(metric_name=target_metric, hours=24)
        
        if not raw:
            return {"message": "데이터가 아직 쌓이지 않았습니다.", "data": []}

        clean_df = transform_to_prophet_df(raw)
        
        forecast_df = forecast_resource_usage(clean_df, periods=60)
        
        return {
            "metric": type,
            "full_name": target_metric,
            "forecast": forecast_df.to_dict(orient='records')
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/predict/prepare")
async def prepare_data():
    raw = get_prometheus_data(metric_name="dummy_cpu_usage", hours=24)
    
    clean_df = transform_to_prophet_df(raw)
    
    return clean_df.to_dict(orient='records')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)