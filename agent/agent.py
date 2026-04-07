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

LOAD_TEST_STATUS_FILE = os.getenv("LOAD_TEST_STATUS_FILE", "/tmp/auto-healing-load-test/status.json")


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


def update_metrics():
    while True:
        forced_cpu = os.getenv("FORCE_CPU_USAGE")
        forced_memory = os.getenv("FORCE_MEMORY_USAGE")

        cpu_usage.set(int(forced_cpu) if forced_cpu is not None and forced_cpu != "" else random.randint(10, 90))
        memory_usage.set(int(forced_memory) if forced_memory is not None and forced_memory != "" else random.randint(20, 80))
        request_count.set(random.randint(100, 500))
        update_load_test_metrics()
        print("metrics updated")
        time.sleep(2)


if __name__ == "__main__":
    start_http_server(9100)
    print("Serving metrics at http://localhost:9100/metrics")
    update_metrics()
