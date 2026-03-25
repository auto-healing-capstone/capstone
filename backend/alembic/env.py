import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from dotenv import load_dotenv  # 루트의 .env를 읽어오기 위함

# ==========================================
# 1. 경로 설정 및 .env 로드 
# ==========================================
# 현재 파일(alembic/env.py) 기준 backend 폴더와 최상단 루트 폴더 경로 계산
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)

# app 모듈을 찾을 수 있게 파이썬 경로에 backend 추가
sys.path.append(BACKEND_DIR)

# 루트 폴더에 있는 .env 파일을 강제로 읽어옴
load_dotenv(os.path.join(ROOT_DIR, ".env"))


# ==========================================
# 2. FastAPI 설정 및 SQLAlchemy 모델 임포트
# ==========================================
from app.core.config import settings
from app.models.schema import Base 

config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ==========================================
# 3. Alembic 핵심 설정
# ==========================================
target_metadata = Base.metadata

# .env 파일에서 가져온 DATABASE_URL을 알렘빅에게 주입
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)



def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
