#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import signal
import sys
import time
from pathlib import Path


MB = 1024 * 1024
SAFE_MAX_MEMORY_MB = 512
SAFE_MAX_DISK_MB = 1024
PAGE_SIZE = 4096


class LoadTester:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.memory_blocks: list[bytearray] = []
        self.disk_file = (
            Path(args.target_dir)
            / f"resource-load-{int(time.time())}.bin"
        )
        self.status_file = Path(args.status_file)
        self.stopped = False

    def validate(self) -> None:
        if self.args.memory_mb <= 0 and self.args.disk_mb <= 0:
            raise ValueError("At least one of --memory-mb or --disk-mb must be greater than 0.")
        if self.args.duration <= 0:
            raise ValueError("--duration must be greater than 0.")
        if self.args.memory_step_mb <= 0 or self.args.disk_chunk_mb <= 0:
            raise ValueError("Step and chunk sizes must be greater than 0.")
        if not self.args.force:
            if self.args.memory_mb > SAFE_MAX_MEMORY_MB:
                raise ValueError(
                    f"--memory-mb exceeds safe limit ({SAFE_MAX_MEMORY_MB} MB). "
                    "Use --force if you intentionally want a larger load."
                )
            if self.args.disk_mb > SAFE_MAX_DISK_MB:
                raise ValueError(
                    f"--disk-mb exceeds safe limit ({SAFE_MAX_DISK_MB} MB). "
                    "Use --force if you intentionally want a larger load."
                )

    def prepare(self) -> None:
        self.disk_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        signal.signal(signal.SIGINT, self.handle_stop)
        signal.signal(signal.SIGTERM, self.handle_stop)
        self.write_status(phase="starting", elapsed=0)

    def handle_stop(self, signum, _frame) -> None:
        self.stopped = True
        print(f"[load-test] Received signal {signum}, stopping...")

    def allocate_memory(self) -> None:
        target_mb = self.args.memory_mb
        if target_mb <= 0:
            return

        allocated_mb = 0
        while allocated_mb < target_mb and not self.stopped:
            chunk_mb = min(self.args.memory_step_mb, target_mb - allocated_mb)
            block = bytearray(chunk_mb * MB)
            for index in range(0, len(block), PAGE_SIZE):
                block[index] = 1
            self.memory_blocks.append(block)
            allocated_mb += chunk_mb
            print(f"[load-test] Memory allocated: {allocated_mb}/{target_mb} MB")
            time.sleep(self.args.allocate_pause)

    def allocate_disk(self) -> None:
        target_mb = self.args.disk_mb
        if target_mb <= 0:
            return

        written_mb = 0
        chunk = b"0" * (self.args.disk_chunk_mb * MB)
        with self.disk_file.open("wb") as file_obj:
            while written_mb < target_mb and not self.stopped:
                chunk_mb = min(self.args.disk_chunk_mb, target_mb - written_mb)
                file_obj.write(chunk[: chunk_mb * MB])
                file_obj.flush()
                os.fsync(file_obj.fileno())
                written_mb += chunk_mb
                print(f"[load-test] Disk written: {written_mb}/{target_mb} MB -> {self.disk_file}")
                time.sleep(self.args.allocate_pause)

    def current_rss_mb(self) -> float:
        status_path = Path("/proc/self/status")
        if status_path.exists():
            for line in status_path.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) / 1024
        return 0.0

    def current_disk_file_mb(self) -> float:
        if not self.disk_file.exists():
            return 0.0
        return self.disk_file.stat().st_size / MB

    def write_status(self, phase: str, elapsed: int) -> None:
        payload = {
            "phase": phase,
            "memory_mb": round(self.current_rss_mb(), 1),
            "disk_mb": round(self.current_disk_file_mb(), 1),
            "elapsed_seconds": elapsed,
            "updated_at": int(time.time()),
        }
        temp_path = self.status_file.with_suffix(f"{self.status_file.suffix}.tmp")
        temp_path.write_text(json.dumps(payload), encoding="utf-8")
        temp_path.replace(self.status_file)

    def print_status(self, elapsed: int) -> None:
        disk_usage = shutil.disk_usage(self.disk_file.parent)
        self.write_status(phase="running", elapsed=elapsed)
        print(
            "[load-test] "
            f"elapsed={elapsed}s "
            f"rss={self.current_rss_mb():.1f}MB "
            f"disk_file={self.current_disk_file_mb():.1f}MB "
            f"disk_free={disk_usage.free / MB:.1f}MB"
        )

    def hold_load(self) -> None:
        start = time.time()
        next_log = 0
        while not self.stopped:
            elapsed = int(time.time() - start)
            if elapsed >= self.args.duration:
                break
            if elapsed >= next_log:
                self.print_status(elapsed)
                next_log += self.args.log_interval
            time.sleep(1)

    def cleanup(self) -> None:
        self.write_status(phase="stopping", elapsed=self.args.duration)
        self.memory_blocks.clear()
        if self.args.cleanup and self.disk_file.exists():
            self.disk_file.unlink()
            print(f"[load-test] Removed disk artifact: {self.disk_file}")
        self.write_status(phase="idle", elapsed=self.args.duration)

    def run(self) -> int:
        self.validate()
        self.prepare()

        print(
            "[load-test] Starting "
            f"(memory={self.args.memory_mb}MB, disk={self.args.disk_mb}MB, "
            f"duration={self.args.duration}s, cleanup={self.args.cleanup})"
        )
        self.allocate_memory()
        self.allocate_disk()
        self.hold_load()
        self.cleanup()
        print("[load-test] Completed.")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate memory and disk pressure for infra testing."
    )
    parser.add_argument("--memory-mb", type=int, default=0, help="Amount of memory to reserve in MB.")
    parser.add_argument("--disk-mb", type=int, default=0, help="Amount of disk to occupy in MB.")
    parser.add_argument("--duration", type=int, default=60, help="How long to hold the load in seconds.")
    parser.add_argument(
        "--memory-step-mb",
        type=int,
        default=64,
        help="Memory allocation step in MB.",
    )
    parser.add_argument(
        "--disk-chunk-mb",
        type=int,
        default=64,
        help="Disk write chunk size in MB.",
    )
    parser.add_argument(
        "--allocate-pause",
        type=float,
        default=0.2,
        help="Pause between allocation steps in seconds.",
    )
    parser.add_argument(
        "--log-interval",
        type=int,
        default=5,
        help="Status log interval in seconds.",
    )
    parser.add_argument(
        "--target-dir",
        default="/tmp/auto-healing-load-test",
        help="Directory where disk load artifacts are written.",
    )
    parser.add_argument(
        "--status-file",
        default="/tmp/auto-healing-load-test/status.json",
        help="Path to the JSON status file consumed by the metrics agent.",
    )
    parser.add_argument(
        "--cleanup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove generated disk artifacts after the test.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow loads above the built-in safe limits.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return LoadTester(args).run()
    except ValueError as exc:
        print(f"[load-test] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
