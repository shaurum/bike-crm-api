from datetime import timedelta
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token_type,
)
from app.models import User, UserRole
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str | None = None
    role: UserRole = UserRole.MANAGER
    branch_id: uuid.UUID | None = None
    invite_token: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    branch_id: uuid.UUID | None
    is_active: bool

    class Config:
        from_attributes = True


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if not payload or not verify_token_type(token, "access"):
        raise credentials_exception
    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise credentials_exception
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Только для администратора — управление пользователями и настройками."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Действие доступно только администратору",
        )
    return current_user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Регистрация по приглашению; без него — только на пустой базе (bootstrap, admin)."""
    from datetime import datetime, timezone

    from sqlalchemy import func

    from app.models import Invite

    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")

    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    total = await db.scalar(select(func.count()).select_from(User)) or 0
    role = UserRole.ADMIN
    invite = None

    if user_data.invite_token:
        result = await db.execute(
            select(Invite).where(Invite.token == user_data.invite_token)
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise HTTPException(status_code=400, detail="Неверная ссылка-приглашение")
        if invite.used_at:
            raise HTTPException(status_code=403, detail="Приглашение уже использовано")
        if invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Приглашение истекло")
        if invite.email and invite.email.lower() != user_data.email.lower():
            raise HTTPException(
                status_code=403,
                detail="Приглашение оформлено на другой email",
            )
        role = UserRole(invite.role)
    elif total > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Регистрация закрыта — аккаунт создаёт администратор",
        )

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
        role=role,
        branch_id=user_data.branch_id,
    )
    db.add(user)
    if invite:
        invite.used_at = datetime.now(timezone.utc)
        invite.used_by = user.id
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/register-status")
async def register_status(db: AsyncSession = Depends(get_db)):
    """Можно ли регистрироваться без приглашения (пустая база — bootstrap)."""
    from sqlalchemy import func

    total = await db.scalar(select(func.count()).select_from(User)) or 0
    return {"open": total == 0}


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь деактивирован")

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    user.last_login = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(token)
    if not payload or not verify_token_type(token, "refresh"):
        raise HTTPException(status_code=401, detail="Неверный refresh токен")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Неверный токен")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Пользователь не найден или деактивирован")

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role.value})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user