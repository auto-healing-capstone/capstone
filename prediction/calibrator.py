"""복구 후 안정화 관찰 및 Prophet 보정 모듈."""

import logging
import threading
from datetime import datetime, timedelta

from collector import get_prometheus_data, COLLECTION_HOURS
from preprocess import transform_to_prophet_df, validate_dataframe
from model import forecast_metric, PROPHET_CONFIG

logger = logging.getLogger(__name__)

# 안정화 판단 기준
STABILIZATION_WINDOW_MIN = 15  # 복구 후 관찰 시간 (분)
STABILIZATION_RATIO = 0.70  # 복구 후 평균이 threshold의 70% 이하여야 안정
STABILIZATION_STD_RATIO = 0.10  # 복구 후 표준편차가 threshold의 10% 이하여야 안정

# 최근 보정 결과를 in-memory 캐시 (재시작 시 초기화되는 것 허용)
_calibration_results: dict[str, dict] = {}
_calibration_lock = threading.Lock()


def _collect_post_recovery(metric_name: str, recovered_at: datetime) -> list:
    """복구 시각 이후 데이터만 수집. Prometheus query_range를 직접 호출."""
    import requests
    from collector import PROMETHEUS_URL

    start = recovered_at
    end = recovered_at + timedelta(minutes=STABILIZATION_WINDOW_MIN)

    params = {
        "query": metric_name,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": "1m",
    }
    try:
        resp = requests.get(PROMETHEUS_URL, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("data", {}).get("result", [])
        return results[0].get("values", []) if results else []
    except Exception as e:
        logger.warning("[Calibrator] post-recovery 데이터 수집 실패: %s", e)
        return []


def _is_stabilized(post_df, threshold: float) -> bool:
    """안정화 판단: 평균 < threshold * 70% AND std < threshold * 10%."""
    if post_df.empty or len(post_df) < 3:
        return False
    mean_val = post_df["y"].mean()
    std_val = post_df["y"].std()
    return (
        mean_val < threshold * STABILIZATION_RATIO
        and std_val < threshold * STABILIZATION_STD_RATIO
    )


def _do_calibration(
    metric_type: str, metric_name: str, threshold: float, recovered_at: datetime
) -> None:
    """
    복구 후 STABILIZATION_WINDOW_MIN 대기 → 메트릭 수집 → 안정화 판단 → 결과 저장.
    별도 스레드에서 실행됨.
    """
    logger.info(
        "[Calibrator] %s 보정 시작 (복구시각=%s, %d분 대기)",
        metric_type,
        recovered_at.isoformat(),
        STABILIZATION_WINDOW_MIN,
    )

    import time

    time.sleep(STABILIZATION_WINDOW_MIN * 60)

    raw = _collect_post_recovery(metric_name, recovered_at)
    if not raw:
        logger.warning(
            "[Calibrator] %s post-recovery 데이터 없음, 보정 건너뜀", metric_type
        )
        _store_result(metric_type, stabilized=False, reason="데이터 없음")
        return

    post_df = transform_to_prophet_df(raw)
    stabilized = _is_stabilized(post_df, threshold)

    if stabilized:
        logger.info("[Calibrator] %s 안정화 확인됨. 재학습 시작.", metric_type)
        _retrain_with_changepoint(metric_type, metric_name, recovered_at)
        _store_result(metric_type, stabilized=True, reason="안정화 확인 후 재학습 완료")
    else:
        mean_val = round(float(post_df["y"].mean()), 3) if not post_df.empty else None
        logger.warning(
            "[Calibrator] %s 아직 불안정 (mean=%.3f, threshold=%.1f)",
            metric_type,
            mean_val or 0,
            threshold,
        )
        _store_result(
            metric_type,
            stabilized=False,
            reason=f"불안정 (복구 후 평균={mean_val}, 임계치={threshold})",
        )


def _retrain_with_changepoint(
    metric_type: str, metric_name: str, recovered_at: datetime
) -> None:
    """changepoint를 복구 시각으로 지정하고 전체 데이터로 Prophet 재학습."""
    hours = COLLECTION_HOURS.get(metric_type, 24)
    raw = get_prometheus_data(metric_name, hours=hours)
    if not raw:
        logger.warning("[Calibrator] 재학습용 데이터 없음: %s", metric_type)
        return

    df = transform_to_prophet_df(raw)
    if not validate_dataframe(df):
        logger.warning("[Calibrator] 재학습 데이터 부족: %s", metric_type)
        return

    # recovered_at 시각을 changepoint 힌트로 전달
    forecast_df = forecast_metric(df, metric_type, extra_changepoints=[recovered_at])
    logger.info(
        "[Calibrator] %s 재학습 완료 (changepoint=%s)",
        metric_type,
        recovered_at.isoformat(),
    )
    logger.info(
        "[Calibrator] %s 캘리브레이션 완료 (forecast_points=%d)",
        metric_type,
        len(forecast_df),
    )


def _store_result(metric_type: str, stabilized: bool, reason: str) -> None:
    with _calibration_lock:
        _calibration_results[metric_type] = {
            "stabilized": stabilized,
            "reason": reason,
            "calibrated_at": datetime.utcnow().isoformat(),
        }


# ── 공개 API ───────────────────────────────────────────────────────────────

METRIC_NAME_MAP: dict[str, str] = {
    "memory_leak": "infra_memory_leak_mb",
    "fd_ratio": "infra_fd_usage_ratio",
}

THRESHOLD_MAP: dict[str, float] = {
    "memory_leak": 100.0,
    "fd_ratio": 0.8,
}


def schedule_calibration(metric_type: str, recovered_at: datetime) -> bool:
    """
    복구 완료 직후 백엔드에서 호출.
    STABILIZATION_WINDOW_MIN 후 자동으로 안정화 판단 + 재학습.
    반환값: True=스케줄됨, False=지원하지 않는 메트릭
    """
    metric_name = METRIC_NAME_MAP.get(metric_type)
    threshold = THRESHOLD_MAP.get(metric_type)
    if not metric_name or threshold is None:
        logger.warning("[Calibrator] 지원하지 않는 메트릭: %s", metric_type)
        return False

    t = threading.Thread(
        target=_do_calibration,
        args=(metric_type, metric_name, threshold, recovered_at),
        daemon=True,
        name=f"calibrator-{metric_type}",
    )
    t.start()
    return True


def get_calibration_status() -> dict[str, dict]:
    """최근 보정 결과 조회 (진단용)."""
    with _calibration_lock:
        return dict(_calibration_results)
