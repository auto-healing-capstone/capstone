from prometheus_client import start_http_server, Gauge
import random
import time

cpu_usage = Gauge('dummy_cpu_usage', 'Dummy CPU Usage')
memory_usage = Gauge('dummy_memory_usage', 'Dummy Memory Usage')
request_count = Gauge('dummy_request_count', 'Dummy Request Count')

def update_metrics():
    while True:
        cpu_usage.set(random.randint(10, 90))
        memory_usage.set(random.randint(20, 80))
        request_count.set(random.randint(100, 500))
        print("metrics updated")
        time.sleep(2)

if __name__ == "__main__":
    start_http_server(9100)
    print("Serving metrics at http://localhost:9100/metrics")
    update_metrics()