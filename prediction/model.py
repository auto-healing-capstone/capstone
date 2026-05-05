from prophet import Prophet
import pandas as pd

def forecast_resource_usage(df, periods=60, events=None):
    cp_scale = 0.05
    cp_list = None

    if events is not None and not events.empty:
        cp_list = events['ds'].tolist()
        cp_scale = 0.5

    m = Prophet(
        interval_width=0.95,
        holidays=events,
        changepoints=cp_list,
        changepoint_prior_scale=cp_scale
    )

    m.fit(df)
    future = m.make_future_dataframe(periods=periods, freq="min")
    forecast = m.predict(future)

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods)

def get_cpu_report(peak, time_msg, conf_msg, is_risky, threshold, is_recovered=False):
    if is_recovered and not is_risky:
        return f"✨ [복구 성공] 복구 액션 실행 후 CPU 사용량이 {peak:.1f}%로 안정화되었습니다. 추가 장애 위험이 낮습니다."

    if not is_risky:
        return f"✅ [CPU 안정] 현재 사용량 {peak:.1f}%로 임계치({threshold}%) 미만입니다. 성능 저하 우려가 없습니다."

    return (
        f"⚠️ [CPU 과부하 예보] {time_msg} 사용량이 {peak:.1f}%까지 치솟을 것으로 보입니다(임계치 {threshold}%). "
        f"신뢰도: {conf_msg}. 프로세스 스케줄링 지연이 예상되므로 CPU 쿼터 조정을 검토하십시오."
    )

def get_stabilization_report(metric, impact, is_risky, threshold):
    fact_msg = (
        f"📊 [Fact] 복구 액션 실행 전 {metric} 지표는 {impact['before']:.1f}였으나, "
        f"현재 {impact['after']:.1f}로 안정화되어 {impact['improvement_pct']}%의 개선율을 기록했습니다."
    )

    if not is_risky:
        opinion_msg = (
            f"💡 [Opinion] 현재 지표가 임계치({threshold}) 이하로 안정적으로 유지되고 있습니다. "
            "복구 조치가 유효하며 조만간 추가 장애가 발생할 가능성은 낮습니다."
        )
    else:
        opinion_msg = (
            f"💡 [Opinion] 복구 액션에도 불구하고 지표가 여전히 임계치({threshold}) 근처에 머물고 있습니다. "
            "자원 증설(update_container) 등 추가적인 후속 조치를 검토할 필요가 있습니다."
        )

    return f"{fact_msg}\n{opinion_msg}"

def generate_llm_report(metric_type, peak_value, expected_time, confidence, threshold, is_recovered=False, impact=None):
    is_risky = peak_value >= threshold
    time_msg = f"{expected_time}경" if expected_time else "조만간"
    conf_msg = "매우 확실" if confidence >= 0.9 else "높음" if confidence >= 0.7 else "주의 필요"

    if is_recovered and impact:
        return get_stabilization_report(metric_type, impact, is_risky, threshold)

    if "cpu" in metric_type:
        return get_cpu_report(peak_value, time_msg, conf_msg, is_risky, threshold, is_recovered)

    status = "✨ 복구후 안정" if is_recovered and not is_risky else "⚠️ 위험" if is_risky else "✅ 정상"
    return f"{status} [{metric_type.upper()}] 예상치 {peak_value:.1f} (임계치: {threshold})."

def calculate_recovery_impact(df, events):
    if events is None or events.empty:
        return None

    last_event_time = events['ds'].max()

    pre_heal = df[df['ds'] < last_event_time].tail(10)
    if pre_heal.empty:
        return None
    before_val = pre_heal['y'].max()

    post_heal = df[df['ds'] >= last_event_time]
    if post_heal.empty:
        return None
    after_val = post_heal['y'].mean()

    drop_delta = before_val - after_val
    imp_ratio = (drop_delta / before_val * 100) if before_val > 0 else 0

    return {
        "before": round(before_val, 2),
        "after": round(after_val, 2),
        "improvement_pct": round(imp_ratio, 1)
    }
