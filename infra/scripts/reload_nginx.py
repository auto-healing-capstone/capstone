"""
Nginx 설정 핫 리로드 - 컨테이너 재시작 없이 적용.

동작 방식:
  1. config_path 지정 시 → infra/nginx/default.conf 를 새 설정으로 교체
     (docker-compose 에서 ./infra/nginx 를 /etc/nginx/conf.d 로 볼륨 마운트)
  2. nginx -t 로 설정 문법 검증
  3. nginx -s reload 로 무중단 반영

CLI:
  python reload_nginx.py --container target_nginx
  python reload_nginx.py --container target_nginx --config /path/to/new.conf

API:
  from reload_nginx import reload_nginx
  ok, msg = reload_nginx("target_nginx", config_path="/path/to/new.conf")
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# docker-compose 볼륨 마운트 대상: ./infra/nginx → /etc/nginx/conf.d
NGINX_CONF_DIR = Path(__file__).resolve().parent.parent / "nginx"
DEFAULT_CONF = NGINX_CONF_DIR / "default.conf"


def reload_nginx(
    container: str = "target_nginx",
    config_path: str | None = None,
) -> tuple[bool, str]:
    """
    Nginx 설정을 교체(선택)하고 nginx -s reload 로 무중단 적용.

    Args:
        container:   Nginx 컨테이너 이름
        config_path: 적용할 새 nginx.conf 경로. None 이면 현재 설정으로 리로드만 수행.

    Returns:
        (True, 결과 메시지) 또는 (False, 에러 메시지)
    """
    if config_path:
        src = Path(config_path)
        if not src.exists():
            return False, f"설정 파일을 찾을 수 없습니다: {config_path}"
        NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, DEFAULT_CONF)

    def _exec(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container] + cmd,
            capture_output=True, text=True, timeout=15,
        )

    # 1) 문법 검증
    test = _exec(["nginx", "-t"])
    if test.returncode != 0:
        return False, f"nginx -t 실패 (설정 오류):\n{test.stderr.strip()}"

    # 2) 무중단 리로드
    reload_result = _exec(["nginx", "-s", "reload"])
    if reload_result.returncode != 0:
        return False, f"nginx -s reload 실패:\n{reload_result.stderr.strip()}"

    suffix = f" (설정 교체: {config_path})" if config_path else ""
    return True, f"Nginx 설정 리로드 완료 (container={container}){suffix}"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nginx 무중단 설정 리로드")
    p.add_argument("--container", default="target_nginx", help="Nginx 컨테이너 이름")
    p.add_argument("--config", dest="config_path",
                   help="적용할 nginx.conf 경로 (없으면 현재 설정으로 리로드만)")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    ok, msg = reload_nginx(args.container, args.config_path)
    print(msg)
    sys.exit(0 if ok else 1)
