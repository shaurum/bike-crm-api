import logging
from celery import shared_task
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_contract_pdf(self, booking_id: str, template_id: str):
    import asyncio
    asyncio.run(_generate_contract_pdf(booking_id, template_id))


async def _generate_contract_pdf(booking_id: str, template_id: str):
    async with async_session_maker() as session:
        try:
            from app.models import Booking, ContractTemplate, Customer, Bike
            booking = await session.get(Booking, UUID(booking_id))
            if not booking:
                logger.error(f"Booking {booking_id} not found")
                return

            template = await session.get(ContractTemplate, UUID(template_id))
            if not template:
                logger.error(f"Template {template_id} not found")
                return

            from jinja2 import Template
            jinja_template = Template(template.html_template)

            customer = await session.get(Customer, booking.customer_id)
            bike = await session.get(Bike, booking.bike_id)

            context = {
                "booking": booking,
                "customer": customer,
                "bike": bike,
                "today": __import__("datetime").datetime.now().strftime("%d.%m.%Y"),
            }

            html = jinja_template.render(**context)

            from weasyprint import HTML
            pdf = HTML(string=html).write_pdf()

            from app.tasks.notifications import send_email_notification
            if customer and customer.email:
                send_email_notification.delay(
                    customer.email,
                    f"Договор аренды #{booking.id}",
                    f"<p>Уважаемый {customer.full_name},</p><p>В приложении ваш договор аренды.</p>",
                )

            logger.info(f"Generated contract PDF for booking {booking_id}")

        except Exception as e:
            await session.rollback()
            logger.exception(f"Error generating contract: {e}")
            raise


@shared_task
def send_contract_to_client(booking_id: str, template_id: str):
    generate_contract_pdf.delay(booking_id, template_id)