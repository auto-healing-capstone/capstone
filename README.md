프론트: https://github.com/auto-healing-capstone/auto-healing-FE

## Infra Load Test

디스크/메모리 자원 변화를 안전하게 시뮬레이션하려면 아래 스크립트를 사용합니다.

```bash
python3 infra/load_test.py --memory-mb 256 --disk-mb 256 --duration 60
```

기본 동작:
- `--memory-mb`: 지정한 크기만큼 메모리 점유
- `--disk-mb`: `/tmp/auto-healing-load-test` 아래에 임시 파일 생성
- `--duration`: 지정 시간 동안 부하 유지
- `--cleanup`: 기본값 `true`, 종료 후 디스크 파일 자동 삭제

안전 장치:
- 기본 안전 한도는 메모리 `512MB`, 디스크 `1024MB`
- 더 큰 부하가 필요하면 `--force`를 명시적으로 사용

예시:

```bash
# 메모리만 테스트
python3 infra/load_test.py --memory-mb 256 --duration 45

# 디스크만 테스트
python3 infra/load_test.py --disk-mb 512 --duration 45

# cleanup 없이 파일 유지
python3 infra/load_test.py --disk-mb 256 --duration 30 --no-cleanup
```

Docker 환경에서 `agent` 컨테이너 내부 기준으로 검증하려면:

```bash
docker compose exec agent python /infra/load_test.py --memory-mb 256 --disk-mb 256 --duration 60
```

이 방식은 `agent`가 읽는 상태 파일(`/tmp/auto-healing-load-test/status.json`)을 함께 갱신하므로,
Prometheus에서 아래 메트릭 변화를 바로 확인할 수 있습니다.

- `infra_load_test_memory_mb`
- `infra_load_test_disk_mb`

연계된 alert rule:
- `LoadTestHighMemoryUsage`
- `LoadTestHighDiskUsage`

권장 기준:
- 시연/검증 기준 메모리 부하는 `256MB`, alert threshold는 `240MB`
- 시연/검증 기준 디스크 부하는 `256MB`, alert threshold는 `240MB`
- `dummy_*` alert는 기본 샘플용이며, 실제 infra load test 확인은 `LoadTest*` alert 기준으로 봅니다

검증 메모:
- Docker 기준 검증 명령: `docker compose exec -T agent python /infra/load_test.py --memory-mb 256 --disk-mb 256 --duration 22 --log-interval 5`
- 실행 중 `infra_load_test_memory_mb=267.7`, `infra_load_test_disk_mb=256.0` 확인
- Prometheus `/api/v1/alerts`에서 `LoadTestHighMemoryUsage`, `LoadTestHighDiskUsage`가 `firing` 상태로 확인됨
