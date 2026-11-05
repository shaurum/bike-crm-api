# PLAN: вложения и голосовые по всем каналам + визуал по брендбуку (2026-10-29)

Как работать с планом: агент `coder` получает ровно один пункт и реализует только его. После него агент `tester` пишет и запускает тесты этого пункта. Если тесты падают, пункт возвращается к `coder` с конкретным указанием. Пункты выполняются по порядку. Главное в этой задаче — функционал (П1–П5), визуал (П6) — последним.

Окружение: docker-стек (`docker compose up -d` из корня), `./backend` смонтирован в `/app` контейнера `api`. Тесты: `docker compose exec -T api pytest tests/<файл> -q` (БД `bike_crm_test`, полный прогон ~4,5 мин — гонять только свои файлы, полный — в конце). После правок фронтенда: `docker compose restart frontend` и ждать `Ready` (HMR на Windows не видит изменений).

**Безопасность.** Celery локального стека ходит в боевой шлюз `gateway.vzuhandgo.ru`, в БД реальные переписки. В тестах и ручных проверках НЕЛЬЗЯ реально отправлять что-либо клиентам: все внешние вызовы (шлюз, `api.telegram.org`, Resend/SMTP, Авито) в тестах подменять (monkeypatch функций или `httpx.MockTransport`). Никаких вызовов `send_message` против реальных диалогов из основной БД.

## Что сейчас сломано (найдено при разборе)

1. `POST /conversations/{id}/messages` принимает `attachments: List[str]` и сохраняет `[{"url": …}]` — имя файла и тип теряются. В ленте исходящие файлы подписаны «Вложение», Telegram получает документ с именем `att-<hex>.pdf`.
2. Telegram (через шлюз и напрямую ботом): тип отправки выбирается только «картинка → sendPhoto, иначе sendDocument». Голосовые (`.ogg/.oga/.opus`) уходят документом, аудио/видео — документом.
3. Почта: в письмо добавляются относительные ссылки `/uploads/...` — у получателя они не открываются. Файлы не прикладываются.
4. Авито: в текст добавляются относительные ссылки, и они же передаются шлюзу в `media` — шлюз приписывает их ещё раз. Получатель видит две нерабочие ссылки.
5. Входящие голосовые из Telegram сохраняются с `content_type` из заголовка файлового сервера (часто `application/octet-stream`), в ленте показываются как скрепка без проигрывателя. Аудио/видео плеера в ленте нет вообще.
6. В CRM нельзя записать голосовое.
7. Визуал — дефолтная тема shadcn (синий primary, Inter, «Bike CRM»), не по брендбуку.

## П1. Метаданные вложений при отправке (backend)

Файлы: `backend/app/schemas/messaging.py`, `backend/app/api/v1/messages.py`, новый `backend/app/services/attachments.py`.

- В `schemas/messaging.py` добавить `AttachmentIn(BaseModel)`: `url: str`, `name: Optional[str]`, `content_type: Optional[str]`, `size: Optional[int]`. `MessageCreate.attachments: List[Union[AttachmentIn, str]]` — строки по-прежнему принимаются (обратная совместимость), нормализуются в `AttachmentIn(url=s)`.
- Новый модуль `services/attachments.py` — общие функции для всех каналов:
  - `resolve_upload(url) -> Optional[str]` — перенести сюда `_resolve_upload` из `messages.py` (защита от `../`, поддержка подпапок), в `messages.py` импортировать.
  - `public_url(url) -> Optional[str]` — полная ссылка через `settings.PUBLIC_BASE_URL` (перенести `_public_media_urls`, вернуть по одному URL; внешние `http(s)://` возвращать как есть). Части пути кодировать `urllib.parse.quote`.
  - `detect_kind(name, content_type) -> Literal["image","animation","voice","audio","video","document"]`: `.gif` → animation; прочие `image/*` и `.jpg .jpeg .png .webp` → image (`.heic` → document, Telegram его не показывает как фото); `.ogg .oga .opus` → voice; `.mp3 .m4a` и `audio/*` → audio; `.mp4 .mov` и `video/*` → video; иначе document.
  - `normalize_content_type(name, content_type)` — если тип пустой или `application/octet-stream`, брать `mimetypes.guess_type`, для `.oga/.opus/.ogg` — `audio/ogg`.
- В `send_message` каждое вложение: url обязан начинаться с `/uploads/messages/` и `resolve_upload` должен найти файл, иначе 400 «Вложение не найдено, загрузите файл заново». Имя/тип/размер берутся из запроса, тип нормализуется, размер при отсутствии — из файла. В `LeadMessage.attachments` сохраняется `{url, name, content_type, size}`, в `_deliver` передаётся этот же список.
- `upload_attachment`: файл сохранять как `/uploads/messages/att-<hex>/<safe_name>`, где `safe_name` — транслитерация имени в латиницу (простая таблица кириллицы в `attachments.py`), только `[A-Za-z0-9._-]`, не длиннее 80 символов, расширение — проверенное `ext`; пустое → `file<ext>`. Так Telegram и почтовые клиенты видят понятное имя файла. В ответе `name` — исходное имя, `content_type` — нормализованный. Добавить в `ALLOWED_UPLOAD_EXTS`: `.oga .opus .webm .mov`.
- Фронтенд в этом пункте не трогать (он шлёт строки — должно продолжать работать).

Критерии готовности:
- Отправка с `attachments=[{"url":…, "name":"Договор №5.pdf", "content_type":"application/pdf"}]` сохраняет все поля; отправка строкой тоже работает.
- Url вне `/uploads/messages/` или несуществующий файл → 400.
- Загрузка `Счёт март.pdf` возвращает `url` вида `/uploads/messages/att-<hex>/Schet_mart.pdf` и `name="Счёт март.pdf"`; файл реально лежит там.
- `detect_kind`/`normalize_content_type` покрыты табличным тестом.

## П2. Доставка вложений по каналам (backend)

Файлы: `backend/app/api/v1/messages.py` (`_deliver`, `_send_telegram_files`), `backend/app/services/mail.py`.

**Telegram напрямую ботом** (ветка без шлюза, `_send_telegram_files`): метод по `detect_kind`: image → `sendPhoto` (если файл > 10 МБ — `sendDocument`), animation → `sendAnimation`, voice → `sendVoice`, audio → `sendAudio`, video → `sendVideo`, document → `sendDocument`. Ключ поля совпадает с видом (`photo/animation/voice/audio/video/document`). Файл уходит multipart с исходным именем `name`. Если текст ≤ 1024 символов и вложение одно — текст уходит подписью (`caption`) этим же запросом, отдельного `sendMessage` нет; иначе как сейчас: текст, затем файлы.

**Telegram через шлюз**: `media` — полные ссылки (`public_url`). Если `PUBLIC_BASE_URL` пуст и есть вложения — не ставить в очередь ничего, вернуть замечание «Вложения не отправлены: в .env не задан PUBLIC_BASE_URL» (текст без файла не отправлять, чтобы менеджер не думал, что ушло всё). Если вложений нет — как сейчас.

**Почта**: `send_email(..., attachments: Optional[list[tuple[str, bytes, str]]] = None)` — `(имя, данные, тип)`. Resend: поле `attachments: [{"filename", "content": base64}]`. SMTP: `EmailMessage.add_attachment(data, maintype, subtype, filename=name)`. В `_deliver` для email читать файлы через `resolve_upload`; если суммарно > 20 МБ — не прикладывать, а добавить в текст полные ссылки (`public_url`); если и `PUBLIC_BASE_URL` пуст — вернуть замечание «Вложения слишком большие для письма и не отправлены». Тема письма — как сейчас.

**Авито**: API Авито в нашей интеграции умеет только текст. В текст добавлять ПОЛНЫЕ ссылки (`public_url`) с подписью имени: `«Договор.pdf: https://…»`. В шлюз `media` НЕ передавать (иначе шлюз дублирует ссылки). Если `PUBLIC_BASE_URL` пуст и есть вложения — ничего не отправлять, замечание «Вложения не отправлены: в .env не задан PUBLIC_BASE_URL».

**VK** — без изменений.

Критерии готовности (всё с подменой внешних вызовов):
- Telegram-бот: jpg → sendPhoto, gif → sendAnimation, ogg → sendVoice, mp3 → sendAudio, mp4 → sendVideo, pdf → sendDocument с именем `Договор №5.pdf`; один файл + короткий текст = один запрос с caption.
- Шлюз: `enqueue_outbound` получает полные https-ссылки; без `PUBLIC_BASE_URL` очередь не вызывается и `ok=false` с замечанием.
- Почта: Resend получает `attachments` с base64 и правильным `filename`; SMTP-сообщение содержит вложение; > 20 МБ → ссылки.
- Авито: текст содержит полные ссылки, `media` в шлюз не передаётся.

## П3. Шлюз: правильный метод Telegram для медиа

Файлы: `gateway/app/telegram.py` (`send_media`), `gateway/app/main.py` (`deliver_telegram`).

- `send_media` выбирает метод по расширению URL (без query): `.jpg .jpeg .png .webp` → sendPhoto; `.gif` → sendAnimation; `.ogg .oga .opus` → sendVoice; `.mp3 .m4a` → sendAudio; `.mp4 .mov` → sendVideo; иначе sendDocument.
- Если Telegram ответил ошибкой на sendPhoto/sendVoice/sendVideo (например, неподходящий формат) — один повтор через sendDocument, чтобы файл всё равно дошёл.
- Если в очереди один файл и текст ≤ 1024 символов — отправить текст подписью (`caption`) к файлу одним сообщением.
- Тесты: в `gateway/` тестов нет — добавить `gateway/tests/test_send_media.py` (pytest, `call` подменить). Запуск: `docker run --rm -v ${PWD}/gateway:/g -w /g python:3.11-slim sh -c "pip install -q -r requirements.txt pytest pytest-asyncio && pytest -q tests"` (или через образ шлюза, если собирается).
- Шлюз на боевом сервере обновляет пользователь сам (деплой не делать).

Критерии готовности: таблица «расширение → метод» покрыта тестом, повтор через sendDocument проверен, caption проверен.

## П4. Входящие медиа: типы и проигрыватели

Файлы: `backend/app/services/tg_media.py`, `frontend/src/app/(app)/messages/page.tsx`.

- `save_tg_file`: если тип из заголовка пустой или `application/octet-stream` — `normalize_content_type` по расширению; для `kind == "voice"` всегда `audio/ogg`, имя `Голосовое.ogg` (если нет своего). `extract_attachments` передаёт `kind` в `save_tg_file`.
- Фронтенд, лента: вложение рендерится по типу: image — как сейчас; audio (`audio/*` или `.ogg .oga .opus .mp3 .m4a .webm`-аудио) — `<audio controls preload="none">` шириной до 280px + имя/ссылка «скачать» мелко; video (`video/*`, `.mp4 .mov`) — `<video controls preload="metadata" class="max-h-60">`; прочее — как сейчас, скрепка + имя (у исходящих теперь настоящее имя из П1).

Критерии готовности: тест `save_tg_file` с подменённым httpx — voice с `application/octet-stream` сохраняется как `audio/ogg`; `tsc --noEmit` проходит; в браузере входящее голосовое (если есть в БД) играет.

## П5. Отправка из интерфейса: имена файлов, вставка, голосовые

Файлы: `frontend/src/app/(app)/messages/page.tsx`, `backend/app/api/v1/messages.py` (`upload_attachment`), `backend/Dockerfile`.

- Отправка шлёт объекты `{url, name, content_type, size}` (из ответа загрузки), а не строки.
- Черновые вложения показываются чипами с иконкой по типу, именем, размером и крестиком «убрать». Картинки — миниатюрой.
- Вставка из буфера (Ctrl+V картинки в поле ввода) и перетаскивание файлов на ленту загружают их так же, как кнопка-скрепка.
- Подсказка под полем ввода по каналу, если есть вложения: Авито — «В Авито файлы уходят ссылками»; почта — «Файлы приложатся к письму».
- **Голосовое**: кнопка-микрофон рядом со скрепкой, видна для канала `telegram`. Нажатие — запись через `MediaRecorder` (`audio/ogg;codecs=opus`, если `MediaRecorder.isTypeSupported`, иначе `audio/webm;codecs=opus`, иначе `audio/mp4`), во время записи — красная точка, таймер, кнопки «Стоп» и «Отмена»; лимит 5 минут. После «Стоп» файл грузится как `voice.<ext>` с полем формы `voice=1`, появляется в черновике как аудио-чип с проигрывателем; отправка — обычной кнопкой. Нет доступа к микрофону — тост с объяснением.
- Backend `upload_attachment(voice: bool = Form(False))`: если `voice` и файл не `.ogg/.oga/.opus` — перекодировать в OGG/Opus через ffmpeg (`ffmpeg -i in -c:a libopus -b:a 32k -ac 1 out.ogg`, `asyncio.create_subprocess_exec`, таймаут 60 с), сохранить `voice.ogg`, `content_type=audio/ogg`, имя «Голосовое.ogg». Ошибка ffmpeg → 422 «Не удалось обработать запись». В `backend/Dockerfile` (стадия base) добавить пакет `ffmpeg`; пересобрать `api`, `celery-worker`, `celery-beat`.

Критерии готовности: тест загрузки с `voice=1` и маленьким webm/opus (сгенерировать в тесте ffmpeg-ом `-f lavfi -i sine=d=1`) возвращает `.ogg` + `audio/ogg`, ffprobe показывает opus; `tsc --noEmit`; в браузере: вставка картинки, перетаскивание pdf, запись голосового (в браузере пейна может не быть микрофона — тогда проверить показ тоста), чипы с именами. Реальную отправку клиентам НЕ делать.

## П6. Визуал по брендбуку «ВЖУХ И ПОЕХАЛИ»

Источник: `F:\Seafile\ВЖУХ\Вжух и поехали\brandbook_vzhuh_i_poekhali.pdf`, логотип `F:\Seafile\ВЖУХ\Вжух и поехали\ВЖУХ И ПОЕХАЛИ_ Электровелосипед.png` (1983×793, почти белый фон).

Правила брендбука: жёлтый `#F5B91B` (акцент, кнопки действия, маркеры — дозированно, ~10%), графитовый чёрный `#111111` (заголовки, текст, логотип), белый фон (~70%). Кнопки действия — жёлтые с чёрным текстом. Шрифты: Unbounded (ExtraBold/Bold) — заголовки, Montserrat (Regular/Medium текст, SemiBold/Bold кнопки). Логотип не растягивать, без теней/обводок, не на пёстром фоне.

Это рабочий инструмент: плотность, читаемость и контраст важнее «рекламности». Unbounded — только для заголовков страниц и логотипной зоны, не для таблиц и форм.

- `frontend/src/app/globals.css`, светлая тема: `--primary: 43 92% 53%` (#F5B91B), `--primary-foreground: 0 0% 7%` (#111), `--foreground/--card-foreground/--popover-foreground: 0 0% 7%`, `--ring: 43 92% 53%`, `--secondary/--muted/--accent: 40 20% 96%` (тёплый светлый), `--accent-foreground: 0 0% 7%`, `--border/--input: 40 10% 88%`. Новый токен `--brand-soft: 45 100% 90%` (#FFF3CC) и в tailwind `brand-soft`. Тёмная тема: фон `0 0% 7%`, primary тот же жёлтый с чёрным текстом.
- Где `text-primary`/`bg-primary/..` использовался как синий для ссылок и текста (жёлтый текст на белом нечитаем) — заменить на `text-foreground` с подчёркиванием/жирностью или на `bg-brand-soft`. Пройти grep по `text-primary` во всём `frontend/src` и проверить каждый случай.
- Исходящие пузыри в чате: `bg-brand-soft text-foreground` вместо `bg-primary`; входящие — `bg-muted`. Плашка «Новые сообщения» и непрочитанные — чёрный/жёлтый маркер.
- Шрифты: локально через npm `@fontsource/montserrat` (400, 500, 600, 700) и `@fontsource/unbounded` (700, 800), импорт в `src/app/layout.tsx`; убрать `next/font/google` Inter (он же даёт таймауты Google Fonts в контейнере). В tailwind `fontFamily.sans = ["Montserrat", ...]`, `fontFamily.display = ["Unbounded", ...]`; заголовки страниц (`h1`) — `font-display`.
- Логотип: уменьшить PNG до ширины 480px (Pillow в контейнере api), сохранить `frontend/public/brand/logo.png`; в сайдбаре `app-shell.tsx` вместо «Bike CRM» — `<img src="/brand/logo.png" alt="ВЖУХ И ПОЕХАЛИ" class="h-9 w-auto">` на белом фоне. Иконка вкладки: вырезать из логотипа знак велосипеда (левая часть, примерно x 110–860) на квадрат с жёлтым фоном `#F5B91B` (так брендбук требует аватар), 64×64 и 180×180 → `frontend/src/app/icon.png`, `apple-icon.png`. `metadata.title` — «ВЖУХ CRM». Страница входа — логотип над формой.
- Кнопки `variant=default` — жёлтые с чёрным текстом автоматически через токены; `destructive` не трогать.

Критерии готовности: `tsc --noEmit`, `next build` без ошибок (или dev без ошибок в логах); в браузере проверены вход, сайдбар, /messages, /customers, /leads: жёлтый — только акценты и кнопки, текст читаемый, нет жёлтого текста на белом; скриншоты до/после.

## Финальная проверка

- Полный `pytest` в контейнере api, `alembic check` (схема не менялась), `tsc --noEmit`.
- Ручная проверка в браузере без реальной отправки клиентам.
- Отдельно сообщить пользователю: шлюз (П3) нужно задеплоить на `gateway.vzuhandgo.ru`; для вложений в Telegram/Авито на проде должен быть задан `PUBLIC_BASE_URL`; реальную доставку лучше проверить отправкой в свой собственный Telegram-чат.
