# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. FastAPI 애플리케이션 생성
app = FastAPI(
    title="AIOps Auto-Healing API",
    description="중앙 API",
    version="1.0.0",
)

# 2. CORS 설정 (나중에 프론트엔드 대시보드와 연결할 때 에러가 나지 않도록 미리 세팅)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 나중에 실제 프론트엔드 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 기본 헬스 체크 엔드포인트 (서버가 잘 살았는지 확인용)
@app.get("/")
async def root():
    return {"message": "Welcome to AIOps Auto-Healing System!"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Backend is running flawlessly!"}