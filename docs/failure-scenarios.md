# 장애 시나리오 문서

Auto-Healing 시스템이 지원하는 장애 시뮬레이션 시나리오 목록입니다.  
각 시나리오는 **시뮬레이션 스크립트 → Prometheus 메트릭 → Alert → Auto-Healing 액션** 파이프라인으로 연결됩니다.

---

## 파이프라인 구조

```
simulate_*.py              agent/agent.py            Prometheus
  상태 파일 기록    →   status.json 읽어 Gauge 노출  →  alert rule 평가
(/tmp/.../status.json)     (2초 간격 폴링)             (rules.yml)

         → Alertmanager → webhook (backend) → 복구 액션 실행
                                              (run_recovery.py)
```

---

## 공통 사전 조건

| 항목 | 내용 |
|------|------|
| 실행 위치 | 프로젝트 루트 (Windows 호스트) |
| Python | `C:\python.exe` (3.11) |
| 필수 패키지 | `psycopg2-binary` (S2 전용) |
| Docker | 실행 중이어야 함 |
| 컨테이너 | `docker compose up -d` 로 기동 상태 |

> **인코딩 주의 (Windows)**: 한글 경로가 포함된 디렉터리에서 psycopg2를 사용하는 스크립트는 cp949/UTF-8 충돌이 발생합니다.  
> S2 스크립트는 host psycopg2 연결 실패 시 `docker exec psql` 방식으로 자동 대체합니다.

---

## 데모 환경 고정 체크리스트

> 시연 전에는 메트릭 상태와 포트 충돌을 통제해 예측 가능한 시작 상태를 만듭니다.

### 1. 데모 환경값 고정

```bash
# Windows PowerShell
Copy-Item .env.demo .env
```

`.env.demo`는 아래 값을 고정합니다.

| 항목 | 데모 기본값 | 목적 |
|------|-------------|------|
| `POSTGRES_MAX_CONNECTIONS` | `100` | DB 커넥션 풀 시나리오 기준값 고정 |
| `FORCE_CPU_USAGE` | `35` | dummy CPU 메트릭 안정화 |
| `FORCE_MEMORY_USAGE` | `45` | dummy memory 메트릭 안정화 |
| `FORCE_REQUEST_COUNT` | `180` | dummy request 메트릭 안정화 |
| `AGENT_UPDATE_INTERVAL` | `5` | agent 루프 부하 완화 |
| `AGENT_LOG_LEVEL` | `warning` | 반복 로그 억제 |
| `DEMO_MODE` | `true` | agent 랜덤 메트릭 기본값 고정 |

### 2. 포트/컨테이너 사전 점검

```bash
python infra/scripts/prepare_demo.py
```

점검 대상 포트:

| 포트 | 서비스 |
|------|--------|
| `5432` | PostgreSQL |
| `8080` | target_nginx |
| `8081` | upstream_app |
| `9100` | agent |
| `9090` | Prometheus |
| `9093` | Alertmanager |
| `8000` | backend |

> `8080`을 Airflow 등 다른 컨테이너가 점유하면 `target_nginx`가 시작되지 않습니다.

### 3. 데모 상태 초기화

```bash
python infra/scripts/prepare_demo.py --apply
```

초기화 대상:

| 상태 파일 | 초기화 내용 |
|-----------|-------------|
| `/tmp/auto-healing-scenarios/status.json` | 모든 장애 시나리오 메트릭 `0` |
| `/tmp/auto-healing-load-test/status.json` | load test 메모리/디스크 메트릭 `0` |

### 4. 모니터링 부하 최적화 상태

| 항목 | 현재 설정 | 상태 |
|------|-----------|------|
| Prometheus scrape interval | `15s` | 완료 |
| Prometheus evaluation interval | `15s` | 완료 |
| Agent update interval | env 기반, 기본 `5s` | 완료 |
| Agent 반복 로그 | `AGENT_LOG_LEVEL=debug`일 때만 출력 | 완료 |
| Dummy CPU/memory/request | env 또는 `DEMO_MODE`로 고정 | 완료 |

---

---

## 로드 테스트 시나리오

> 인프라 자원(메모리/디스크) 변화를 안전하게 시뮬레이션하는 기본 검증용 시나리오입니다.

### LT-1. 메모리 부하 (`LoadTestHighMemoryUsage`)

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/load_test.py` |
| Prometheus 메트릭 | `infra_load_test_memory_mb` |
| Alert 조건 | `> 240 MB`, 15초 유지 |
| 심각도 | warning |
| 자동 복구 | `update_resources` - 컨테이너 메모리 상한 조정 |

```bash
python3 infra/load_test.py --memory-mb 256 --duration 60
```

### LT-2. 디스크 부하 (`LoadTestHighDiskUsage`)

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/load_test.py` |
| Prometheus 메트릭 | `infra_load_test_disk_mb` |
| Alert 조건 | `> 240 MB`, 15초 유지 |
| 심각도 | warning |
| 자동 복구 | `cleanup_disk` - 임시 파일 정리 |

```bash
python3 infra/load_test.py --disk-mb 256 --duration 60
```

---

## 기본 장애 시나리오

### S1. Nginx 5xx 에러 (`NginxHighErrorRate`)

**시나리오 설명**: `upstream_app` 컨테이너를 중단시켜 Nginx가 502 Bad Gateway를 반환하게 유도합니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_nginx_5xx.py` |
| 대상 컨테이너 | `upstream_app` (중단), `target_nginx` (proxy) |
| Prometheus 메트릭 | `infra_nginx_5xx_total` |
| Alert 조건 | `> 0`, 15초 유지 |
| 심각도 | critical |
| 자동 복구 | `reload_nginx` - Nginx 설정 리로드 |

```bash
# 기본 (30초)
python infra/scripts/simulate_nginx_5xx.py

# 옵션
python infra/scripts/simulate_nginx_5xx.py --duration 60
python infra/scripts/simulate_nginx_5xx.py --no-restore   # upstream 재시작 생략
```

**시뮬레이션 흐름**:
1. `docker stop upstream_app` - Nginx가 502 반환 시작
2. 매초 HTTP 상태 확인, 5xx 누적 카운트를 상태 파일에 기록
3. `duration` 경과 후 `docker start upstream_app` (restore=True 시)
4. 메트릭 0으로 초기화

---

### S2. DB 커넥션 풀 고갈 (`DBConnectionPoolExhausted`)

**시나리오 설명**: PostgreSQL의 `max_connections` 이상으로 연결을 동시에 열어 커넥션 풀을 고갈시킵니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_connection_pool.py` |
| 대상 컨테이너 | `aiops_postgres` |
| Prometheus 메트릭 | `infra_db_active_connections`, `infra_db_max_connections` |
| Alert 조건 | `active / max >= 0.9`, 15초 유지 |
| 심각도 | critical |
| 자동 복구 | `update_db_config` - `max_connections` 값 상향 |

```bash
# 기본 (20개 연결, 30초 유지) - C:\tmp 에서 실행
python infra/scripts/simulate_connection_pool.py --connections 20 --duration 30
```

> **팁**: `.env`의 `POSTGRES_MAX_CONNECTIONS=10`으로 설정하면 고갈이 빠르게 발생합니다.

**시뮬레이션 흐름**:
1. psycopg2로 `connections` 개수만큼 동시 연결 시도
2. max_connections 초과 시 연결 실패 확인
3. 활성 연결 수와 max_connections 를 상태 파일에 기록
4. `duration` 유지 후 전체 연결 해제

---

### S3. 컨테이너 OOM Kill (`ContainerOOMKilled`)

**시나리오 설명**: `docker update`로 컨테이너에 낮은 메모리 제한을 설정하고 내부에서 메모리를 초과 할당해 OOM Killer를 유발합니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_oom.py` |
| 대상 컨테이너 | `target_nginx` (기본값) |
| Prometheus 메트릭 | `infra_container_oom_killed` |
| Alert 조건 | `> 0`, 5초 유지 |
| 심각도 | critical |
| 자동 복구 | `update_resources` - 메모리 제한 상향 |

```bash
# 기본 (64m 제한, 복구 포함)
python infra/scripts/simulate_oom.py --container target_nginx

# 옵션
python infra/scripts/simulate_oom.py --container upstream_app --limit 32m
python infra/scripts/simulate_oom.py --no-restore   # 메모리 제한 복원 생략
```

**시뮬레이션 흐름**:
1. `docker update --memory=64m --memory-swap=64m <container>`
2. 컨테이너 재시작 (새 제한 적용)
3. 컨테이너 내부에서 `dd`로 256MB 메모리 할당 시도
4. `docker inspect --format {{.State.OOMKilled}}`로 OOM 여부 확인
5. 복구 시 `docker update --memory=0` (무제한 복원)

---

## 심화 장애 시나리오

### S5. DB 데드락 (`DBDeadlockDetected`)

**시나리오 설명**: 두 psql 세션이 서로의 행 락을 교차 획득하도록 유도해 PostgreSQL의 DeadlockDetected 에러를 반복 발생시킵니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_deadlock.py` |
| 대상 컨테이너 | `aiops_postgres` |
| Prometheus 메트릭 | `infra_db_deadlock_count` |
| Alert 조건 | `> 0`, 5초 유지 |
| 심각도 | critical |
| 자동 복구 | `restart_container` - DB 컨테이너 재시작 |

```bash
# 기본 (3라운드)
python infra/scripts/simulate_deadlock.py

# 옵션
python infra/scripts/simulate_deadlock.py --rounds 5
python infra/scripts/simulate_deadlock.py --container aiops_postgres --user aiops_user --db aiops_db
```

**시뮬레이션 흐름**:
1. `_deadlock_test` 테이블 생성 (row 2개)
2. Thread A: id=1 잠금 -> 2초 대기 -> id=2 잠금 시도
3. Thread B: 0.5초 대기 -> id=2 잠금 -> id=1 잠금 시도 -> **DEADLOCK**
4. PostgreSQL이 한 세션을 자동 롤백, 데드락 횟수 기록
5. `rounds` 횟수만큼 반복 후 테이블 삭제

> psql 기반으로 동작하므로 Windows 인코딩 문제 없음

---

### S6. 좀비 프로세스 누적 (`ZombieProcessAccumulation`)

**시나리오 설명**: 컨테이너 내부에서 자식 프로세스를 fork 후 부모가 `wait()` 하지 않아 좀비 상태(Z) 프로세스를 의도적으로 누적시킵니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_zombie.py` |
| 대상 컨테이너 | `upstream_app` |
| Prometheus 메트릭 | `infra_zombie_process_count` |
| Alert 조건 | `>= 3`, 10초 유지 |
| 심각도 | warning |
| 자동 복구 | `restart_container` - 컨테이너 재시작으로 좀비 일괄 정리 |

```bash
# 기본 (8개 좀비, 30초)
python infra/scripts/simulate_zombie.py

# 옵션
python infra/scripts/simulate_zombie.py --container upstream_app --count 8 --duration 30
```

**시뮬레이션 흐름**:
1. `docker exec upstream_app python3 -c <fork 코드>` 백그라운드 실행
2. 부모 프로세스가 N개 자식을 fork - 자식들은 즉시 `os._exit(0)` 종료
3. 부모는 `wait()` 없이 `sleep(duration)` - 자식들이 좀비(Z) 상태로 잔류
4. `/proc/*/status`에서 `Z (zombie)` 항목 수를 2초 간격으로 폴링
5. duration 경과 후 부모 프로세스 종료 - 좀비 자동 소멸

---

### S7. 파일 디스크립터 고갈 (`FDExhaustionRisk`)

**시나리오 설명**: 컨테이너 내부에서 `/dev/null`을 반복 열어 ulimit의 95% 수준까지 FD를 소진합니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_fd_exhaustion.py` |
| 대상 컨테이너 | `upstream_app` |
| Prometheus 메트릭 | `infra_fd_usage_ratio` (0.0 ~ 1.0) |
| Alert 조건 | `>= 0.8` (80%), 10초 유지 |
| 심각도 | critical |
| 자동 복구 | `restart_container` - FD 테이블 초기화 |

```bash
# 기본 (30초)
python infra/scripts/simulate_fd_exhaustion.py

# 옵션
python infra/scripts/simulate_fd_exhaustion.py --container upstream_app --duration 30
```

**시뮬레이션 흐름**:
1. `ulimit -n`으로 soft limit 조회 (unlimited -> 8192 cap 적용)
2. `docker exec upstream_app python3 -c <FD 소진 코드>` 백그라운드 실행
3. `open('/dev/null', 'r')`을 soft_limit x 95%까지 반복
4. `/proc/<pid>/fd` 항목 수를 3초 간격 폴링 - `fd_count / soft_limit`로 비율 계산
5. duration 경과 후 프로세스 종료 - FD 자동 반환

---

### S8. 메모리 누수 (`MemoryLeakDetected`)

**시나리오 설명**: 컨테이너 내부에서 10MB 단위로 메모리를 점진적으로 할당해 누수가 발생하는 상황을 재현합니다.

| 항목 | 내용 |
|------|------|
| 스크립트 | `infra/scripts/simulate_memory_leak.py` |
| 대상 컨테이너 | `upstream_app` |
| Prometheus 메트릭 | `infra_memory_leak_mb` |
| Alert 조건 | `> 100 MB`, 15초 유지 |
| 심각도 | warning |
| 자동 복구 | `update_resources` - 메모리 제한 상향 조정 |

```bash
# 기본 (200MB 목표, 30초 유지)
python infra/scripts/simulate_memory_leak.py

# 옵션
python infra/scripts/simulate_memory_leak.py --container upstream_app --target-mb 150 --hold 20
```

**시뮬레이션 흐름**:
1. `docker exec upstream_app python3 -c <누수 코드>` 백그라운드 실행
2. 2초마다 `bytearray(10MB)` 할당, GC 방지를 위해 리스트에 보관
3. `docker stats --no-stream`으로 실제 메모리 사용량을 3초 간격 폴링
4. target_mb 도달 후 hold 초 동안 유지
5. 프로세스 종료 시 메모리 자동 반환

---

## 자동 복구 액션 요약

| 복구 액션 | 동작 | 관련 시나리오 |
|-----------|------|---------------|
| `restart_container` | `docker restart <container>` | S5, S6, S7 |
| `update_resources` | `docker update --memory --cpus` | LT-1, S3, S8 |
| `reload_nginx` | Nginx 설정 검사 + `nginx -s reload` | S1 |
| `update_db_config` | `ALTER SYSTEM SET <param>` + reload | S2 |
| `cleanup_disk` | 컨테이너 내 오래된 파일 삭제 | LT-2 |

---

## 전체 시나리오 한눈에 보기

| # | 이름 | 원인 | 메트릭 | 복구 액션 |
|---|------|------|--------|-----------|
| LT-1 | 메모리 부하 | 의도적 메모리 점유 | `infra_load_test_memory_mb > 240` | update_resources |
| LT-2 | 디스크 부하 | 의도적 파일 생성 | `infra_load_test_disk_mb > 240` | cleanup_disk |
| S1 | Nginx 5xx | upstream 컨테이너 중단 | `infra_nginx_5xx_total > 0` | reload_nginx |
| S2 | 커넥션 풀 고갈 | max_connections 초과 연결 | `active/max >= 0.9` | update_db_config |
| S3 | OOM Kill | 메모리 제한 초과 할당 | `infra_container_oom_killed > 0` | update_resources |
| S5 | DB 데드락 | 교차 row-lock | `infra_db_deadlock_count > 0` | restart_container |
| S6 | 좀비 프로세스 | fork + no wait | `infra_zombie_process_count >= 3` | restart_container |
| S7 | FD 고갈 | /dev/null 반복 open | `infra_fd_usage_ratio >= 0.8` | restart_container |
| S8 | 메모리 누수 | bytearray 점진 할당 | `infra_memory_leak_mb > 100` | update_resources |

---

## 복합 장애 시나리오

> 여러 단일 장애를 섞어 실제 운영처럼 "겉으로 보이는 증상"과 "우선 복구해야 할 원인"이 다른 상황을 검증합니다.  
> 목표는 AI가 단일 알림에 끌려가지 않고 `incident_types`, severity, 첫 번째 복구 액션을 올바르게 고르는지 확인하는 것입니다.

### C1. 업스트림 장애가 Nginx 5xx로 보이는 상황 (`upstream-collapse`)

| 항목 | 내용 |
|------|------|
| 조합 | S1 Nginx 5xx + S6 좀비 프로세스 |
| 실제 상황 | 앱 프로세스가 비정상 상태가 되면서 Nginx가 5xx를 반환 |
| AI 판단 포인트 | Nginx 자체 장애가 아니라 upstream 앱 장애가 5xx로 전파된 것으로 판단 |
| 기대 incident_types | `NGINX_5XX`, `CONTAINER_CRASH` |
| 기대 우선 액션 | `RESTART_CONTAINER` 또는 `RESTART_PROCESS` |

### C2. 앱 리소스 포화가 점진적으로 누적되는 상황 (`app-saturation`)

| 항목 | 내용 |
|------|------|
| 조합 | S8 메모리 누수 + S7 FD 고갈 |
| 실제 상황 | 앱이 죽지는 않았지만 메모리와 FD가 함께 고갈되어 장애 직전 상태 |
| AI 판단 포인트 | 즉시 재시작보다 용량 압박/누수성 장애로 보고 확장 또는 제한 상향을 우선 고려 |
| 기대 incident_types | `OOM`, `CONTAINER_CRASH` |
| 기대 우선 액션 | `SCALE_OUT` |

### C3. DB 커넥션 고갈 후 데드락이 이어지는 상황 (`db-cascade`)

| 항목 | 내용 |
|------|------|
| 조합 | S2 커넥션 풀 고갈 + S5 DB 데드락 |
| 실제 상황 | DB 연결 수가 한계에 가까운 상태에서 트랜잭션 경합까지 발생 |
| AI 판단 포인트 | 단순 데드락 1건이 아니라 DB 계층 전체 포화/경합으로 판단 |
| 기대 incident_types | `DB_CONNECTION` |
| 기대 우선 액션 | `RESTART_PROCESS` 또는 `RESTART_CONTAINER` |

### C4. 용량 부족이 실제 서비스 장애로 전파되는 상황 (`capacity-to-outage`)

| 항목 | 내용 |
|------|------|
| 조합 | S8 메모리 누수 + S3 OOM Kill + S1 Nginx 5xx |
| 실제 상황 | 메모리 누수가 OOM으로 이어지고, 그 결과 사용자 요청에 5xx가 발생 |
| AI 판단 포인트 | 5xx는 결과이며 1차 원인은 메모리/OOM 계열임을 구분 |
| 기대 incident_types | `OOM`, `NGINX_5XX` |
| 기대 우선 액션 | OOMKilled 확인 시 `RESTART_CONTAINER`, 누수 단계면 `SCALE_OUT` |

### C5. DB와 앱 리소스 압박이 동시에 발생하는 상황 (`mixed-control-plane`)

| 항목 | 내용 |
|------|------|
| 조합 | S2 커넥션 풀 고갈 + S8 메모리 누수 + S7 FD 고갈 |
| 실제 상황 | DB 계층과 앱 계층이 동시에 느려져 원인 우선순위가 모호한 상태 |
| AI 판단 포인트 | 여러 알림을 독립 장애로 흩뜨리지 않고 가장 위험한 병목을 첫 복구 대상으로 선정 |
| 기대 incident_types | `DB_CONNECTION`, `OOM`, `CONTAINER_CRASH` |
| 기대 우선 액션 | DB가 critical이면 `RESTART_PROCESS`/`RESTART_CONTAINER`, 앱 포화가 우세하면 `SCALE_OUT` |

```bash
# 사용 가능한 복합 프로필 확인
python infra/scripts/simulate_composite.py --list-profiles

# 실행 전 스케줄 확인
python infra/scripts/simulate_composite.py --profile upstream-collapse --dry-run

# 복합 시나리오 실행
python infra/scripts/simulate_composite.py --profile upstream-collapse
python infra/scripts/simulate_composite.py --profile app-saturation
python infra/scripts/simulate_composite.py --profile db-cascade
python infra/scripts/simulate_composite.py --profile capacity-to-outage
python infra/scripts/simulate_composite.py --profile mixed-control-plane
```

**운영 주의**:
- 복합 시나리오는 기존 `simulate_*.py`를 별도 프로세스로 실행합니다.
- 모든 시나리오는 같은 `SCENARIO_STATUS_FILE`에 메트릭을 기록하므로 Prometheus에는 여러 장애 메트릭이 동시에 노출됩니다.
- `db-cascade`는 `psycopg2-binary`가 필요하며, Windows 한글 경로 인코딩 문제가 있으면 `C:\tmp` 등 ASCII 경로에서 실행하세요.
- AI 평가는 "정답 액션 하나"만 보는 것이 아니라, 원인/증상 구분과 첫 복구 우선순위가 맞는지 함께 확인합니다.

---

## 주요 파일 경로

```
infra/
  load_test.py                      # 로드 테스트 (LT-1, LT-2)
  rules.yml                         # Prometheus alert 규칙
  alertmanager.yml                  # Alertmanager 설정 (webhook 라우팅)
  scripts/
    simulate_nginx_5xx.py           # S1
    simulate_connection_pool.py     # S2
    simulate_oom.py                 # S3
    simulate_deadlock.py            # S5
    simulate_zombie.py              # S6
    simulate_fd_exhaustion.py       # S7
    simulate_memory_leak.py         # S8
    simulate_composite.py           # 복합 장애 시나리오 실행기
    run_recovery.py                 # 복구 액션 통합 실행기
    update_resources.py             # update_resources 구현
    reload_nginx.py                 # reload_nginx 구현
    update_db_config.py             # update_db_config 구현
agent/
  agent.py                          # Prometheus 메트릭 노출 (포트 9100)
```
