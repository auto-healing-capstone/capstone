from prophet import Prophet
import pandas as pd


def forecast_resource_usage(df, periods=60):
    """
    df: ds와 y 컬럼이 있는 전처리된 데이터프레임
    periods: 미래를 얼마나 예측할지 (기본 60분)
    """

    m = Prophet(interval_width=0.95)  # 95% 신뢰구간 표시

    m.fit(df)

    future = m.make_future_dataframe(periods=periods, freq="min")

    forecast = m.predict(future)

    result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods)

    return result

def generate_llm_report(metric_type, peak_value, expected_time, confidence, threshold=70.0):
    is_risky = peak_value >= threshold
    time_msg = f"{expected_time}경" if expected_time else "가까운 미래에"
    
    # 신뢰도 문구
    conf_msg = "매우 확실함" if confidence >= 0.9 else "높음" if confidence >= 0.7 else "주의 필요"

    # 1. 정상 상태일 때
    if not is_risky:
        return f"✅ [정상 상태] {metric_type.upper()} 지표가 안정적입니다. 최고 예상치 {peak_value:.1f}% 수준으로 유지될 것으로 보입니다."

    # 2. 위험 상태일 때 (메트릭별 맞춤 문구)
    if metric_type.lower() == "requests":
        # 트래픽 전용 문구
        report = (
            f"⚠️ [트래픽 급증 예보] {time_msg} 서비스 요청량이 급격히 증가할 것으로 예측됩니다. "
            f"예상 부하 수치는 {peak_value:.1f}%이며, 신뢰도는 '{conf_msg}'입니다. "
            f"서버 커넥션 풀 고갈이나 응답 지연에 대비한 스케일 아웃 검토가 필요합니다."
        )
    else:
        # CPU, Memory 등 자원 전용 문구
        report = (
            f"⚠️ [자원 고갈 경보] {metric_type.upper()} 사용량이 {time_msg} 임계치를 넘을 것으로 보입니다. "
            f"예상 피크치: {peak_value:.1f}%, 신뢰도: '{conf_msg}'. "
            f"시스템 다운타임 방지를 위해 리소스 최적화가 필요합니다."
        )
    
    return report