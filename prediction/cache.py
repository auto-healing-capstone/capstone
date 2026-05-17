"""예측 결과 in-memory TTL 캐시.

스케줄러 주기(5분)에 맞춰 동일 메트릭의 중복 연산을 방지한다.
Calibration 실행 / Incident 생성 시 해당 메트릭 캐시를 즉시 무효화한다.
"""

import threading
import time
from typing import Optional

_store: dict[str, tuple[dict, float]] = {}
_lock = threading.Lock()

DEFAULT_TTL = 300  # 5분 — 스케줄러 주기와 동일


def get(key: str) -> Optional[dict]:
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del _store[key]
            return None
        return value


def set(key: str, value: dict, ttl: int = DEFAULT_TTL) -> None:
    with _lock:
        _store[key] = (value, time.monotonic() + ttl)


def invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def stats() -> dict:
    """진단용: 각 캐시 키의 잔여 TTL 반환."""
    with _lock:
        now = time.monotonic()
        return {
            k: {"ttl_remaining_sec": round(exp - now, 1)}
            for k, (_, exp) in _store.items()
            if exp > now
        }
