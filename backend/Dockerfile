# 1. 베이스 이미지: 가볍고 튼튼한 파이썬 3.11 slim 버전 사용
FROM python:3.11-slim

# 2. 파이썬 로그가 버퍼링 없이 터미널에 바로 출력되도록 설정 (도커 로그 볼 때 필수!)
ENV PYTHONUNBUFFERED=1

# 3. 컨테이너 내부의 작업 폴더를 /app으로 지정
WORKDIR /app

# 4. PostgreSQL 연결(psycopg2 등)에 필요한 리눅스 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. 요구사항 파일(requirements.txt)만 먼저 복사
# (이렇게 하면 코드가 바뀌어도 패키지를 매번 새로 다운받지 않아 빌드가 훨씬 빨라짐)
COPY requirements.txt .

# 6. 파이썬 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 7. 나머지 모든 백엔드 코드(app 폴더, alembic 등)를 컨테이너 안으로 복사
COPY . .

# 8. 컨테이너가 8000번 포트를 쓴다는 것을 명시
EXPOSE 8000

# 9. FastAPI 서버 실행 명령어 (app 폴더 안의 main.py 안의 app 객체를 실행)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]