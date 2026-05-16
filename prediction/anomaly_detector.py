from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class AnomalyLevel(str, Enum):
    CLEAR = "CLEAR"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


DETECTOR_CONFIG: dict[str, dict] = {
    "memory_leak": {
        "signal_weights": {"residual": 0.4, "breach": 0.5, "trend": 0.1},
        "min_breach_duration": 3,
        "score_thresholds": {"WATCH": 0.2, "WARNING": 0.4, "CRITICAL": 0.7},
        "recommended_action": "restart_container",
    },
    "fd_ratio": {
        "signal_weights": {"residual": 0.3, "breach": 0.5, "trend": 0.2},
        "min_breach_duration": 3,
        "score_thresholds": {"WATCH": 0.2, "WARNING": 0.4, "CRITICAL": 0.7},
        "recommended_action": "restart_container",
    },
}

_DEFAULT_CONFIG: dict = {
    "signal_weights": {"residual": 0.33, "breach": 0.34, "trend": 0.33},
    "min_breach_duration": 3,
    "score_thresholds": {"WATCH": 0.2, "WARNING": 0.4, "CRITICAL": 0.7},
    "recommended_action": None,
}


# ── Signal A: 임계 초과 잔차 ────────────────────────────────────────────────


def _residual_score(df: pd.DataFrame, threshold: float) -> float:
    above = df[df["yhat"] > threshold]
    if above.empty:
        return 0.0
    excess = (above["yhat"] - threshold) / (threshold if threshold > 0 else 1.0)
    return float(min(1.0, excess.mean()))


# ── Signal B: 연속 임계 초과 구간 ──────────────────────────────────────────


def _breach_score(df: pd.DataFrame, threshold: float, min_duration: int) -> float:
    flags = (df["yhat"] >= threshold).astype(int).tolist()
    max_run = cur = 0
    for v in flags:
        cur = cur + 1 if v else 0
        max_run = max(max_run, cur)
    if max_run < min_duration:
        return 0.0
    return float(min(1.0, max_run / (min_duration * 3)))


# ── Signal C: 상승 추세 속도 ───────────────────────────────────────────────


def _trend_score(df: pd.DataFrame, threshold: float) -> float:
    if len(df) < 2:
        return 0.0
    y = df["yhat"].values
    slope = float(np.polyfit(np.arange(len(y)), y, 1)[0])
    normalized = slope / threshold if threshold > 0 else slope
    return float(min(1.0, max(0.0, normalized * 10)))


# ── 공개 API ───────────────────────────────────────────────────────────────


def detect_anomaly(
    forecast_df: pd.DataFrame,
    metric_type: str,
    threshold: float,
) -> dict:
    cfg = DETECTOR_CONFIG.get(metric_type, _DEFAULT_CONFIG)
    weights = cfg["signal_weights"]
    min_dur = cfg.get("min_breach_duration", 3)
    thresholds = cfg.get("score_thresholds", _DEFAULT_CONFIG["score_thresholds"])

    r = _residual_score(forecast_df, threshold)
    b = _breach_score(forecast_df, threshold, min_dur)
    t = _trend_score(forecast_df, threshold)

    composite = weights["residual"] * r + weights["breach"] * b + weights["trend"] * t

    if composite >= thresholds["CRITICAL"]:
        level = AnomalyLevel.CRITICAL
    elif composite >= thresholds["WARNING"]:
        level = AnomalyLevel.WARNING
    elif composite >= thresholds["WATCH"]:
        level = AnomalyLevel.WATCH
    else:
        level = AnomalyLevel.CLEAR

    # 임계 돌파 예상 시각 + 지속 시간 (WARNING 이상일 때만)
    breach_time: Optional[str] = None
    breach_duration_min: Optional[int] = None
    if level in (AnomalyLevel.WARNING, AnomalyLevel.CRITICAL):
        breach_rows = forecast_df[forecast_df["yhat"] >= threshold]
        if not breach_rows.empty:
            breach_time = pd.to_datetime(breach_rows["ds"].iloc[0]).strftime("%H:%M")
            breach_duration_min = len(breach_rows)

    # 이유 문자열
    signals = []
    if r > 0.3:
        signals.append(f"잔차 과대({r:.2f})")
    if b > 0.3:
        signals.append(f"임계 초과 지속({b:.2f})")
    if t > 0.3:
        signals.append(f"상승 추세({t:.2f})")
    reason = ", ".join(signals) if signals else "정상 범위"

    return {
        "anomaly_level": level.value,
        "anomaly_score": round(composite, 4),
        "reason": reason,
        "breach_time": breach_time,
        "breach_duration_min": breach_duration_min,
        "recommended_action": cfg.get("recommended_action"),
        "peak_predicted": round(float(forecast_df["yhat"].max()), 4),
        "signals": {
            "residual": round(r, 4),
            "breach": round(b, 4),
            "trend": round(t, 4),
        },
    }
