# Bike CRM — Админка проката электробайков

> CRM-система для управления прокатом электробайков: флит, бронирование, воронка лидов (Авито, ВК, Telegram, Email), виджет бронирования, генерация договоров, таск-менеджмент.

## 🏗 Архитектура

| Компонент | Технология | Порт (localhost) |
|-----------|------------|------------------|
| **API** | FastAPI + SQLAlchemy 2.0 + Alembic | 8000 |
| **Админка** | Next.js 14 + TypeScript + Tailwind + shadcn/ui | 3000 |
| **Виджет** | React + Vite (деплой на GitHub Pages) | 5173 (dev) |
| **БД** | PostgreSQL 16 | 5432 |
| **Кэш/Очереди** | Redis 7 | 6379 |
| **Асинк задачи** | Celery + Redis | — |

## 🚀 Быстрый старт (Windows 11 + Docker Desktop)

### Предварительные требования
- Windows 11 Pro/Enterprise (WSL2 включён)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) с WSL2 backend
- 8+ GB RAM (рекомендуется 16 GB)
- Git, VS Code

### 1. Клонирование и настройка
```powershell
cd F:\Github\ВЖУХ и поехали
# Скопируйте .env.example в .env и при необходимости измените пароли
copy .env.example .env
```

### 2. Запуск инфраструктуры (БД + Redis)
```powershell
docker compose up -d postgres redis
```

Проверить статус:
```powershell
docker compose ps
# Должно показать: bike-crm-postgres (healthy), bike-crm-redis (healthy)
```

### 3. Запуск Backend (после реализации)
```powershell
docker compose up -d api celery-worker celery-beat
```
API будет доступен: http://localhost:8000
Swagger UI: http://localhost:8000/docs

### 4. Запуск Frontend (после реализации)
```powershell
docker compose up -d frontend
```
Админка: http://localhost:3000

### 5. Полный стек одной командой (после реализации всех сервисов)
```powershell
docker compose up -d
```

### 6. Остановка
```powershell
docker compose down
# С удалением данных (осторожно!):
# docker compose down -v
```

## 📁 Структура проекта

```
.
├── .github/workflows/      # CI/CD (GitHub Actions)
├── backend/                # FastAPI приложение
│   ├── app/
│   │   ├── api/           # Роутеры (webhooks, public, admin)
│   │   ├── core/          # Config, security, database
│   │   ├── models/        # SQLAlchemy модели
│   │   ├── schemas/       # Pydantic схемы
│   │   ├── services/      # Бизнес-логика
│   │   ├── tasks/         # Celery задачи
│   │   └── main.py
│   ├── alembic/           # Миграции БД
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/               # Next.js админка
│   ├── src/
│   │   ├── app/           # App Router страницы
│   │   ├── components/    # UI компоненты
│   │   ├── lib/           # API клиент, утилиты
│   │   └── hooks/
│   ├── Dockerfile
│   └── package.json
├── nginx/                  # Nginx конфиг для продакшена
├── scripts/                # Скрипты деплоя и бэкапов
├── docker-compose.yml      # Локальная разработка
├── docker-compose.prod.yml # Продакшн (VPS)
├── .env.example
└── README.md
```

## 🗄 Миграции БД (Alembic)

```powershell
# Создать миграцию
docker compose exec api alembic revision --autogenerate -m "описание изменений"

# Применить миграции
docker compose exec api alembic upgrade head

# Откатить последнюю
docker compose exec api alembic downgrade -1

# История
docker compose exec api alembic history
```

## 🔧 Полезные команды

```powershell
# Логи сервисов
docker compose logs -f api
docker compose logs -f postgres

# Shell в контейнере
docker compose exec api bash
docker compose exec postgres psql -U bike_crm -d bike_crm

# Бэкап БД
docker compose exec postgres pg_dump -U bike_crm bike_crm | gzip > backups/db_$(date +%F_%H-%M).sql.gz

# Восстановление БД
gunzip -c backups/db_2026-01-15_03-00.sql.gz | docker compose exec -T postgres psql -U bike_crm -d bike_crm
```

## 🌿 Git Flow

- `main` — стабильная версия (deploy → production)
- `develop` — интеграционная ветка
- `feature/*` — новые фичи
- `fix/*` — багфиксы
- `release/*` — подготовка релиза

## 📦 Деплой на VPS (Продакшн)

```powershell
# На VPS (Ubuntu 22.04):
# 1. Установить Docker + Docker Compose
# 2. Настроить .env.prod (на основе .env.example)
# 3. Запустить:
docker compose -f docker-compose.prod.yml up -d
```

CI/CD настроен через GitHub Actions: пуш в `main` → билд образов → деплой на VPS по SSH.

## 🔐 Переменные окружения

Все секреты в `.env` (не коммитится в git). См. `.env.example` для списка переменных.

### Критичные для продакшена:
- `SECRET_KEY` — 64+ случайных символов
- `JWT_SECRET_KEY` — 64+ случайных символов
- `POSTGRES_PASSWORD` — сложный пароль
- `AVITO_CLIENT_ID/SECRET` — из партнёрки Авито
- `VK_CLIENT_ID/SECRET` — из настройки группы ВК
- `TELEGRAM_BOT_TOKEN` — от @BotFather
- `RESEND_API_KEY` / `SENDGRID_API_KEY` — для email
- `S3_*` — для бэкапов и файлов

## 🧪 Тестирование

```powershell
# Backend
docker compose exec api pytest -v
docker compose exec api pytest --cov=app --cov-report=html

# Frontend
docker compose exec frontend npm run test
docker compose exec frontend npm run test:e2e

# Линтеры
docker compose exec api ruff check .
docker compose exec api mypy app/
docker compose exec frontend npm run lint
```

## 📚 Документация API

После запуска API:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## 🐛 Известные проблемы на Windows

1. **Права доступа к volumes** — если ошибки доступа к `./data/postgres`:
   ```powershell
   icacls "F:\Github\ВЖУХ и поехали\data" /grant "Everyone:(OI)(CI)F" /T
   ```

2. **Порты заняты** — проверьте `netstat -ano | findstr :5432` и остановите конфликтующие процессы.

3. **WSL2 память** — в `.wslconfig` (в `%UserProfile%`):
   ```
   [wsl2]
   memory=6GB
   processors=4
   ```

## 📄 Лицензия

MIT — на базе [RentInfra](https://github.com/j4b3r/rentinfra) (MIT).

---

**Статус:** Инициализация репозитория (Спринт 1, коммиты 1-2)