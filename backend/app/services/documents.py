"""Формирование PDF-документов из шаблона и данных CRM."""

import os
from datetime import datetime, timezone
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.core.config import settings

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def fmt_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def fmt_datetime(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return f"{fmt_date(value)} {value.hour:02d}:{value.minute:02d}"


def fmt_money(value) -> str:
    if value in (None, ""):
        return ""
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")


def build_contract_context(
    lead,
    customer,
    bike,
    company,
    doc_number: str,
    city: str = "Москва",
) -> dict:
    """Собирает значения для подстановки в шаблон договора."""
    issued = datetime.now(timezone.utc)

    rental_start = getattr(lead, "rental_start_at", None)
    rental_end = getattr(lead, "rental_end_at", None)

    days = None
    if rental_start and rental_end:
        try:
            delta = rental_end - rental_start
            days = max(round(delta.total_seconds() / 86400), 1)
        except TypeError:
            days = None

    if days is None:
        period_label = "период аренды"
    elif days <= 1:
        period_label = "сутки"
    elif days <= 7:
        period_label = "неделю"
    else:
        period_label = f"{days} дней"

    return {
        "doc_number": doc_number,
        "city": city,
        "contract_day": f"{issued.day:02d}",
        "contract_month": MONTHS[issued.month - 1],
        "contract_year": issued.year,
        "landlord": {
            "name": company.name if company else "",
            "short_name": company.name if company else "",
            "ogrnip": company.ogrnip if company else None,
            "inn": company.inn if company else None,
            "phone": company.phone if company else None,
            "address": company.address if company else None,
            "return_address": company.return_address if company else None,
            "age_restriction": company.age_restriction if company else None,
            "deposit_return": company.deposit_return if company else None,
            "photo_consent": company.photo_consent if company else None,
        },
        "renter": {
            "full_name": customer.full_name if customer else None,
            "birth_date": fmt_date(customer.birth_date) if customer else None,
            "passport_series": customer.passport_series if customer else None,
            "passport_number": customer.passport_number if customer else None,
            "passport_issued_by": customer.passport_issued_by if customer else None,
            "passport_issued_date": fmt_date(customer.passport_issued_date) if customer else None,
            "address": customer.address if customer else None,
            "phone": customer.phone if customer else None,
            "email": customer.email if customer else None,
        },
        "bike": {
            "model": bike.model if bike else None,
            "frame_number": bike.frame_number if bike else None,
            "purchase_price": fmt_money(bike.purchase_price) if bike else None,
        },
        "rental_start": fmt_datetime(rental_start),
        "rental_end": fmt_datetime(rental_end),
        "price": fmt_money(lead.amount) if lead and lead.amount is not None else None,
        "total": fmt_money(lead.amount) if lead and lead.amount is not None else None,
        "deposit": fmt_money(
            max((p.deposit or 0) for p in bike.prices) if bike and bike.prices else None
        ) or None,
        "period_label": period_label,
    }


def missing_fields(context: dict) -> list[str]:
    """Какие обязательные для договора поля ещё не заполнены."""
    missing = []
    renter = context["renter"]
    for label, key in [
        ("ФИО арендатора", "full_name"),
        ("дата рождения", "birth_date"),
        ("серия паспорта", "passport_series"),
        ("номер паспорта", "passport_number"),
    ]:
        if not renter.get(key):
            missing.append(label)
    if not context.get("price"):
        missing.append("сумма аренды")
    return missing


def render_contract_pdf(context: dict) -> bytes:
    html = env.get_template("rental_contract.html").render(**context)
    return HTML(string=html).write_pdf()


def save_pdf(data: bytes, filename: str) -> tuple[str, int]:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(path, "wb") as fh:
        fh.write(data)
    return f"/uploads/{filename}", len(data)


def next_document_number(existing_count: int) -> str:
    return f"Д-{existing_count + 1:04d}"