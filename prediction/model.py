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

def get_cpu_report(peak, time_msg, conf_msg, is_risky, threshold):
    if not is_risky:
        return f"✅ [CPU 안정] 현재 사용량 {peak:.1f}%로 임계치({threshold}%) 미만입니다. 성능 저하 우려가 없습니다."
    return (
        f"⚠️ [CPU 과부하 예보] {time_msg} 사용량이 {peak:.1f}%까지 치솟을 것으로 보입니다(임계치 {threshold}%). "
        f"신뢰도: {conf_msg}. 프로세스 스케줄링 지연이 예상되므로 CPU 쿼터 조정을 검토하십시오."
    )

def get_memory_report(peak, time_msg, conf_msg, is_risky, threshold):
    unit = "MB" if threshold > 100 else "%"
    
    if not is_risky:
        return (
            f"✅ [메모리 안정] 예상 피크 사용량이 {peak:.1f}{unit}로, "
            f"여유 공간이 충분합니다. 현재로서는 메모리 부족 위험이 없습니다."
        )
    return (
        f"🚨 [메모리 고갈 경보] {time_msg} 사용량이 {peak:.1f}{unit}까지 상승하여 "
        f"임계치({threshold}{unit})를 초과할 전망입니다. 신뢰도는 '{conf_msg}'입니다. "
        f"컨테이너 다운을 막기 위해 'update_resources' 액션 실행을 권장합니다."
    )

def get_request_report(peak, time_msg, conf_msg, is_risky, threshold):
    if not is_risky:
        return (
            f"✅ [트래픽 안정] 예상 요청량 {peak:.1f}건으로 임계치({threshold}) 이내입니다. "
            f"현재 서비스는 매우 안정적인 상태를 유지하고 있습니다."
        )
    return (
        f"⚡ [트래픽 폭주 감지] {time_msg} 요청량이 {peak:.1f}건까지 치솟으며 "
        f"설정된 한계치({threshold})를 크게 상회할 것으로 예측됩니다. "
        f"(모델 신뢰도: {conf_msg})"
    )

def get_fd_report(peak, time_msg, conf_msg, is_risky, threshold):
    if not is_risky:
        return f"✅ [FD 상태 안정] 파일 디스크립터 사용률 {peak:.2f}로 정상입니다."
    return (
        f"🚨 [FD 고갈 위기] {time_msg} FD 사용률이 {peak:.2f}에 도달하여 임계치({threshold})를 초과합니다. "
        f"I/O 중단 방지를 위해 'restart_container' 액션이 시급합니다."
    )

def generate_llm_report(metric_type, peak_value, expected_time, confidence, threshold):
    """
    [4주차 핵심] 메트릭 타입에 따라 LLM용 맞춤형 컨텍스트를 생성합니다.
    """
    is_risky = peak_value >= threshold
    time_msg = f"{expected_time}경" if expected_time else "조만간"
    conf_msg = "매우 확실" if confidence >= 0.9 else "높음" if confidence >= 0.7 else "주의 필요"

    if "cpu" in metric_type:
        return get_cpu_report(peak_value, time_msg, conf_msg, is_risky, threshold)
    elif "memory" in metric_type or "leak" in metric_type:
        return get_memory_report(peak_value, time_msg, conf_msg, is_risky, threshold)
    elif "request" in metric_type or "count" in metric_type:
        return get_request_report(peak_value, time_msg, conf_msg, is_risky, threshold)
    elif "fd" in metric_type:
        return get_fd_report(peak_value, time_msg, conf_msg, is_risky, threshold)
    else:
        status = "⚠️ 위험" if is_risky else "✅ 정상"
        return f"{status} [{metric_type.upper()}] 예상치 {peak_value:.1f} (임계치: {threshold})."