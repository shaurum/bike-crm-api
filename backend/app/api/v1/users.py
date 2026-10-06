from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import User
from app.schemas.rental import UserBrief

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/list", response_model=List[UserBrief])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Активные сотрудники — для назначения ответственного на сделку."""
    result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)
    )
    return result.scalars().all()