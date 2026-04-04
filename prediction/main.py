from fastapi import FastAPI
import uvicorn
from collector import get_prometheus_data
from preprocess import transform_to_prophet_df

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "AIOps 예측 서버가 살아있습니다!"}

@app.get("/predict/prepare")
async def prepare_data():
    raw = get_prometheus_data(metric_name="dummy_cpu_usage", hours=24)
    
    clean_df = transform_to_prophet_df(raw)
    
    return clean_df.to_dict(orient='records')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)