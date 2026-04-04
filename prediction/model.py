from prophet import Prophet
import pandas as pd

def forecast_resource_usage(df, periods=60):
    """
    df: ds와 y 컬럼이 있는 전처리된 데이터프레임
    periods: 미래를 얼마나 예측할지 (기본 60분)
    """

    m = Prophet(interval_width=0.95) # 95% 신뢰구간 표시
    
    m.fit(df)
    
    future = m.make_future_dataframe(periods=periods, freq='min')
    
    forecast = m.predict(future)
    
    result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(periods)
    
    return result