import logging
import httpx
from celery import shared_task
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.models import Task, TaskStatus, User, Booking, BookingStatus, Bike, BikeStatus

logger = logging.getLogger(__name__)

engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool
    )
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@shared_task
def send_telegram_notification(chat_id: str, text: str):
    import asyncio
    asyncio.run(_send_telegram_notification(chat_id, text))


async def _send_telegram_notification(chat_id: str, text: str):
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram bot token not configured")
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            if response.status_code != 200:
                logger.error(f"Telegram send failed: {response.text}")
        except Exception as e:
            logger.exception(f"Telegram notification error: {e}")


@shared_task
def send_email_notification(to_email: str, subject: str, html_content: str):
    import asyncio
    asyncio.run(_send_email_notification(to_email, subject, html_content))


async def _send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.RESEND_API_KEY and not settings.SENDGRID_API_KEY:
        logger.warning("Email provider not configured")
        return

    if settings.RESEND_API_KEY:
        url = "https://api.resend.com/emails"
        headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}
        data = {"from": settings.EMAIL_FROM, "to": [to_email], "subject": subject, "html": html_content}
    else:
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {"Authorization": f"Bearer {settings.SENDGRID_API_KEY}", "Content-Type": "application/json"}
        data = {
            "personalizations": [{"to": [{"email": to_email}], "subject": subject}],
            "from": {"email": settings.EMAIL_FROM},
            "content": [{"type": "text/html", "value": html_content}],
        }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code not in (200, 202):
                logger.error(f"Email send failed: {response.text}")
        except Exception as e:
            logger.exception(f"Email notification error: {e}")


@shared_task
def check_overdue_tasks():
    import asyncio
    asyncio.run(_check_overdue_tasks())


async def _check_overdue_tasks():
    async with async_session_maker() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Task).where(
                Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
                Task.due_at < now,
            )
        )
        overdue_tasks = result.scalars().all()

        for task in overdue_tasks:
            if task.assignee:
                if task.assignee.telegram_chat_id:
                    send_telegram_notification.delay(
                        task.assignee.telegram_chat_id,
                        f"⚠️ Просроченная задача!\n{task.title}\nДедлайн: {task.due_at.strftime('%d.%m.%Y %H:%M')}",
                    )
                if task.assignee.email:
                    send_email_notification.delay(
                        task.assignee.email,
                        "Просроченная задача в Bike CRM",
                        f"<p>Задача <b>{task.title}</b> просрочена.</p><p>Дедлайн: {task.due_at.strftime('%d.%m.%Y %H:%M')}</p>",
                    )


@shared_task
def notify_booking_reminders():
    import asyncio
    asyncio.run(_notify_booking_reminders())


async def _notify_booking_reminders():
    async with async_session_maker() as session:
        now = datetime.now(timezone.utc)
        soon = now + timedelta(hours=1)

        bookings = await session.execute(
            select(Booking).where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.start_at <= soon,
                Booking.start_at > now,
            )
        )
        for booking in bookings.scalars().all():
            if booking.manager and booking.manager.telegram_chat_id:
                send_telegram_notification.delay(
                    booking.manager.telegram_chat_id,
                    f"📅 Через час аренда!\nБайк: {booking.bike.model}\nКлиент: {booking.customer.full_name}\nНачало: {booking.start_at.strftime('%d.%m %H:%M')}",
                )


@shared_task
def notify_daily_schedule():
    import asyncio
    asyncio.run(_notify_daily_schedule())


async def _notify_daily_schedule():
    async with async_session_maker() as session:
        from app.models import User, UserRole
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        admins = await session.execute(
            select(User).where(User.role == UserRole.ADMIN, User.is_active == True, User.telegram_chat_id.isnot(None))
        )

        for admin in admins.scalars().all():
            bookings = await session.execute(
                select(Booking).where(
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ACTIVE]),
                    Booking.start_at >= today_start,
                    Booking.start_at < tomorrow_start,
                )
            )
            bookings_list = bookings.scalars().all()

            text = "📋 План на сегодня:\n"
            for b in bookings_list:
                text += f"\n• {b.start_at.strftime('%H:%M')} — {b.bike.model} ({b.customer.full_name})"

            if bookings_list:
                send_telegram_notification.delay(admin.telegram_chat_id, text)