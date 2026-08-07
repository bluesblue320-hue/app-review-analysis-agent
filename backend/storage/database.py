"""SQLAlchemy models and shared database runtime."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


class Base(DeclarativeBase):
    pass


class DatasetModel(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_rows: Mapped[int] = mapped_column(Integer)
    valid_rows: Mapped[int] = mapped_column(Integer)
    removed_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rating_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_reasons_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    columns_json: Mapped[list[str]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    analysis_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[Any] = mapped_column(DateTime(timezone=True), index=True)
    reviews: Mapped[list[ReviewModel]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    insights: Mapped[list[InsightModel]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReviewModel(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.dataset_id", ondelete="CASCADE"),
        index=True,
    )
    row_number: Mapped[int] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("dataset_id", "row_number", name="uq_reviews_dataset_row"),
    )


class InsightModel(Base):
    __tablename__ = "insights"

    insight_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.dataset_id", ondelete="CASCADE"),
        index=True,
    )
    scope_signature: Mapped[str] = mapped_column(String(64), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(50), default="deepseek")
    model_name: Mapped[str] = mapped_column(String(100), default="deepseek-v4-flash")
    analysis_version: Mapped[str] = mapped_column(String(32), default="v1")
    insight_fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[Any] = mapped_column(DateTime(timezone=True), index=True)


class DatabaseRuntime:
    """SQLAlchemy engine + session factory.

    Schema creation is explicit: ``create_schema=True`` is only used for test
    SQLite runtimes. Production PostgreSQL must be migrated by Alembic; the
    runtime never calls ``Base.metadata.create_all`` implicitly.
    """

    def __init__(self, database_url: str, *, create_schema: bool = False) -> None:
        connect_args = (
            {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        )
        self.engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if database_url.startswith("sqlite"):
            event.listen(self.engine, "connect", _configure_sqlite)
        if create_schema:
            Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            future=True,
        )


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


@lru_cache(maxsize=16)
def get_database_runtime(
    database_url: str, *, create_schema: bool = False
) -> DatabaseRuntime:
    return DatabaseRuntime(database_url, create_schema=create_schema)


def database_ready(engine: Engine) -> bool:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
