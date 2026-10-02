from fastapi import APIRouter

api_router = APIRouter()

from app.api.v1 import health, auth, leads, bikes, bookings, customers, tasks, webhooks, public, dashboard

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(bikes.router, prefix="/bikes", tags=["bikes"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])