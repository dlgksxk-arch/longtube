"""SQLite database setup and session management"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DB_PATH
import os

os.makedirs(DB_PATH.parent, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _migrate_scheduled_episodes() -> None:
    """v1.1.25 마이그레이션.

    기존 DB 의 `scheduled_episodes` 테이블에 구(舊) 스키마
    `scheduled_at DATETIME NOT NULL` 컬럼이 있으면, 이걸 그대로 두면
    새로운 INSERT 에서 NOT NULL 제약으로 실패한다. 그래서 이 함수는
    테이블을 통째로 재작성한다:
        1) 새 스키마로 임시 테이블 생성
        2) 기존 행 복사 (scheduled_at → substr HH:MM → scheduled_time)
        3) 기존 테이블 drop 후 rename

    신규 설치에서는 `create_all` 이 이미 새 스키마로 만들어 두었으므로
    `has_legacy_at == False` 분기를 타고 바로 리턴한다.
    """
    with engine.begin() as conn:
        try:
            cols = conn.execute(
                text("PRAGMA table_info(scheduled_episodes)")
            ).fetchall()
        except Exception:
            return
        if not cols:
            return

        # (cid, name, type, notnull, dflt_value, pk)
        col_names = {c[1] for c in cols}
        has_legacy_at = "scheduled_at" in col_names
        has_time = "scheduled_time" in col_names

        # Case A: 완전한 신규 스키마 (scheduled_time 만 있음) → 할 일 없음
        if has_time and not has_legacy_at:
            return

        # Case B: 둘 다 있음 or scheduled_at 만 있음 → 테이블 재작성 필요
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("DROP TABLE IF EXISTS scheduled_episodes_new"))
        conn.execute(
            text(
                """
                CREATE TABLE scheduled_episodes_new (
                    id TEXT PRIMARY KEY,
                    episode_number INTEGER NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    scheduled_time TEXT NOT NULL DEFAULT '09:00',
                    template_project_id TEXT,
                    privacy TEXT NOT NULL DEFAULT 'private',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    project_id TEXT,
                    video_url TEXT,
                    final_title TEXT,
                    error_message TEXT,
                    started_at DATETIME,
                    finished_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        # scheduled_time 값 결정: 이미 존재하면 그 값을, 없고 legacy 만 있으면 HH:MM 추출
        if has_time and has_legacy_at:
            time_expr = (
                "COALESCE(NULLIF(scheduled_time, ''), "
                "substr(scheduled_at, 12, 5), '09:00')"
            )
        elif has_legacy_at:
            time_expr = "COALESCE(substr(scheduled_at, 12, 5), '09:00')"
        else:
            time_expr = "'09:00'"

        conn.execute(
            text(
                f"""
                INSERT INTO scheduled_episodes_new (
                    id, episode_number, topic, scheduled_time,
                    template_project_id, privacy, enabled, status,
                    project_id, video_url, final_title, error_message,
                    started_at, finished_at, created_at, updated_at
                )
                SELECT
                    id, episode_number, topic, {time_expr},
                    template_project_id, privacy, enabled, status,
                    project_id, video_url, final_title, error_message,
                    started_at, finished_at, created_at, updated_at
                FROM scheduled_episodes
                """
            )
        )
        conn.execute(text("DROP TABLE scheduled_episodes"))
        conn.execute(
            text("ALTER TABLE scheduled_episodes_new RENAME TO scheduled_episodes")
        )
        conn.execute(text("PRAGMA foreign_keys=ON"))


def init_db():
    from app.models.project import Project  # noqa
    from app.models.cut import Cut  # noqa
    from app.models.api_log import ApiLog  # noqa
    from app.models.scheduled_episode import ScheduledEpisode  # noqa
    # v2.1.0 신규 테이블 (병렬). 기존 테이블과 독립.
    from app.models.channel_preset import ChannelPreset  # noqa
    from app.models.preset_queue_item import PresetQueueItem  # noqa
    from app.models.preset_task import PresetTask  # noqa
    from app.models.preset_usage_record import PresetUsageRecord  # noqa
    from app.models.event import Event  # noqa
    from app.models.api_key_vault import ApiKeyVault  # noqa
    Base.metadata.create_all(bind=engine)
    # 기존 설치 호환 마이그레이션
    try:
        _migrate_scheduled_episodes()
    except Exception as e:
        # 마이그레이션 실패는 앱 기동을 막지 않는다. 로그만 남긴다.
        print(f"[db] scheduled_episodes 마이그레이션 경고: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
