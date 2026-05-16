import logging

import numpy as np
import pandas as pd
from prophet import Prophet

logger = logging.getLogger(__name__)

PROPHET_CONFIG: dict[str, dict] = {
    "memory_leak": {
        "seasonality_mode": "multiplicative",
        "changepoint_prior_scale": 0.1,  # 0.3 → 0.1: 24h 단기 데이터 과적합 완화
        "seasonality_prior_scale": 5.0,
        "n_changepoints": 5,  # 기본 25개 → 5개로 축소
        # §1 경량화: 단기(0.5~24h) 데이터에서 시즈널리티 불필요 → CPU 절감
        "daily_seasonality": False,
        "weekly_seasonality": False,
        "yearly_seasonality": False,
    },
    "fd_ratio": {
        "seasonality_mode": "multiplicative",
        "changepoint_prior_scale": 0.05,  # logistic은 더 보수적으로
        "seasonality_prior_scale": 5.0,
        "n_changepoints": 3,
        "growth": "logistic",
        "cap": 1.0,
        "floor": 0.0,  # 음수 예측 방지
        # §1 경량화: 단기 데이터, 시즈널리티 비활성화
        "daily_seasonality": False,
        "weekly_seasonality": False,
        "yearly_seasonality": False,
    },
}

FORECAST_PERIODS: dict[str, int] = {
    "memory_leak": 60,
    "fd_ratio": 60,
}

_MAPE_THRESHOLD = 0.30  # MAPE 30% 초과 시 과적합으로 판단
_HOLDOUT_RATIO = 0.2  # 마지막 20%를 검증셋으로 사용


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = actual != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])))


def _build_prophet(
    config: dict,
    scale_override: float | None = None,
    extra_changepoints: list | None = None,
) -> Prophet:
    growth = config.get("growth", "linear")
    cp_scale = (
        scale_override
        if scale_override is not None
        else config.get("changepoint_prior_scale", 0.05)
    )

    kwargs: dict = dict(
        seasonality_mode=config.get("seasonality_mode", "additive"),
        changepoint_prior_scale=cp_scale,
        seasonality_prior_scale=config.get("seasonality_prior_scale", 10.0),
        interval_width=0.95,
        growth=growth,
        # §1 모델 경량화: 불필요한 시즈널리티 비활성화로 추론 속도 향상
        daily_seasonality=config.get("daily_seasonality", False),
        weekly_seasonality=config.get("weekly_seasonality", False),
        yearly_seasonality=config.get("yearly_seasonality", False),
    )
    # extra_changepoints가 있으면 n_changepoints 대신 명시적 changepoints 목록 사용
    if extra_changepoints:
        kwargs["changepoints"] = [pd.Timestamp(cp) for cp in extra_changepoints]
    else:
        kwargs["n_changepoints"] = config.get("n_changepoints", 25)

    return Prophet(**kwargs)


def _fit_predict(
    m: Prophet, df: pd.DataFrame, config: dict, periods: int
) -> pd.DataFrame:
    growth = config.get("growth", "linear")
    fit_df = df.copy()
    if growth == "logistic":
        fit_df["cap"] = config.get("cap", 1.0)
        fit_df["floor"] = config.get("floor", 0.0)

    m.fit(fit_df)

    future = m.make_future_dataframe(periods=periods, freq="min")
    if growth == "logistic":
        future["cap"] = config.get("cap", 1.0)
        future["floor"] = config.get("floor", 0.0)

    forecast = m.predict(future)
    return (
        forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        .tail(periods)
        .reset_index(drop=True)
    )


def forecast_metric(
    df: pd.DataFrame,
    metric_type: str,
    periods: int = 60,
    extra_changepoints: list | None = None,
) -> pd.DataFrame:
    config = PROPHET_CONFIG.get(metric_type, {})

    # holdout 검증으로 과적합 감지
    split = max(10, int(len(df) * (1 - _HOLDOUT_RATIO)))
    train_df, val_df = df.iloc[:split], df.iloc[split:]

    if len(val_df) >= 5:
        m_val = _build_prophet(config)  # holdout 검증은 extra_changepoints 없이
        val_forecast = _fit_predict(m_val, train_df, config, len(val_df))
        mape = _mape(val_df["y"].values, val_forecast["yhat"].values)

        if mape > _MAPE_THRESHOLD:
            reduced_scale = config.get("changepoint_prior_scale", 0.05) / 2
            logger.warning(
                "metric=%s MAPE=%.2f > %.2f, retrying with cp_scale=%.4f",
                metric_type,
                mape,
                _MAPE_THRESHOLD,
                reduced_scale,
            )
            m_final = _build_prophet(
                config,
                scale_override=reduced_scale,
                extra_changepoints=extra_changepoints,
            )
        else:
            logger.info("metric=%s MAPE=%.2f OK", metric_type, mape)
            m_final = _build_prophet(config, extra_changepoints=extra_changepoints)
    else:
        m_final = _build_prophet(config, extra_changepoints=extra_changepoints)

    return _fit_predict(m_final, df, config, periods)


# ── 이하 기존 함수 유지 (cpu/memory 메트릭 레거시 경로용) ──────────────────


def forecast_resource_usage(df, periods=60, events=None):
    cp_scale = 0.05
    cp_list = None

    if events is not None and not events.empty:
        cp_list = events["ds"].tolist()
        cp_scale = 0.5

    m = Prophet(
        interval_width=0.95,
        holidays=events,
        changepoints=cp_list,
        changepoint_prior_scale=cp_scale,
    )

    m.fit(df)
    future = m.make_future_dataframe(periods=periods, freq="min")
    forecast = m.predict(future)

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods)


def generate_llm_report(
    metric_type,
    peak_value,
    expected_time,
    confidence,
    threshold,
    is_recovered=False,
    impact=None,
):
    is_risky = peak_value >= threshold
    time_msg = f"{expected_time}경" if expected_time else "조만간"
    conf_msg = (
        "매우 확실"
        if confidence >= 0.9
        else "높음" if confidence >= 0.7 else "주의 필요"
    )

    if is_recovered and impact:
        return _get_stabilization_report(metric_type, impact, is_risky, threshold)

    if "cpu" in metric_type:
        return _get_cpu_report(
            peak_value, time_msg, conf_msg, is_risky, threshold, is_recovered
        )

    status = (
        "✨ 복구후 안정"
        if is_recovered and not is_risky
        else "⚠️ 위험" if is_risky else "✅ 정상"
    )
    return f"{status} [{metric_type.upper()}] 예상치 {peak_value:.1f} (임계치: {threshold})."


def _get_cpu_report(peak, time_msg, conf_msg, is_risky, threshold, is_recovered=False):
    if is_recovered and not is_risky:
        return f"✨ [복구 성공] 복구 액션 실행 후 CPU 사용량이 {peak:.1f}%로 안정화되었습니다."
    if not is_risky:
        return (
            f"✅ [CPU 안정] 현재 사용량 {peak:.1f}%로 임계치({threshold}%) 미만입니다."
        )
    return (
        f"⚠️ [CPU 과부하 예보] {time_msg} 사용량이 {peak:.1f}%까지 치솟을 것으로 보입니다(임계치 {threshold}%). "
        f"신뢰도: {conf_msg}."
    )


def _get_stabilization_report(metric, impact, is_risky, threshold):
    fact_msg = (
        f"📊 [Fact] 복구 액션 실행 전 {metric} 지표는 {impact['before']:.1f}였으나, "
        f"현재 {impact['after']:.1f}로 안정화되어 {impact['improvement_pct']}%의 개선율을 기록했습니다."
    )
    if not is_risky:
        opinion_msg = (
            f"💡 [Opinion] 임계치({threshold}) 이하로 안정적으로 유지되고 있습니다."
        )
    else:
        opinion_msg = f"💡 [Opinion] 여전히 임계치({threshold}) 근처에 머물고 있습니다. 추가 조치를 검토하세요."
    return f"{fact_msg}\n{opinion_msg}"


def calculate_recovery_impact(df, events):
    if events is None or events.empty:
        return None

    last_event_time = events["ds"].max()
    pre_heal = df[df["ds"] < last_event_time].tail(10)
    if pre_heal.empty:
        return None
    before_val = pre_heal["y"].max()

    post_heal = df[df["ds"] >= last_event_time]
    if post_heal.empty:
        return None
    after_val = post_heal["y"].mean()

    drop_delta = before_val - after_val
    imp_ratio = (drop_delta / before_val * 100) if before_val > 0 else 0

    return {
        "before": round(before_val, 2),
        "after": round(after_val, 2),
        "improvement_pct": round(imp_ratio, 1),
    }
