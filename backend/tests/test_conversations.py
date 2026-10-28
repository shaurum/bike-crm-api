"""Раздел «Сообщения»: поле deal_state и фильтр status_filter в GET /api/v1/conversations.

Контракт deal_state (PLAN.md, П3):
- active: лид в NEW / CONTACTED / QUALIFIED / BOOKING;
- won: лид в WON;
- lost: лид в LOST;
- none: у диалога нет лида.
"""

import uuid
from typing import Dict, List, Optional, Set, Tuple

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Customer, Lead, LeadSource, LeadSourceType, LeadStatus

CONVERSATIONS_URL = "/api/v1/conversations"

# (статус лида или None для диалога без лида, ожидаемый deal_state)
DEAL_STATE_CASES = [
    pytest.param(LeadStatus.NEW, "active", id="new"),
    pytest.param(LeadStatus.CONTACTED, "active", id="contacted"),
    pytest.param(LeadStatus.QUALIFIED, "active", id="qualified"),
    pytest.param(LeadStatus.BOOKING, "active", id="booking"),
    pytest.param(LeadStatus.WON, "won", id="won"),
    pytest.param(LeadStatus.LOST, "lost", id="lost"),
    pytest.param(None, "none", id="no_lead"),
]

# Все диалоги для теста фильтров: по одному на каждый случай таблицы
SEED_CASES: List[Tuple[Optional[LeadStatus], str]] = [
    (LeadStatus.NEW, "active"),
    (LeadStatus.CONTACTED, "active"),
    (LeadStatus.QUALIFIED, "active"),
    (LeadStatus.BOOKING, "active"),
    (LeadStatus.WON, "won"),
    (LeadStatus.LOST, "lost"),
    (None, "none"),
]

FILTER_CASES = [
    pytest.param({"status_filter": "active"}, {"active"}, id="active"),
    pytest.param({"status_filter": "closed"}, {"won", "lost", "none"}, id="closed"),
    pytest.param({}, {"active", "won", "lost", "none"}, id="no_param"),
    pytest.param({"status_filter": "all"}, {"active", "won", "lost", "none"}, id="all"),
]


@pytest_asyncio.fixture
async def lead_source(db_session: AsyncSession) -> LeadSource:
    """Источник для лидов: у лида source_id обязателен."""
    source = LeadSource(
        type=LeadSourceType.MANUAL,
        name="Тестовый источник",
        config={},
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


async def _create_conversation(
    db: AsyncSession,
    source: LeadSource,
    status: Optional[LeadStatus],
    name: str,
) -> Conversation:
    """Клиент, при необходимости лид с нужным статусом и диалог между ними.

    Клиент создаётся всегда: GET /conversations отбрасывает диалоги без клиента.
    """
    customer = Customer(full_name=name)
    db.add(customer)
    await db.flush()

    lead: Optional[Lead] = None
    if status is not None:
        lead = Lead(
            source_id=source.id,
            external_id=f"test-{uuid.uuid4().hex}",
            client_name=name,
            status=status,
            customer_id=customer.id,
        )
        db.add(lead)
        await db.flush()

    conversation = Conversation(
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
        status="open",
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def _get_list(client: AsyncClient, headers: dict, params: Optional[dict] = None) -> List[dict]:
    response = await client.get(CONVERSATIONS_URL, headers=headers, params=params or {})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("lead_status, expected_state", DEAL_STATE_CASES)
async def test_deal_state_matches_contract(
    client: AsyncClient,
    db_session: AsyncSession,
    lead_source: LeadSource,
    auth_headers: dict,
    lead_status: Optional[LeadStatus],
    expected_state: str,
):
    conversation = await _create_conversation(db_session, lead_source, lead_status, "Клиент тест")

    items = await _get_list(client, auth_headers)

    item = next((i for i in items if i["id"] == str(conversation.id)), None)
    assert item is not None, f"Диалог не попал в ответ: {items}"
    assert item["deal_state"] == expected_state
    assert item["lead_id"] == (str(conversation.lead_id) if conversation.lead_id else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("params, expected_states", FILTER_CASES)
async def test_status_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    lead_source: LeadSource,
    auth_headers: dict,
    params: dict,
    expected_states: Set[str],
):
    # Один диалог на каждый случай таблицы: id -> ожидаемый deal_state
    expected_by_id: Dict[str, str] = {}
    for idx, (lead_status, state) in enumerate(SEED_CASES):
        conversation = await _create_conversation(
            db_session, lead_source, lead_status, f"Клиент {idx}"
        )
        expected_by_id[str(conversation.id)] = state

    expected_ids = {cid for cid, state in expected_by_id.items() if state in expected_states}

    items = await _get_list(client, auth_headers, params)

    returned_ids = {i["id"] for i in items}
    assert returned_ids == expected_ids, (
        f"Фильтр {params}: ожидались {len(expected_ids)} диалогов, пришло {len(returned_ids)}"
    )
    for item in items:
        assert item["deal_state"] in expected_states
        assert item["deal_state"] == expected_by_id[item["id"]]


@pytest.mark.asyncio
async def test_list_without_token_returns_401(client: AsyncClient):
    response = await client.get(CONVERSATIONS_URL)
    assert response.status_code == 401
