"""Пользователи: список для назначений и админ-управление."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, require_admin
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models import User, UserRole
from app.schemas.rental import UserCreate, UserPasswordReset, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/list", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Активные сотрудники — для назначения ответственного на сделку."""
    result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
    )
    return result.scalars().all()


# --- Админ-управление ---


@router.get("", response_model=List[UserResponse])
async def list_all_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Все аккаунты, включая деактивированные."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")

    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email уже занят")

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        branch_id=payload.branch_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    data = payload.model_dump(exclude_unset=True)

    # Администратор не может разжаловать или деактивировать сам себя
    if user.id == admin.id:
        if "role" in data and data["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=400, detail="Нельзя изменить роль собственного аккаунта"
            )
        if data.get("is_active") is False:
            raise HTTPException(
                status_code=400, detail="Нельзя деактивировать собственный аккаунт"
            )

    # Последнего активного администратора нельзя понижать
    if user.role == UserRole.ADMIN and "role" in data and data["role"] != UserRole.ADMIN:
        from sqlalchemy import func

        active_admins = (
            await db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.ADMIN, User.is_active == True)  # noqa: E712
            )
            or 0
        )
        if active_admins <= 1:
            raise HTTPException(
                status_code=400, detail="Нельзя понизить последнего администратора"
            )

    for field, value in data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/password", response_model=UserResponse)
async def reset_password(
    user_id: UUID,
    payload: UserPasswordReset,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Админ сбрасывает пароль пользователю — текущий пароль не нужен."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")

    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Полное удаление аккаунта. Нельзя удалить себя и последнего админа."""
    from sqlalchemy import func

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    if user.role == UserRole.ADMIN:
        others = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.id != user.id)
        )
        if not others:
            raise HTTPException(
                status_code=400, detail="Нельзя удалить последнего администратора"
            )

    await db.delete(user)
    await db.commit()
    return {"ok": True}
