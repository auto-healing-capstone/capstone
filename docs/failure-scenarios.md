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
> S2 스크립트는 `C:\tmp` 등 ASCII 경로에서 실행하세요.

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
    run_recovery.py                 # 복구 액션 통합 실행기
    update_resources.py             # update_resources 구현
    reload_nginx.py                 # reload_nginx 구현
    update_db_config.py             # update_db_config 구현
agent/
  agent.py                          # Prometheus 메트릭 노출 (포트 9100)
```
