from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 설정 관리 클래스를 불러오기
from app.core.config import settings

# 1. 데이터베이스 엔진 생성 (실제 DB와 연결을 담당하는 객체)
# 💡 pool_pre_ping=True: 연결 풀(Pool)에서 세션을 가져오기 전에 DB가 살아있는지 
# 핑(Ping)을 날려보는 실무 필수 옵션입니다. (DB가 잠깐 끊겼을 때 앱이 뻗는 걸 방지해요!)
engine = create_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True
)

# 2. 세션 팩토리 생성 (세션 만듦)
# 💡 autocommit=False: 우리가 원할 때만 명시적으로 db.commit()을 호출하기 위해 끕니다. (데이터 안전성)
# 💡 autoflush=False: 커밋하기 전에 의도치 않게 변경사항이 DB로 넘어가는 것을 막아줍니다.
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)