from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.api.v1.bikes import _with_rental_state
from app.core.database import get_db
from app.models import Bike, User, UserRole
from app.schemas.tracking import (
    AccountState,
    BikeTrackingResponse,
    FleetBike,
    FleetResponse,
    TrackerOption,
    TrackersResponse,
    TrackResponse,
)
from app.services import gdegazel

router = APIRouter(prefix="/tracking", tags=["tracking"])


async def _load_status() -> tuple[AccountState, list[dict]]:
    """Сбой мониторинга не должен ломать гараж: состояние уходит в ответ, а не в HTTP-ошибку."""
    try:
        trackers = await gdegazel.trackers_status()
    except gdegazel.GdegazelError as exc:
        return AccountState(state=exc.account_state, message=str(exc)), []
    return AccountState(state=gdegazel.ACCOUNT_OK), trackers


def _visible_bikes_query(user: User):
    query = select(Bike).where(Bike.deleted_at.is_(None))
    if user.role != UserRole.ADMIN and user.branch_id:
        query = query.where(Bike.branch_id == user.branch_id)
    return query


async def _load_visible_bike(db: AsyncSession, bike_id: UUID, user: User) -> Bike:
    bike = (
        await db.execute(_visible_bikes_query(user).where(Bike.id == bike_id))
    ).scalar_one_or_none()
    if not bike:
        raise HTTPException(status_code=404, detail="Байк не найден")
    return bike


@router.get("/fleet", response_model=FleetResponse)
async def fleet(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account, trackers = await _load_status()
    by_id = {t.get("tracker_id"): t for t in trackers}

    bikes = list(
        (await db.execute(_visible_bikes_query(current_user).order_by(Bike.model))).scalars().all()
    )
    items = []
    for bike in bikes:
        await _with_rental_state(db, bike)
        raw = by_id.get(bike.tracker_id) if bike.tracker_id is not None else None
        items.append(
            FleetBike(
                id=bike.id,
                model=bike.model,
                frame_number=bike.frame_number,
                status=bike.status.value,
                is_rented=bike.is_rented,
                tracker_id=bike.tracker_id,
                position=gdegazel.to_position(raw) if raw else None,
            )
        )

    # Трекеры без байка показываем только админу: у них нет филиала
    unbound = []
    if current_user.role == UserRole.ADMIN:
        bound_ids = (
            await db.execute(
                select(Bike.tracker_id).where(
                    Bike.tracker_id.is_not(None), Bike.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        unbound = [
            gdegazel.to_position(t) for t in trackers if t.get("tracker_id") not in set(bound_ids)
        ]

    return FleetResponse(account=account, bikes=items, unbound_trackers=unbound)


@router.get("/trackers", response_model=TrackersResponse)
async def trackers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Трекеры для выбора в карточке байка."""
    account, raw = await _load_status()
    bound = dict(
        (
            await db.execute(
                select(Bike.tracker_id, Bike.id).where(
                    Bike.tracker_id.is_not(None), Bike.deleted_at.is_(None)
                )
            )
        ).all()
    )
    return TrackersResponse(
        account=account,
        items=[
            TrackerOption(
                tracker_id=t["tracker_id"],
                title=t.get("title"),
                note=t.get("note"),
                bike_id=bound.get(t["tracker_id"]),
            )
            for t in raw
            if t.get("tracker_id") is not None
        ],
    )


@router.get("/bikes/{bike_id}", response_model=BikeTrackingResponse)
async def bike_tracking(
    bike_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bike = await _load_visible_bike(db, bike_id, current_user)
    account, raw = await _load_status()
    if bike.tracker_id is None:
        return BikeTrackingResponse(account=account)

    match: Optional[dict] = next((t for t in raw if t.get("tracker_id") == bike.tracker_id), None)
    return BikeTrackingResponse(
        account=account,
        tracker_id=bike.tracker_id,
        position=gdegazel.to_position(match) if match else None,
    )


@router.get("/bikes/{bike_id}/track", response_model=TrackResponse)
async def bike_track(
    bike_id: UUID,
    # Интервалы длиннее суток API модерирует и может отвергать с кодом 429
    hours: int = Query(24, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bike = await _load_visible_bike(db, bike_id, current_user)
    if bike.tracker_id is None:
        raise HTTPException(status_code=409, detail="К байку не привязан трекер")

    end = datetime.now(timezone.utc)
    try:
        raw = await gdegazel.gps_log(bike.tracker_id, end - timedelta(hours=hours), end)
    except gdegazel.GdegazelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    points, dropped = gdegazel.clean_track(raw)
    return TrackResponse(points=points, dropped=dropped)
