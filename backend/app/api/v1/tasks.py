from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models import Task, TaskType, TaskStatus, TaskPriority, User, UserRole
from app.schemas.crm import (
    TaskCreate,
    TaskResponse,
    TaskListResponse,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

DONE_STATES = (TaskStatus.DONE, TaskStatus.CANCELLED)


def _can_modify(user: User, task: Task) -> bool:
    return (
        user.role == UserRole.ADMIN
        or task.assignee_id == user.id
        or task.created_by_id == user.id
    )


def _load_options():
    return (
        selectinload(Task.assignee),
        selectinload(Task.created_by),
        selectinload(Task.lead),
        selectinload(Task.booking),
        selectinload(Task.bike),
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    status: Optional[TaskStatus] = None,
    type: Optional[TaskType] = None,
    priority: Optional[TaskPriority] = None,
    assignee_id: Optional[UUID] = None,
    overdue: bool = Query(False),
    q: Optional[str] = Query(None, max_length=200),
    related_bike_id: Optional[UUID] = None,
    related_booking_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Task).options(*_load_options())

    if status:
        query = query.where(Task.status == status)
    if type:
        query = query.where(Task.type == type)
    if priority:
        query = query.where(Task.priority == priority)
    if assignee_id:
        query = query.where(Task.assignee_id == assignee_id)
    elif current_user.role != UserRole.ADMIN:
        query = query.where(Task.assignee_id == current_user.id)
    if overdue:
        query = query.where(
            Task.due_at.isnot(None),
            Task.due_at < datetime.now(timezone.utc),
            Task.status.notin_(DONE_STATES),
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    if related_bike_id:
        query = query.where(Task.related_bike_id == related_bike_id)
    if related_booking_id:
        query = query.where(Task.related_booking_id == related_booking_id)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        query.order_by(Task.due_at.asc().nullslast(), Task.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "items": tasks,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Task).options(*_load_options()).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    if not data.get("assignee_id"):
        data["assignee_id"] = current_user.id
    task = Task(**data, created_by_id=current_user.id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not _can_modify(current_user, task):
        raise HTTPException(status_code=403, detail="Нет доступа")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: UUID,
    status: TaskStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not _can_modify(current_user, task):
        raise HTTPException(status_code=403, detail="Нет доступа")
    task.status = status
    await db.commit()
    return {"message": "Статус обновлен", "status": task.status.value}


@router.delete("/{task_id}")
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not _can_modify(current_user, task):
        raise HTTPException(status_code=403, detail="Нет доступа")
    await db.delete(task)
    await db.commit()
    return {"ok": True}
