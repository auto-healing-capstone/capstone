import json
import os
from prometheus_client import start_http_server, Gauge
import random
import time

cpu_usage = Gauge("dummy_cpu_usage", "Dummy CPU Usage")
memory_usage = Gauge("dummy_memory_usage", "Dummy Memory Usage")
request_count = Gauge("dummy_request_count", "Dummy Request Count")
load_test_memory_mb = Gauge("infra_load_test_memory_mb", "Infra load test memory usage in MB")
load_test_disk_mb = Gauge("infra_load_test_disk_mb", "Infra load test disk usage in MB")

# 장애 시나리오 메트릭
nginx_5xx_total = Gauge("infra_nginx_5xx_total", "Nginx 5xx error count during simulation")
db_active_connections = Gauge("infra_db_active_connections", "Active DB connections during simulation")
db_max_connections = Gauge("infra_db_max_connections", "DB max_connections setting")
container_oom_killed = Gauge("infra_container_oom_killed", "Number of OOM-killed containers")
db_deadlock_count    = Gauge("infra_db_deadlock_count",    "DB deadlock count during simulation")
zombie_process_count = Gauge("infra_zombie_process_count", "Zombie process count in container")
fd_usage_ratio       = Gauge("infra_fd_usage_ratio",       "File descriptor usage ratio (0-1)")
memory_leak_mb       = Gauge("infra_memory_leak_mb",       "Simulated memory leak size in MB")

LOAD_TEST_STATUS_FILE = os.getenv("LOAD_TEST_STATUS_FILE", "/tmp/auto-healing-load-test/status.json")
SCENARIO_STATUS_FILE = os.getenv("SCENARIO_STATUS_FILE", "/tmp/auto-healing-scenarios/status.json")
AGENT_LOG_LEVEL = os.getenv("AGENT_LOG_LEVEL", "warning").lower()
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _log_debug(message: str) -> None:
    if AGENT_LOG_LEVEL == "debug":
        print(message)


def update_load_test_metrics() -> None:
    if not os.path.exists(LOAD_TEST_STATUS_FILE):
        load_test_memory_mb.set(0)
        load_test_disk_mb.set(0)
        return

    try:
        with open(LOAD_TEST_STATUS_FILE, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
        load_test_memory_mb.set(float(payload.get("memory_mb", 0)))
        load_test_disk_mb.set(float(payload.get("disk_mb", 0)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        load_test_memory_mb.set(0)
        load_test_disk_mb.set(0)


def update_scenario_metrics() -> None:
    if not os.path.exists(SCENARIO_STATUS_FILE):
        return
    try:
        with open(SCENARIO_STATUS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        nginx_5xx_total.set(float(payload.get("nginx_5xx_total", 0)))
        db_active_connections.set(float(payload.get("db_active_connections", 0)))
        db_max_connections.set(float(payload.get("db_max_connections", 0)))
        container_oom_killed.set(float(payload.get("container_oom_killed", 0)))
        db_deadlock_count.set(float(payload.get("db_deadlock_count", 0)))
        zombie_process_count.set(float(payload.get("zombie_process_count", 0)))
        fd_usage_ratio.set(float(payload.get("fd_usage_ratio", 0)))
        memory_leak_mb.set(float(payload.get("memory_leak_mb", 0)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def update_metrics():
    while True:
        default_cpu = 35 if DEMO_MODE else random.randint(10, 90)
        default_memory = 45 if DEMO_MODE else random.randint(20, 80)
        default_requests = 180 if DEMO_MODE else random.randint(100, 500)

        cpu_usage.set(_env_int("FORCE_CPU_USAGE", default_cpu))
        memory_usage.set(_env_int("FORCE_MEMORY_USAGE", default_memory))
        request_count.set(_env_int("FORCE_REQUEST_COUNT", default_requests))
        update_load_test_metrics()
        update_scenario_metrics()
        _log_debug("metrics updated")
        time.sleep(_env_float("AGENT_UPDATE_INTERVAL", 5.0, minimum=1.0))


if __name__ == "__main__":
    start_http_server(9100)
    print("Serving metrics at http://localhost:9100/metrics")
    update_metrics()
