"""
복합 장애 시나리오 실행기.

기존 simulate_*.py 단일 시나리오를 조합해 시간차 또는 동시 장애를 만든다.

CLI:
  python infra/scripts/simulate_composite.py --list-profiles
  python infra/scripts/simulate_composite.py --profile upstream-collapse
  python infra/scripts/simulate_composite.py --profile app-saturation --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ScenarioStep:
    name: str
    script: str
    args: tuple[str, ...] = ()
    delay: int = 0

    def command(self) -> list[str]:
        return [sys.executable, str(SCRIPT_DIR / self.script), *self.args]


@dataclass(frozen=True)
class CompositeProfile:
    name: str
    description: str
    steps: tuple[ScenarioStep, ...]


PROFILES: dict[str, CompositeProfile] = {
    "upstream-collapse": CompositeProfile(
        name="upstream-collapse",
        description="업스트림 앱 이상이 Nginx 5xx로 번지는 상황에서 겉증상과 원인을 구분하는지 검증",
        steps=(
            ScenarioStep(
                name="zombie-process",
                script="simulate_zombie.py",
                args=("--container", "upstream_app", "--count", "8", "--duration", "50"),
            ),
            ScenarioStep(
                name="nginx-5xx",
                script="simulate_nginx_5xx.py",
                args=("--duration", "45"),
                delay=5,
            ),
        ),
    ),
    "app-saturation": CompositeProfile(
        name="app-saturation",
        description="메모리 누수와 FD 고갈이 함께 발생해 앱 컨테이너가 점진적으로 불안정해지는 상황 검증",
        steps=(
            ScenarioStep(
                name="memory-leak",
                script="simulate_memory_leak.py",
                args=("--container", "upstream_app", "--target-mb", "150", "--hold", "25"),
            ),
            ScenarioStep(
                name="fd-exhaustion",
                script="simulate_fd_exhaustion.py",
                args=("--container", "upstream_app", "--duration", "45"),
                delay=8,
            ),
        ),
    ),
    "db-cascade": CompositeProfile(
        name="db-cascade",
        description="DB 커넥션 풀 압박 이후 데드락을 이어서 발생시켜 DB 계층 연쇄 장애를 검증",
        steps=(
            ScenarioStep(
                name="connection-pool",
                script="simulate_connection_pool.py",
                args=("--connections", "95", "--duration", "40"),
            ),
            ScenarioStep(
                name="deadlock",
                script="simulate_deadlock.py",
                args=("--rounds", "4"),
                delay=18,
            ),
        ),
    ),
    "capacity-to-outage": CompositeProfile(
        name="capacity-to-outage",
        description="메모리 누수가 OOM과 5xx로 이어지는 용량 부족 기반 장애 전파를 검증",
        steps=(
            ScenarioStep(
                name="memory-leak",
                script="simulate_memory_leak.py",
                args=("--container", "upstream_app", "--target-mb", "150", "--hold", "30"),
            ),
            ScenarioStep(
                name="target-oom",
                script="simulate_oom.py",
                args=("--container", "target_nginx", "--limit", "64m"),
                delay=10,
            ),
            ScenarioStep(
                name="nginx-5xx",
                script="simulate_nginx_5xx.py",
                args=("--duration", "45"),
                delay=20,
            ),
        ),
    ),
    "mixed-control-plane": CompositeProfile(
        name="mixed-control-plane",
        description="DB 압박과 앱 리소스 압박이 동시에 발생할 때 복구 우선순위를 정하는지 검증",
        steps=(
            ScenarioStep(
                name="connection-pool",
                script="simulate_connection_pool.py",
                args=("--connections", "95", "--duration", "40"),
            ),
            ScenarioStep(
                name="memory-leak",
                script="simulate_memory_leak.py",
                args=("--container", "upstream_app", "--target-mb", "150", "--hold", "25"),
                delay=6,
            ),
            ScenarioStep(
                name="fd-exhaustion",
                script="simulate_fd_exhaustion.py",
                args=("--container", "upstream_app", "--duration", "35"),
                delay=14,
            ),
        ),
    ),
}


def _stream_output(name: str, pipe) -> None:
    if pipe is None:
        return
    for line in iter(pipe.readline, ""):
        print(f"[{name}] {line.rstrip()}", flush=True)
    pipe.close()


def _start_step(step: ScenarioStep) -> subprocess.Popen:
    command = step.command()
    print(f"[composite] start {step.name}: {' '.join(command)}", flush=True)
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_stream_output, args=(step.name, proc.stdout), daemon=True)
    thread.start()
    return proc


def _terminate_running(running: list[tuple[ScenarioStep, subprocess.Popen]]) -> None:
    for step, proc in running:
        if proc.poll() is not None:
            continue
        print(f"[composite] terminate {step.name}", flush=True)
        proc.terminate()

    for step, proc in running:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print(f"[composite] kill {step.name}", flush=True)
            proc.kill()
            proc.wait(timeout=5)


def run_profile(profile: CompositeProfile, dry_run: bool = False) -> int:
    print(f"[composite] profile={profile.name}")
    print(f"[composite] {profile.description}")

    if dry_run:
        for step in profile.steps:
            print(f"+{step.delay:>3}s {step.name}: {' '.join(step.command())}")
        return 0

    running: list[tuple[ScenarioStep, subprocess.Popen]] = []
    started_at = time.monotonic()

    try:
        for step in profile.steps:
            wait_seconds = step.delay - int(time.monotonic() - started_at)
            if wait_seconds > 0:
                print(f"[composite] wait {wait_seconds}s before {step.name}", flush=True)
                time.sleep(wait_seconds)
            running.append((step, _start_step(step)))

        failed = 0
        for step, proc in running:
            return_code = proc.wait()
            status = "ok" if return_code == 0 else f"failed({return_code})"
            print(f"[composite] done {step.name}: {status}", flush=True)
            if return_code != 0:
                failed += 1
    except KeyboardInterrupt:
        print("[composite] interrupted; cleaning up running steps", flush=True)
        _terminate_running(running)
        return 130
    except Exception:
        print("[composite] error; cleaning up running steps", flush=True)
        _terminate_running(running)
        raise

    if failed:
        print(f"[composite] profile finished with {failed} failed step(s)", flush=True)
        return 1

    print("[composite] profile finished successfully", flush=True)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="복합 장애 시나리오 실행기")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="upstream-collapse",
        help="실행할 복합 시나리오 프로필",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="사용 가능한 프로필 목록 출력",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실행하지 않고 스케줄과 명령만 출력",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.list_profiles:
        for profile in PROFILES.values():
            print(f"{profile.name}: {profile.description}")
        return 0
    return run_profile(PROFILES[args.profile], args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
