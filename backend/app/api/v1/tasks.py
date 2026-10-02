from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Task, TaskType, TaskStatus, User, UserRole

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = None,
    type: Optional[TaskType] = None,
    assignee_id: Optional[UUID] = None,
    related_bike_id: Optional[UUID] = None,
    related_booking_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Task).options(
        selectinload(Task.assignee),
        selectinload(Task.lead),
        selectinload(Task.booking),
        selectinload(Task.bike),
    )

    if status:
        query = query.where(Task.status == status)
    if type:
        query = query.where(Task.type == type)
    if assignee_id:
        query = query.where(Task.assignee_id == assignee_id)
    elif current_user.role != UserRole.ADMIN:
        query = query.where(Task.assignee_id == current_user.id)
    if related_bike_id:
        query = query.where(Task.related_bike_id == related_bike_id)
    if related_booking_id:
        query = query.where(Task.related_booking_id == related_booking_id)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(Task.due_at.asc().nullslast()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "items": tasks,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.lead),
            selectinload(Task.booking),
            selectinload(Task.bike),
        )
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: UUID,
    status: TaskStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if current_user.role != UserRole.ADMIN and task.assignee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    task.status = status
    await db.commit()
    return {"message": "Статус обновлен"}


@router.post("", status_code=201)
async def create_task(
    task_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = Task(**task_data)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task