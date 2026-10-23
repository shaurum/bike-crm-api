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
| `GITHUB_TOKEN` в `.env` (для автообновления) | та же строка в `.env` | та же строка в `.env` |
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
6. дождётся ответа API и напечатает адреса;
7. запишет текущую версию (`.release_tag`) и проверит `GITHUB_TOKEN` в `.env`;
8. зарегистрирует **автообновление** в Планировщике заданий Windows
   (каждые 5 минут и при входе в систему — подробности ниже).
   Чтобы пропустить этот шаг: `setup-new-pc.ps1 -NoAutoUpdate`.

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
- Health (через nginx): http://localhost:3000/health
- API + Swagger напрямую (только с самого ПК): http://localhost:8000/docs
- Статус сервисов: значок колокольчика в сайдбаре CRM

---

## Шаг 5.1. Доступ из сети (другие ПК / интернет)

Единая точка входа — **порт 3000** (контейнер `bike-crm-nginx`):

| Путь | Куда идёт |
|------|-----------|
| `/`, страницы CRM | frontend |
| `/api/*`, `/uploads/*`, `/health` | backend |

Снаружи нужен **только порт 3000** — Keenetic/роутер перенаправляет на него,
nginx сам разруливает API и файлы. Порт 8000 наружу открывать не нужно.

1. Firewall (PowerShell от администратора, если ещё не открывали):
   ```powershell
   netsh advfirewall firewall add rule name="CRM-3000" dir=in action=allow protocol=TCP localport=3000
   ```
2. На Keenetic — перенаправление внешнего порта (например 443) на `192.168.1.10:3000`.
3. В `.env` обязательно:
   ```
   NEXT_PUBLIC_API_URL=
   ```
   (пусто = same-origin: браузер ходит API по тому же адресу, что и страница;
   при другом значении удалённый логин падает с «неверной парой» из-за CORS/mixed content).
4. Пересоздать контейнеры: `docker compose up -d --force-recreate frontend nginx`.

Проверка с любого ПК: `http://<адрес>:3000/health` → `{"status":"ok",...}`.

Если раньше открывали 8000 наружу — можно закрыть:
```powershell
netsh advfirewall firewall delete rule name="CRM-api-8000"
```

---

## Шаг 6. Проверка, что всё ок

```powershell
docker compose ps                 # все контейнеры Up/healthy
cd frontend
npx tsc --noEmit                  # проверка типов (должно быть пусто)
```

---

## Как работают обновления и деплой

Обновления раздаются через **GitHub Releases**: версия = тег `v*` в репозитории.
Push тега запускает Actions (`.github/workflows/release.yml`) — создаётся Release
с zip-архивом исходников (без `.env` и `data/`). Скрипты автообновления
(`scripts/auto-update.ps1` на Windows, `scripts/auto-update.sh` на VPS)
каждые 5 минут (VPS — каждую минуту) сверяют последний релиз с установленной
версией (файл `.release_tag`); при расхождении скачивают zip, раскладывают
файлы, собирают образы, применяют миграции и перезапускают стек.

- **Как выпустить обновление**: слить в `main` → поставить и запушить тег:
  ```powershell
  git tag v1.1.0
  git push origin v1.1.0
  ```
  Все ПК с автообновлением подхватят его в течение 5 минут.
- **Галка режима** в CRM: **Настройки → Обновление** → «Авто» (ставить сразу)
  или «Вручную» (только по кнопке «Проверить и установить»). Кнопка
  «Проверить обновления сейчас» устанавливает доступную версию немедленно
  в обоих режимах.
- **Защита от порчи рабочей копии**: если в копии есть несcommitted правки —
  автообновление не применяется (видно в CRM: «есть локальные изменения»);
  принудительно: `scripts\auto-update.ps1 -Apply` (правки сотрутся!).
- **Токен**: в `.env` нужен `GITHUB_TOKEN` — Fine-grained PAT с доступом к
  `shaurum/bike-crm-api`, Contents: Read-only (иначе скрипт не скачает zip).
- **Откат**: удалить/закрыть битый тег и выпустить предыдущий тег заново.
- **Прод (VPS)**: та же схема по тегу; push тега дополнительно дёргает
  `scripts/auto-update.sh` по SSH (`.github/workflows/deploy.yml`), обычно
  VPS подхватывает сам по cron.
- Сервер: `31.56.197.234` (SSH-ключ `bike_crm_gateway`),
  шлюз интеграций: https://gateway.vzuhandgo.ru

---

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| `port is already allocated` | порт занят другим процессом: `netstat -ano \| findstr :3000` → остановить конфликтующее приложение |
| Docker не запускается | включить WSL2: `wsl --set-default-version 2`, перезагрузить ПК, запустить Docker Desktop от админа |
| `docker compose` пишет про старый синтаксис | обновить Docker Desktop (compose v2 входит в комплект) |
| Фронтенд отдаёт старые страницы | `docker compose restart frontend` |
| Бэкенд не подхватил правки | `docker compose restart api` (код смонтирован volume’ом, рестарт обязателен) |
| Не проходит `git push` | войти в GitHub: `git config --global credential.helper manager` |
