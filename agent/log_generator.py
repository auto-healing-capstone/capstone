import time
import random

messages = [
    "Service running normally",
    "Health check passed",
    "Temporary response delay detected",
    "Database connection timeout",
    "Internal server error occurred"
]

levels = ["INFO", "INFO", "INFO", "WARNING", "ERROR"]

while True:
    idx = random.randint(0, len(messages) - 1)
    log_line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{levels[idx]}] {messages[idx]}"

    with open("app.log", "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

    print(log_line)
    time.sleep(2)