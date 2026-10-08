# Настройка нового (рабочего) ПК

Пошаговая инструкция для чистой Windows-машины: как развернуть проект локально.
На рабочем ПК ничего не установлено — начинаем с нуля.

---

## Шаг 1. Установить программы (один раз)

Открыть PowerShell **от имени администратора**:

```powershell
# Git
winget install --id Git.Git -e --source winget

# WSL2 (нужен Docker Desktop)
wsl --install
# (перезагрузка ПК после этого)

# Docker Desktop
winget install --id Docker.DockerDesktop -e --source winget

# Node.js LTS (для проверки типов: npx tsc)
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

Если `winget` недоступен — скачать установщики вручную:
- https://git-scm.com/download/win
- https://www.docker.com/products/docker-desktop/
- https://nodejs.org

**После установки — перезагрузить ПК**, затем запустить Docker Desktop и дождаться
значка в трее (Engine running).

> Python не нужен: бэкенд и скрипты работают внутри Docker.

---

## Шаг 2. Клонировать репозиторий

Репозиторий **приватный** — при клонировании откроется окно авторизации GitHub
(или используйте Personal Access Token).

```powershell
mkdir C:\Github            # если ещё нет
cd C:\Github
git clone https://github.com/shaurum/bike-crm-api.git
cd bike-crm-api
```

---

## Шаг 3. Перенести секреты со старого ПК

`.env` **не хранится в git** — его нужно скопировать вручную с этого (старого) ПК:

| Что | Откуда (старый ПК) | Куда (новый ПК) |
|-----|--------------------|-----------------|
| `.env` (обязательно) | `F:\Github\bike-crm-api\.env` | `C:\Github\bike-crm-api\.env` |
| SSH-ключ доступа к серверу (опционально) | `%USERPROFILE%\.ssh\bike_crm_gateway` | `%USERPROFILE%\.ssh\bike_crm_gateway` |
| SSH-ключи деплоя (опционально) | `%USERPROFILE%\.ssh\deploy_github`, `deploy_actions` | туда же |

Если `.env` пока некуда взять — положите шаблон:

```powershell
copy .env.example .env
```

Работать будет всё, кроме внешних интеграций (Авито, Telegram, Email) — они
включатся после заполнения секретов в `.env`.

---

## Шаг 4. Запуск (скрипт)

```powershell
cd C:\Github\bike-crm-api
powershell -ExecutionPolicy Bypass -File scripts\setup-new-pc.ps1
```

Скрипт сам:
1. проверит, что Git/Docker установлены и Docker запущен;
2. подложит `.env` (если его нет — скопирует из `.env.example`);
3. проверит, что порты 3000/8000/5433/6380 свободны;
4. соберёт и поднимет весь стек (`docker compose up -d --build`);
5. прогонит миграции БД (`alembic upgrade head`);
6. дождётся ответа API и напечатает адреса.

### Запуск вручную (если не хочется скрипт)

```powershell
cd C:\Github\bike-crm-api
docker compose up -d --build
docker compose exec -T api alembic upgrade head
docker compose ps
```

---

## Шаг 5. Первый вход

1. Открыть **http://localhost:3000**
2. Зарегистрироваться: **http://localhost:3000/register**
   - на свежей базе **первый зарегистрированный пользователь = админ**
     (регистрируйтесь сразу правильным e-mail, например `shaurum@mail.ru`);
   - далее регистрация закрыта — новых сотрудников заводите через
     пригласительные ссылки в разделе **Пользователи**.
3. Логин: http://localhost:3000/login

Полезные адреса:
- Админка: http://localhost:3000
- API + Swagger: http://localhost:8000/docs
- Статус сервисов: значок колокольчика в сайдбаре CRM

---

## Шаг 6. Проверка, что всё ок

```powershell
docker compose ps                 # все контейнеры Up/healthy
cd frontend
npx tsc --noEmit                  # проверка типов (должно быть пусто)
```

---

## Как работают обновления и деплой

- **Локальная разработка**: меняете код → `git add/commit/push` в `main`.
- **Прод (VPS)**: после push срабатывает GitHub Actions
  (`.github/workflows/deploy.yml`) → на сервере
  `scripts/auto-update.sh` подтягивает код, собирает и поднимает стек;
  в CRM: **Настройки → Обновление** (версия, «Проверить обновления сейчас»).
  Тот же скрипт крутится там по cron каждую минуту.
- Сервер: `31.56.197.234` (SSH-ключ `bike_crm_gateway`),
  шлюз интеграций: https://gateway.vzuhandgo.ru

---

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| `port is already allocated` | порт занят другим процессом: `netstat -ano \| findstr :3000` → остановить конфликтующее приложение или изменить `FRONTEND_PORT` в `.env` |
| Docker не запускается | включить WSL2: `wsl --set-default-version 2`, перезагрузить ПК, запустить Docker Desktop от админа |
| `docker compose` пишет про старый синтаксис | обновить Docker Desktop (compose v2 входит в комплект) |
| Фронтенд отдаёт старые страницы | `docker compose restart frontend` |
| Бэкенд не подхватил правки | `docker compose restart api` (код смонтирован volume’ом, рестарт обязателен) |
| Не проходит `git push` | войти в GitHub: `git config --global credential.helper manager` |
