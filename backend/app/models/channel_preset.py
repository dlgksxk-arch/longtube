"""ChannelPreset — v2.1.0 신규.

프리셋 단일 진실원(single source of truth).

- 채널(CH1~CH4) × 폼타입(딸깍폼/테스트폼) 조합으로 저장된다.
- 딸깍폼은 채널당 1개로 제한된다 (unique index).
- 테스트폼은 같은 채널에 N개 가능.
- 9 섹션 설정(식별/내용/AI 모델/영상 구조/자막/레퍼런스/업로드/자동화/음향)은
  `config` JSON 한 곳에 모여 있으며, MutableDict 로 감싸서 in-place 변경도
  SQLAlchemy 가 감지한다.

명명 규칙:
    full_name = f"{CH{channel_id}}-{form_type}-{name}"
    예) CH1-딸깍폼-10분역공

호환성:
    기존 v1.x 테이블(projects, cuts, scheduled_episodes, api_logs,
    api_balances, api_keys) 은 전혀 건드리지 않는다. 본 테이블은
    **병렬** 로 존재한다.
"""
from sqlalchemy import (
    Column,
    Integer,
    Text,
    Boolean,
    DateTime,
    JSON,
    UniqueConstraint,
    Index,
    CheckConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func

from app.models.database import Base


FORM_TYPE_DDALKKAK = "딸깍폼"
FORM_TYPE_TEST = "테스트폼"


class ChannelPreset(Base):
    __tablename__ = "channel_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 1~4. 딸깍폼은 이 값에 고정 바인딩된다.
    channel_id = Column(Integer, nullable=False)

    # "딸깍폼" 또는 "테스트폼"
    form_type = Column(Text, nullable=False)

    # 사용자 지정 이름 (예: "10분역공")
    name = Column(Text, nullable=False)

    # 자동 조합: f"CH{channel_id}-{form_type}-{name}"
    # 저장 시점에 서버에서 재계산해서 넣는다.
    full_name = Column(Text, nullable=False)

    # 9 섹션 전체 설정. dict in-place mutation 감지를 위해 MutableDict.
    config = Column(MutableDict.as_mutable(JSON), nullable=False, default=dict)

    # 편집 페이지 modified 뱃지 판정용. 저장 시 False 로 내려간다.
    is_modified = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # 딸깍폼은 채널당 1개만. 테스트폼은 제약 없음.
        # SQLite 는 partial unique index 를 지원하므로 Index 로 구현.
        Index(
            "uq_channel_presets_ddalkkak_per_channel",
            "channel_id",
            unique=True,
            sqlite_where=Column("form_type") == FORM_TYPE_DDALKKAK,
        ),
        CheckConstraint(
            f"form_type in ('{FORM_TYPE_DDALKKAK}', '{FORM_TYPE_TEST}')",
            name="ck_channel_presets_form_type",
        ),
        CheckConstraint(
            "channel_id >= 1 AND channel_id <= 4",
            name="ck_channel_presets_channel_range",
        ),
    )

    def recompute_full_name(self) -> None:
        """저장 직전 호출. name 이나 channel_id, form_type 이 바뀌면 재조합."""
        self.full_name = f"CH{self.channel_id}-{self.form_type}-{self.name}"
