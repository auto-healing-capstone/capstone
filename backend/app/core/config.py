import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 현재 파일(config.py)의 부모의 부모 폴더(root)에 있는 .env 찾기
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    # API 기본 정보
    PROJECT_NAME: str = "AIOps Auto-Healing API"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str
    postgres_user: str
    postgres_password: str
    postgres_db: str

    # AI (OpenAI Function Calling을 위한 키)
    OPENAI_API_KEY: str = ""

    # Slack (Human-in-the-loop 관리자 승인용)
    SLACK_BOT_TOKEN: str = ""
    SLACK_CHANNEL_ID: str = ""

    # .env 파일에서 변수들을 자동으로 읽어오도록 설정
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH), # .env 파일 경로 지정
        env_file_encoding="utf-8",
        extra="ignore"  # .env에 정의되지 않은 변수는 무시 (안정성 강화)
    )

# 앱 전체에서 싱글톤처럼 사용할 수 있게 인스턴스화
settings = Settings()