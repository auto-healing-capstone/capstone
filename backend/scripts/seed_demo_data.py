"""Demo data seed script.

Run from backend/ directory:
    python scripts/seed_demo_data.py
"""

import sys
import os
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.schema import (
    Incident,
    RecoveryAction,
    IncidentTypeEnum,
    StatusEnum,
    SeverityEnum,
    ActionTypeEnum,
    ApprovalStatusEnum,
)
from app.models.alert_event import AlertEvent

random.seed(42)

# ── 상수 ──────────────────────────────────────────────────────────────────────

START = datetime(2026, 3, 1, tzinfo=timezone.utc)
END = datetime(2026, 3, 29, tzinfo=timezone.utc)

STATUS_POOL = (
    [StatusEnum.RESOLVED] * 30
    + [StatusEnum.FAILED] * 8
    + [StatusEnum.PENDING] * 7
    + [StatusEnum.RECOVERING] * 3
    + [StatusEnum.DETECTED] * 2
)

SEVERITY_POOL = (
    [SeverityEnum.CRITICAL] * 20
    + [SeverityEnum.HIGH] * 15
    + [SeverityEnum.MEDIUM] * 10
    + [SeverityEnum.LOW] * 5
)

TYPE_POOL = [
    IncidentTypeEnum.HIGH_CPU,
    IncidentTypeEnum.NGINX_5XX,
    IncidentTypeEnum.OOM,
    IncidentTypeEnum.DISK_FULL,
    IncidentTypeEnum.DB_CONNECTION,
]

AI_TITLES = {
    IncidentTypeEnum.HIGH_CPU: "CPU 사용률 임계값 초과",
    IncidentTypeEnum.NGINX_5XX: "Nginx 5xx 에러 급증",
    IncidentTypeEnum.OOM: "컨테이너 OOM 발생",
    IncidentTypeEnum.DISK_FULL: "디스크 용량 부족",
    IncidentTypeEnum.DB_CONNECTION: "DB 커넥션 풀 고갈",
}

LLM_ANALYSES = {
    IncidentTypeEnum.HIGH_CPU: {
        "analysis": (
            "관측된 증상: CPU 사용률이 95% 이상으로 지속적으로 상승하며 서비스 응답 지연 발생\n"
            "추정 원인: 애플리케이션 무한 루프 또는 급격한 트래픽 증가로 인한 CPU 포화\n"
            "위험 평가: 서비스 전체 다운 가능성 높음, 즉각 조치 필요"
        )
    },
    IncidentTypeEnum.NGINX_5XX: {
        "analysis": (
            "관측된 증상: Nginx 5xx 오류 비율이 분당 500건 이상으로 급증\n"
            "추정 원인: 업스트림 서버 과부하 또는 Nginx 워커 프로세스 비정상 종료\n"
            "위험 평가: 사용자 요청 실패율 80% 초과, 서비스 가용성 심각하게 저하됨"
        )
    },
    IncidentTypeEnum.OOM: {
        "analysis": (
            "관측된 증상: 컨테이너 메모리 사용량이 제한값에 도달하여 OOM Killer 동작\n"
            "추정 원인: 메모리 누수 또는 예상치 못한 대용량 데이터 처리\n"
            "위험 평가: 컨테이너 재시작 반복 시 서비스 불안정 지속 가능"
        )
    },
    IncidentTypeEnum.DISK_FULL: {
        "analysis": (
            "관측된 증상: 루트 파티션 디스크 사용률 98% 초과, 로그 쓰기 실패\n"
            "추정 원인: 로그 로테이션 미동작 또는 대용량 덤프 파일 누적\n"
            "위험 평가: 데이터베이스 쓰기 오류 및 서비스 전체 중단 임박"
        )
    },
    IncidentTypeEnum.DB_CONNECTION: {
        "analysis": (
            "관측된 증상: DB 커넥션 풀 최대값(100) 도달, 신규 연결 요청 거부\n"
            "추정 원인: 커넥션 누수 또는 느린 쿼리로 인한 커넥션 장기 점유\n"
            "위험 평가: API 전체 DB 의존 기능 장애, 빠른 풀 회수 필요"
        )
    },
}

ALERT_NAMES = {
    IncidentTypeEnum.HIGH_CPU: "HighCPU",
    IncidentTypeEnum.NGINX_5XX: "NginxDown",
    IncidentTypeEnum.OOM: "ContainerOOM",
    IncidentTypeEnum.DISK_FULL: "DiskFull",
    IncidentTypeEnum.DB_CONNECTION: "DBConnectionPoolExhausted",
}

ALERT_SUMMARIES = {
    IncidentTypeEnum.HIGH_CPU: "CPU usage exceeded 90% threshold on agent:9100",
    IncidentTypeEnum.NGINX_5XX: "Nginx 5xx error rate spiked above 10% on agent:9100",
    IncidentTypeEnum.OOM: "Container OOM kill detected on agent:9100",
    IncidentTypeEnum.DISK_FULL: "Disk usage above 95% on agent:9100",
    IncidentTypeEnum.DB_CONNECTION: "DB connection pool exhausted on agent:9100",
}

ACTION_TYPES = {
    IncidentTypeEnum.HIGH_CPU: ActionTypeEnum.SCALE_OUT,
    IncidentTypeEnum.NGINX_5XX: ActionTypeEnum.RESTART_PROCESS,
    IncidentTypeEnum.OOM: ActionTypeEnum.RESTART_CONTAINER,
    IncidentTypeEnum.DISK_FULL: ActionTypeEnum.CLEAR_LOGS,
    IncidentTypeEnum.DB_CONNECTION: ActionTypeEnum.RESTART_PROCESS,
}

ACTION_PARAMS = {
    ActionTypeEnum.SCALE_OUT: {"cpu_quota": 100000},
    ActionTypeEnum.RESTART_PROCESS: {"process": "nginx"},
    ActionTypeEnum.RESTART_CONTAINER: {},
    ActionTypeEnum.CLEAR_LOGS: {},
    ActionTypeEnum.DOCKER_PRUNE: {},
}


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _rand_dt(start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, delta))


def _minutes(dt: datetime, lo: int, hi: int) -> datetime:
    return dt + timedelta(minutes=random.randint(lo, hi))


# ── 시드 로직 ─────────────────────────────────────────────────────────────────


def seed():
    random.shuffle(STATUS_POOL)
    random.shuffle(SEVERITY_POOL)

    db = SessionLocal()
    try:
        incidents = []
        alert_events = []
        recovery_actions = []

        for i in range(50):
            status = STATUS_POOL[i]
            severity = SEVERITY_POOL[i]
            inc_type = TYPE_POOL[i % len(TYPE_POOL)]
            detected_at = _rand_dt(START, END)
            resolved_at = (
                _minutes(detected_at, 5, 30) if status == StatusEnum.RESOLVED else None
            )

            trigger_alert = {
                "alert_name": ALERT_NAMES[inc_type],
                "severity": severity.value.lower(),
                "status": "firing",
                "instance": "agent:9100",
                "summary": ALERT_SUMMARIES[inc_type],
                "description": None,
                "fingerprint": None,
                "starts_at": detected_at.isoformat(),
                "ends_at": None,
            }

            incident = Incident(
                incident_types=[inc_type],
                trigger_metrics={"alerts": [trigger_alert]},
                target_node="agent:9100",
                detected_at=detected_at,
                status=status,
                ai_title=AI_TITLES[inc_type],
                ai_severity=severity,
                llm_analysis=LLM_ANALYSES[inc_type],
                resolved_at=resolved_at,
            )
            incidents.append(incident)

        db.add_all(incidents)
        db.flush()  # id 확정

        for i, incident in enumerate(incidents):
            inc_type = incident.incident_types[0]
            detected_at = incident.detected_at

            # AlertEvent
            alert_event = AlertEvent(
                alert_name=ALERT_NAMES[inc_type],
                severity=incident.ai_severity.value.lower(),
                status="firing",
                instance="agent:9100",
                summary=ALERT_SUMMARIES[inc_type],
                description=None,
                fingerprint=None,
                starts_at=detected_at,
                ends_at=None,
                incident_id=incident.id,
                created_at=detected_at,
            )
            alert_events.append(alert_event)

            # RecoveryAction
            action_type = ACTION_TYPES[inc_type]
            status = incident.status

            is_approved = status in (
                StatusEnum.RESOLVED,
                StatusEnum.FAILED,
                StatusEnum.RECOVERING,
            )
            approval_status = (
                ApprovalStatusEnum.APPROVED
                if is_approved
                else ApprovalStatusEnum.PENDING
            )
            reviewed_at = _minutes(detected_at, 2, 5) if is_approved else None
            reviewed_by = "admin" if is_approved else None

            is_executed = status in (StatusEnum.RESOLVED, StatusEnum.FAILED)
            executed_at = (
                reviewed_at + timedelta(minutes=1)
                if is_executed and reviewed_at is not None
                else None
            )
            is_successful = (
                True
                if status == StatusEnum.RESOLVED
                else (False if status == StatusEnum.FAILED else None)
            )

            if status == StatusEnum.RESOLVED:
                log_snippet = "admin 승인\nRecovery executed successfully"
            elif status == StatusEnum.FAILED:
                log_snippet = "admin 승인\nRecovery execution failed"
            else:
                log_snippet = None

            recovery_action = RecoveryAction(
                incident_id=incident.id,
                action_type=action_type,
                params=ACTION_PARAMS[action_type],
                approval_status=approval_status,
                reviewed_at=reviewed_at,
                reviewed_by=reviewed_by,
                executed_at=executed_at,
                is_successful=is_successful,
                log_snippet=log_snippet,
            )
            recovery_actions.append(recovery_action)

        db.add_all(alert_events)
        db.add_all(recovery_actions)
        db.commit()

        print(
            f"Incidents: {len(incidents)}건, "
            f"AlertEvents: {len(alert_events)}건, "
            f"RecoveryActions: {len(recovery_actions)}건 삽입 완료"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
