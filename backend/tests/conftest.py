import os

# Тестовая БД выставляется ДО импорта app.*, чтобы settings и глобальный engine смотрели в неё.
# Боевая БД bike_crm тестами не затрагивается.
os.environ["POSTGRES_DB"] = "bike_crm_test"
TEST_DB_NAME = "bike_crm_test"

import asyncio  # noqa: E402
from typing import AsyncIterator, Dict  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import engine as app_engine, get_db  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User, UserRole  # noqa: E402


# Защита от запуска против боевой БД
assert settings.POSTGRES_DB == TEST_DB_NAME, "Тесты должны работать только с БД bike_crm_test"
assert app_engine.url.database == TEST_DB_NAME, "Глобальный engine смотрит не в bike_crm_test"
assert settings.DATABASE_URL.rsplit("/", 1)[-1] == TEST_DB_NAME, "DATABASE_URL указывает не на bike_crm_test"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "test-password-123"


def _make_engine():
    """Движок тестов: NullPool, чтобы соединения не привязывались к event loop другого теста."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    assert engine.url.database == TEST_DB_NAME, "Тестовый движок смотрит не в bike_crm_test"
    return engine


async def _ensure_database() -> None:
    """Создать bike_crm_test, если её нет (подключаемся к служебной БД postgres)."""
    conn = await asyncpg.connect(
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


async def _create_schema() -> None:
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            # На случай остатков от упавшего прогона
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _drop_schema() -> None:
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Схема тестовой БД: создаётся один раз на сессию и удаляется в конце."""
    asyncio.run(_ensure_database())
    asyncio.run(_create_schema())
    yield
    asyncio.run(_drop_schema())


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Сессия к тестовой БД; после теста все таблицы очищаются."""
    engine = _make_engine()
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    session = session_maker()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент к приложению; get_db отдаёт сессию тестовой БД."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Активный администратор (пароль — ADMIN_PASSWORD)."""
    user = User(
        email=ADMIN_EMAIL,
        hashed_password=get_password_hash(ADMIN_PASSWORD),
        full_name="Тестовый администратор",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(admin_user: User) -> Dict[str, str]:
    """Заголовок авторизации; токен в том же формате, что выдаёт /auth/login."""
    token = create_access_token(
        data={"sub": str(admin_user.id), "email": admin_user.email, "role": admin_user.role.value}
    )
    return {"Authorization": f"Bearer {token}"}
