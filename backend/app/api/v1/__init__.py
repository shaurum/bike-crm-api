from fastapi import APIRouter

api_router = APIRouter()

from app.api.v1 import health, auth, leads, bikes, bookings, customers, tasks, users, documents, webhooks, public, dashboard, settings, messages

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(leads.router, tags=["leads"])
api_router.include_router(bikes.router, tags=["bikes"])
api_router.include_router(bookings.router, tags=["bookings"])
api_router.include_router(customers.router, tags=["customers"])
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(public.router, tags=["public"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(messages.router, prefix="/conversations", tags=["messages"])