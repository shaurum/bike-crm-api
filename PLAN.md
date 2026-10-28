# PLAN: исправления по итогам проверки стека (2026-10-27)

Как работать с планом: агент `coder` получает ровно один пункт и реализует только его. После него агент `tester` пишет и запускает тесты этого пункта. Если тесты падают, пункт возвращается к `coder` с конкретным указанием. Пункты выполняются строго по порядку: П1 нужен для тестов всех остальных.

Окружение: всё запускается внутри docker-стека, который уже поднят.
- Бэкенд: `docker compose exec -T api <cmd>` (каталог `./backend` смонтирован в `/app`, в образе уже есть pytest, pytest-asyncio, httpx и ruff).
- Фронтенд: `docker compose exec -T frontend <cmd>`.
- Postgres внутри сети доступен как `postgres:5432`, пользователь `bike_crm`.

Общие правила:
- Не трогать `.env`, `data/`, `docker-compose.yml`, если пункт этого не требует явно.
- Ничего не коммитить.
- Не отправлять сообщения во внешние каналы (Telegram, почта, Авито).
- Бизнес-логику вне пункта не менять.
- Стиль кода как в соседних файлах: комментарии и сообщения об ошибках по-русски, типы через `Optional`/`List`, как в проекте.

---

## П1. Инфраструктура тестов бэкенда (pytest + отдельная тестовая БД)

**Зачем:** `backend/tests/` пуст. Пункты П3 и П4 проверяются тестами API.

**Модули:**
- `backend/tests/__init__.py`: пустой.
- `backend/tests/conftest.py`: фикстуры, описанные ниже.
- `backend/tests/test_smoke.py`: smoke-тесты.

**Интерфейс фикстур (их будут использовать следующие пункты):**

| Фикстура | Что даёт |
|---|---|
| `db_session` (async, function) | `AsyncSession` к тестовой БД. После теста все таблицы очищаются (`TRUNCATE ... RESTART IDENTITY CASCADE` по `Base.metadata.sorted_tables`). |
| `client` (async, function) | `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. `get_db` переопределён через `app.dependency_overrides`, чтобы отдавать сессию к тестовой БД. |
| `admin_user` (async) | Созданный в БД `User` с ролью администратора (`UserRole`), `is_active=True`, паролем через `app.core.security.get_password_hash`. |
| `auth_headers` (async) | `{"Authorization": f"Bearer {token}"}`, где токен получен через `app.core.security.create_access_token` в том же формате, что и в `/auth/login` (`backend/app/api/v1/auth.py`). |

**Требования к реализации:**
- Тестовая БД `bike_crm_test` на том же сервере. В самом верху `conftest.py`, до любого импорта `app.*`, выставить `os.environ["POSTGRES_DB"] = "bike_crm_test"`, чтобы `settings.DATABASE_URL` и глобальный `engine` смотрели в тестовую БД. **Боевую БД `bike_crm` тесты не должны трогать ни при каких условиях.** Добавить assert, что в URL тестового движка указана `bike_crm_test`.
- Если БД `bike_crm_test` нет, создать её: подключиться через asyncpg к БД `postgres` и выполнить `CREATE DATABASE`.
- Схему создавать один раз на сессию через `app.models.Base.metadata.create_all` и удалять в конце через `drop_all`. Использовать именно `app.models.Base`, а не `app.core.database.Base`: у последнего пустая metadata.
- Чтобы не было ошибок «attached to a different loop» с pytest-asyncio 0.23: движки тестов создавать с `poolclass=NullPool`. Создание и удаление схемы на уровне сессии делать синхронной фикстурой через `asyncio.run(...)`.
- Lifespan приложения (`init_db`) в тестах не запускать: ASGITransport не вызывает lifespan, и этого достаточно.
- Celery-задачи и внешние HTTP-вызовы в smoke-тестах не вызываются.
- **Зависимость:** закреплённая `pytest-asyncio==0.23.3` несовместима с `pytest==8.2.2` (падает с `'Package' object has no attribute 'obj'` и `'FixtureDef' object has no attribute 'unittest'`). Поднять до `pytest-asyncio==0.23.8` в `backend/requirements.txt` и в extras `dev` файла `backend/pyproject.toml`. В запущенный контейнер поставить через `docker compose exec -T api pip install pytest-asyncio==0.23.8`. Остальные версии не менять.

**Smoke-тесты (`test_smoke.py`):**
1. `GET /health` → 200, `{"status": "ok", ...}`.
2. `GET /api/v1/auth/me` без токена → 401.
3. `GET /api/v1/auth/me` с `auth_headers` → 200, email совпадает с `admin_user`.
4. `POST /api/v1/auth/login` (form-data `username`/`password`) с неверным паролем → 401; с верным → 200 и `access_token` в ответе.

**Критерии готовности:**
- `docker compose exec -T api pytest` проходит, 4 теста зелёные, 3 запуска подряд без флаков.
- После прогона в БД `bike_crm` ничего не изменилось. Проверка: `SELECT count(*) FROM "user"` до и после совпадает.

---

## П2. Конфиг ruff

**Проблема:** `backend/pyproject.toml`, секция `[tool.ruff]`, содержит несуществующий селектор `QCS`. Из-за этого ruff 0.4.8 падает на разборе конфига.

**Изменения:**
- Убрать `QCS`. Проверить, что ruff 0.4.8 знает все остальные селекторы из `select` и `ignore`, неизвестные убрать.
- Перенести `select`/`ignore` в `[tool.ruff.lint]`: в 0.4.x старое расположение даёт deprecation-предупреждение. `target-version` и `line-length` оставить в `[tool.ruff]`.
- Сами нарушения в коде **не исправлять**: это отдельная задача.

**Критерии готовности:**
- `docker compose exec -T api ruff check app --statistics` отрабатывает без ошибки разбора конфига и без предупреждений о deprecated-настройках. Код выхода 0 или 1 (найдены нарушения) допустим, 2 нет.
- `ruff format --check app` тоже не падает на конфиге.
- В отчёте coder привести итоговую статистику нарушений.

---

## П3. Метки сделки в «Сообщениях»

**Проблема:** `_deal_state()` (`backend/app/api/v1/messages.py`) возвращает `"active"` для любого открытого лида (`new`, `contacted`, `qualified`, `booking`), а фронтенд подписывает его «В аренде». Выигранная (`won`) и проигранная (`lost`) сделки обе попадают в `"deal_closed"` → «Сделки нет».

**Новый контракт поля `deal_state`:** `"active" | "won" | "lost" | "none"`.

| Значение | Когда | Подпись в UI | Стиль бейджа |
|---|---|---|---|
| `active` | лид в `NEW/CONTACTED/QUALIFIED/BOOKING` | «В работе» | синий (`bg-blue-100 text-blue-800`) |
| `won` | лид в `WON` | «Сделка заключена» | зелёный (как сейчас у active) |
| `lost` | лид в `LOST` | «Отказ» | янтарный (как сейчас у deal_closed) |
| `none` | у диалога нет лида | «Нет сделки» | серый (как сейчас) |

**Бэкенд (`backend/app/api/v1/messages.py`, `backend/app/schemas/messaging.py`):**
- `_deal_state(lead)` возвращает значения по таблице выше.
- `status_filter` в `GET /api/v1/conversations`:
  - `active`: только `active`;
  - `closed`: всё, кроме `active` (`won`, `lost`, `none`);
  - отсутствие параметра или `all`: всё.
- Обновить `description` поля `deal_state` в схемах (строки ~53 и ~98).
- Найти по коду все остальные места, которые сравнивают с `"deal_closed"`, и перевести их на новый контракт.

**Фронтенд (`frontend/src/app/(app)/messages/page.tsx`):**
- Тип `deal_state` (строки ~36 и ~82) → `"active" | "won" | "lost" | "none"`.
- `DEAL_LABELS` и `DealBadge` по таблице.
- Вкладки фильтра: `{ key: "active", label: "В работе" }`, `{ key: "closed", label: "Закрытые" }`; ключи API не меняются.
- Блок «Завершённая сделка сохранена в истории…» (около строки 1109) показывать при `won` или `lost`.

**Критерии готовности:**
- Тесты (`backend/tests/test_conversations.py`, пишет tester на фикстурах П1): для каждого из 6 статусов лида и для диалога без лида `deal_state` в `GET /api/v1/conversations` соответствует таблице. Фильтры `active` и `closed` возвращают ровно ожидаемые диалоги.
- `docker compose exec -T frontend npx tsc --noEmit` проходит.
- В браузере на `/messages` нет надписи «В аренде».

---

## П4. Валидация даты рождения клиента

**Проблема:** `birth_date` в схемах клиента (`backend/app/schemas/rental.py`, строки ~230 и ~253) ничем не ограничена. В БД уже лежит `1299-11-21`, карточка показывает «726 лет».

**Бэкенд:**
- Общий валидатор `field_validator("birth_date")` (pydantic v2) для схем создания и обновления клиента. Разрешено `None` или дата в диапазоне `[1900-01-01, сегодня]`. Иначе `ValueError("Дата рождения должна быть между 01.01.1900 и сегодняшним днём")` → API отвечает 422.
- Минимальный возраст **не** проверять: это бизнес-правило, ограничение по возрасту задаётся в реквизитах.
- Проверить, есть ли `birth_date` в других входящих схемах (например, при распознавании паспорта или в публичном виджете бронирования), и навесить туда тот же валидатор.

**Фронтенд:**
- У всех полей ввода даты рождения клиента (как минимум `frontend/src/components/customers/customer-create-dialog.tsx`, а также формы редактирования, если найдутся) выставить `min="1900-01-01"` и `max` = сегодняшняя дата в формате `YYYY-MM-DD`.

**Данные:** существующую запись с 1299 годом **не** трогать. Чтение старых некорректных данных не должно ломаться: валидатор стоит только на входящих схемах, не на response-схемах.

**Критерии готовности:**
- Тесты (`backend/tests/test_customers.py`):
  - создание клиента с `birth_date` = `1299-11-21`, завтрашней датой или `1899-12-31` → 422;
  - с `1990-05-01`, сегодняшней датой и `null` → успех;
  - то же для обновления клиента;
  - GET клиента с уже записанной в БД датой `1299-11-21` (вставить напрямую через `db_session`) → 200.
- `npx tsc --noEmit` проходит.

---

## П5. `devIndicators` в Next.js 14.1

**Проблема:** `frontend/next.config.js` содержит `devIndicators: false`. В Next 14.1 это поле — объект, поэтому при старте выводится «Invalid next.config.js options detected», а индикатор не скрывается.

**Изменение:** `devIndicators: { buildActivity: false }`. Комментарий над полем сохранить.

**Критерии готовности:**
- После `docker compose restart frontend` в `docker compose logs frontend` нет строки `Invalid next.config.js options`.
- `/` и `/login` через `http://localhost:3000` отвечают 200.

---

## П6. Дрейф схемы БД и моделей (`alembic check`)

**Текущее расхождение** (`docker compose exec -T api alembic check`):
- 396 `modify_comment`: в моделях есть `comment=`, в БД комментариев нет;
- 172 `modify_default`: в БД есть server default из миграций, в моделях только Python-default;
- 24 `modify_type` на 12 колонках: в БД нативные PG ENUM (например `bike_status_enum`), в моделях `SQLEnum(..., native_enum=False)`. Колонки: `bike.status`, `booking.status`, `customer.document_type`, `customer_document.kind`, `document.kind`, `document.status`, `lead.status`, `lead_source.type`, `task.priority`, `task.status`, `task.type`, `user.role`;
- 5 `remove_index`: индексы есть в БД, но не объявлены в моделях (`ix_contact_point_channel_value`, `ix_contact_point_external_id`, `ix_conversation_last_message`, `ix_customer_birth_date`, `ix_integration_setting_name`);
- 1 `add_index`: `ix_customer_full_name` объявлен в модели, но в БД его нет.

**Принцип:** источник правды — фактическая схема БД. Модели подгоняются под неё. Миграция только **добавляет** то, чего не хватает: комментарии и индекс. Ничего не удаляет и не меняет типы колонок.

**Изменения:**
1. **Enum-ы.** Для каждой из 12 колонок узнать имя PG-типа (`SELECT ... FROM pg_type t JOIN pg_enum e ...`, или `\d+ <table>` в psql) и привести модель к виду `SQLEnum(<PyEnum>, name="<имя_типа_в_БД>", values_callable=lambda x: [m.value for m in x])` (нативный enum, `native_enum=False` убрать). Списки значений в БД и в модели должны совпадать. Если не совпадают, остановиться и описать расхождение, не додумывать.
2. **Индексы.** Добавить 5 недостающих индексов в `__table_args__` соответствующих моделей. Определения (колонки, unique, `postgresql_where`) скопировать из миграции, где индекс создавался (`grep -rn "<имя индекса>" backend/alembic/versions`).
3. **Server defaults.** В `backend/alembic/env.py` (обе функции, offline и online) заменить `compare_server_default=True` на функцию сравнения, которая возвращает `False` (считать равными), если у колонки модели нет `server_default`. В остальных случаях она возвращает `None`, то есть отдаёт решение стандартному сравнению alembic. Server default в БД остаются как есть.
4. **Миграция** `backend/alembic/versions/20261027_1200_sync_comments_and_indexes.py`, `down_revision = "20261026_1200"`:
   - `upgrade`: проставить комментарии к колонкам из моделей (`op.alter_column(..., comment=...)` или `COMMENT ON COLUMN`) и создать `ix_customer_full_name`;
   - `downgrade`: удалить `ix_customer_full_name` и снять комментарии (`comment=None`).
   - Удобно сгенерировать через `alembic revision --autogenerate` после шагов 1–3, а затем проверить вручную, что в файле нет `drop_*`, `alter_column(type_=...)` и `server_default=`.
5. **Перед применением** сделать бэкап: `docker compose exec -T postgres pg_dump -U bike_crm bike_crm | gzip > backend/backups/before_20261027_1200.sql.gz`. Потом `alembic upgrade head`.

**Критерии готовности:**
- `docker compose exec -T api alembic check` → `No new upgrade operations detected.`
- `alembic downgrade -1` и затем `alembic upgrade head` проходят без ошибок, после этого `alembic check` снова чистый.
- `docker compose restart api celery-worker celery-beat`: `GET http://localhost:3000/health` → 200, в логах api и worker нет новых ошибок за 2 минуты.
- `pytest` (все тесты П1, П3, П4) зелёный: тестовая БД создаётся из моделей с нативными enum-ами.
- Ручная проверка в API (tester): `GET /api/v1/bikes`, `/api/v1/leads`, `/api/v1/tasks`, `/api/v1/customers` с токеном тестового админа на **тестовой** БД отвечают 200. Enum-колонки читаются и пишутся: тест создаёт задачу и лид со статусами и читает их обратно.

---

## Итоговая проверка (выполняет основная сессия)
- `pytest`: всё зелёное.
- `ruff check app` не падает на конфиге.
- `alembic check`: дрейфа нет.
- Фронтенд: `tsc` проходит, `Invalid next.config.js` в логах нет.
- В браузере (localhost:3000) открываются `/messages` с новыми метками и фильтрами и `/customers`. Отправка сообщений и сохранение форм с реальными данными не выполняются.
