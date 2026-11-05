#!/usr/bin/env bash
# Автообновление CRM на VPS из GitHub Releases (не через git pull).
# Cron: * * * * * /opt/bike-crm/scripts/auto-update.sh >> /var/log/bike-crm-update.log 2>&1
#
# GITHUB_TOKEN берётся из /opt/bike-crm/.env (Fine-grained PAT, Contents: Read).
# Режим: backend/.update_mode = auto (по умолчанию) | manual.
#   manual: ставит обновление только по кнопке «Проверить и установить» в CRM
#   (файл backend/.update_requested).
# В backend/.update_requested может лежать тег (например v1.1.4) — тогда ставится
# именно эта версия: так работает выбор версии и откат.
# Состояние пишет в backend/.update_state.json — его читает API (/api/v1/system/version):
# кроме версии там этап установки, прогресс, процент скачивания и ошибка.
set -uo pipefail

REPO_DIR="/opt/bike-crm"
STATE_FILE="$REPO_DIR/backend/.update_state.json"
JOB_FILE="$REPO_DIR/backend/.update_job"
REQUEST_FILE="$REPO_DIR/backend/.update_requested"
MODE_FILE="$REPO_DIR/backend/.update_mode"
LOG_FILE="$REPO_DIR/backend/.update.log"
TAG_FILE="$REPO_DIR/.release_tag"
LOCK_FILE="/tmp/bike-crm-update.lock"
REPO_API="https://api.github.com/repos/shaurum/bike-crm-api"
ACTIVE_STAGES=" checking downloading extracting copying building migrating restarting "

cd "$REPO_DIR" 2>/dev/null || exit 0
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

# В stdout для cron и в файл, который CRM показывает в журнале
log() {
    local line
    line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$line"
    echo "$line" >>"$LOG_FILE" 2>/dev/null || true
}

now_utc() { date -u +%FT%TZ; }

read_env() { # $1: имя переменной
    [ -f "$REPO_DIR/.env" ] || return 1
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$REPO_DIR/.env" |
        head -n1 | tr -d '"'"'"'[:space:]'
}

read_mode() {
    local mode=""
    [ -f "$MODE_FILE" ] && mode="$(tr -d '[:space:]' <"$MODE_FILE")"
    case "$mode" in auto|manual) echo "$mode" ;; *) echo "auto" ;; esac
}

current_tag() {
    [ -f "$TAG_FILE" ] && tr -d '[:space:]' <"$TAG_FILE" || true
}

requested_tag() { # «1» или пусто — последняя версия; тег — конкретная
    local req=""
    [ -f "$REQUEST_FILE" ] && req="$(tr -d '[:space:]' <"$REQUEST_FILE")"
    if echo "$req" | grep -Eq '^v[0-9A-Za-z._-]+$'; then echo "$req"; fi
}

# Сведения о последней установке переживают холостые запуски по расписанию
JOB_STAGE="idle"; JOB_PROGRESS=0; JOB_TARGET=""; JOB_STARTED=""; JOB_FINISHED=""
JOB_ERROR=""; JOB_DL_PERCENT=""; JOB_DL_BYTES=""; JOB_DL_TOTAL=""
LATEST_TAG=""

save_job() {
    cat >"$JOB_FILE" <<EOF
JOB_STAGE=$JOB_STAGE
JOB_PROGRESS=$JOB_PROGRESS
JOB_TARGET=$JOB_TARGET
JOB_STARTED=$JOB_STARTED
JOB_FINISHED=$JOB_FINISHED
JOB_ERROR=$JOB_ERROR
JOB_DL_PERCENT=$JOB_DL_PERCENT
JOB_DL_BYTES=$JOB_DL_BYTES
JOB_DL_TOTAL=$JOB_DL_TOTAL
EOF
}

restore_job() {
    [ -f "$JOB_FILE" ] || return 0
    local key value
    while IFS='=' read -r key value; do
        case "$key" in
            JOB_STAGE) JOB_STAGE="$value" ;;
            JOB_PROGRESS) JOB_PROGRESS="${value:-0}" ;;
            JOB_TARGET) JOB_TARGET="$value" ;;
            JOB_STARTED) JOB_STARTED="$value" ;;
            JOB_FINISHED) JOB_FINISHED="$value" ;;
            JOB_ERROR) JOB_ERROR="$value" ;;
            JOB_DL_PERCENT) JOB_DL_PERCENT="$value" ;;
            JOB_DL_BYTES) JOB_DL_BYTES="$value" ;;
            JOB_DL_TOTAL) JOB_DL_TOTAL="$value" ;;
        esac
    done <"$JOB_FILE"
    case "$ACTIVE_STAGES" in
        *" $JOB_STAGE "*)
            # Лок свободен, а этап «в процессе» — прошлый запуск оборвался
            JOB_ERROR="установка прервана: скрипт остановился на этапе «$JOB_STAGE»"
            JOB_STAGE="error"
            JOB_FINISHED="$(now_utc)"
            save_job
            ;;
    esac
}

json_str() { # строка или null; наши тексты без кавычек и обратных слешей
    if [ -n "$1" ]; then printf '"%s"' "$1"; else printf 'null'; fi
}

json_num() {
    if [ -n "$1" ]; then printf '%s' "$1"; else printf 'null'; fi
}

write_state() { # $1: true|false (updating), $2: примечание, $3: latest_tag, $4: true|false (update_available)
    local updating="$1" note="$2" latest_tag="$3" avail="$4"
    local local_sha="" local_date=""
    if git rev-parse --git-dir >/dev/null 2>&1; then
        local_sha="$(git rev-parse --short HEAD)"
        local_date="$(git log -1 --format=%cI)"
    fi
    mkdir -p "$REPO_DIR/backend"
    cat >"$STATE_FILE.tmp" <<EOF
{
  "current_sha": $(json_str "$local_sha"),
  "current_date": $(json_str "$local_date"),
  "current_tag": $(json_str "$(current_tag)"),
  "remote_sha": $(json_str "$latest_tag"),
  "update_available": $avail,
  "updating": $updating,
  "last_check": "$(now_utc)",
  "auto_update": true,
  "mode": "$(read_mode)",
  "note": $(json_str "$note"),
  "stage": "$JOB_STAGE",
  "progress": $JOB_PROGRESS,
  "target_tag": $(json_str "$JOB_TARGET"),
  "started_at": $(json_str "$JOB_STARTED"),
  "finished_at": $(json_str "$JOB_FINISHED"),
  "error": $(json_str "$JOB_ERROR"),
  "download_percent": $(json_num "$JOB_DL_PERCENT"),
  "download_bytes": $(json_num "$JOB_DL_BYTES"),
  "download_total": $(json_num "$JOB_DL_TOTAL")
}
EOF
    mv -f "$STATE_FILE.tmp" "$STATE_FILE"
}

set_stage() { # $1: этап, $2: общий прогресс, $3: примечание
    [ "$JOB_STAGE" != "$1" ] && log "этап: $1 — $3"
    JOB_STAGE="$1"
    JOB_PROGRESS="$2"
    save_job
    write_state true "$3" "$LATEST_TAG" true
}

fail_update() { # $1: текст ошибки
    JOB_STAGE="error"
    JOB_ERROR="$1"
    JOB_FINISHED="$(now_utc)"
    save_job
    write_state false "$1" "$LATEST_TAG" true
    log "ошибка: $1"
}

restore_job

TOKEN="$(read_env GITHUB_TOKEN)"
if [ -z "$TOKEN" ]; then
    write_state false "нет GITHUB_TOKEN в .env — обновления недоступны" "" false
    log "GITHUB_TOKEN не задан"
    exit 0
fi

gh_api() { # $1: путь после /repos/.../
    curl -fsS --max-time 30 \
        -H "Authorization: token $TOKEN" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "$REPO_API/$1" 2>/dev/null
}

json_field() { # $1: имя поля верхнего уровня в JSON из stdin
    sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n1
}

if ! RELEASE_JSON="$(gh_api releases/latest)"; then
    write_state false "нет связи с GitHub Releases" "" false
    log "releases/latest не ответил"
    exit 0
fi

LATEST_TAG="$(echo "$RELEASE_JSON" | json_field tag_name)"
if [ -z "$LATEST_TAG" ]; then
    write_state false "релизов нет" "" false
    exit 0
fi

CUR_TAG="$(current_tag)"
AVAILABLE=false
[ "$LATEST_TAG" != "$CUR_TAG" ] && AVAILABLE=true
MODE="$(read_mode)"
REQUESTED=false
[ -f "$REQUEST_FILE" ] && REQUESTED=true
REQ_TAG="$(requested_tag)"

# Выбрана конкретная версия (в том числе откат) — берём её релиз
TARGET_TAG="$LATEST_TAG"
if [ -n "$REQ_TAG" ] && [ "$REQ_TAG" != "$LATEST_TAG" ]; then
    if ! RELEASE_JSON="$(gh_api "releases/tags/$REQ_TAG")"; then
        rm -f "$REQUEST_FILE"
        JOB_TARGET="$REQ_TAG"
        fail_update "версия $REQ_TAG не найдена на GitHub"
        exit 1
    fi
    TARGET_TAG="$REQ_TAG"
fi

if [ "$AVAILABLE" != true ] && [ "$REQUESTED" != true ]; then
    write_state false "актуальная версия ($LATEST_TAG)" "$LATEST_TAG" false
    exit 0
fi

MUST_APPLY=false
[ "$REQUESTED" = true ] && MUST_APPLY=true
[ "$MODE" = "auto" ] && MUST_APPLY=true

if [ "$AVAILABLE" = true ] && [ "$MUST_APPLY" != true ]; then
    write_state false "доступна $LATEST_TAG — установите вручную (Настройки → Обновление)" "$LATEST_TAG" true
    exit 0
fi

if [ ! -f "$REPO_DIR/.apply_force" ] && git rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        write_state false "есть локальные изменения — автообновление пропущено" "$LATEST_TAG" "$AVAILABLE"
        log "локальные правки, обновление не применено"
        exit 0
    fi
fi

# Для приватного репо browser_download_url не работает — берём API-url ассета
ASSET_API_URL="$(echo "$RELEASE_JSON" | tr ',' '\n' | grep -o '"url"[[:space:]]*:[[:space:]]*"[^"]*\/releases\/assets\/[0-9]*"' |
    head -n1 | sed 's/.*"\(https[^"]*\)".*/\1/')"
ASSET_URL="$(echo "$RELEASE_JSON" | tr ',' '\n' | grep -o '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*\.zip"' |
    head -n1 | sed 's/.*"\(https[^"]*\)".*/\1/')"
DOWNLOAD_URL="${ASSET_API_URL:-$ASSET_URL}"
ASSET_SIZE="$(echo "$RELEASE_JSON" | tr ',' '\n' | sed -n 's/.*"size"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' | head -n1)"

JOB_TARGET="$TARGET_TAG"; JOB_STARTED="$(now_utc)"; JOB_FINISHED=""; JOB_ERROR=""
JOB_DL_PERCENT=""; JOB_DL_BYTES=""; JOB_DL_TOTAL=""
set_stage checking 2 "подготовка к установке $TARGET_TAG"

if [ -z "$DOWNLOAD_URL" ]; then
    fail_update "в релизе $TARGET_TAG нет zip-архива"
    exit 1
fi

TMP_DIR="$(mktemp -d /tmp/bike-crm-update.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
ZIP_FILE="$TMP_DIR/release.zip"

JOB_DL_TOTAL="$ASSET_SIZE"; JOB_DL_PERCENT=0; JOB_DL_BYTES=0
set_stage downloading 5 "скачивание $TARGET_TAG"

# curl в фоне: пока он качает, по размеру файла считаем процент
curl -fsSL --max-time 300 \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/octet-stream" \
    -o "$ZIP_FILE" "$DOWNLOAD_URL" &
CURL_PID=$!
LAST_PCT=-1
while kill -0 "$CURL_PID" 2>/dev/null; do
    sleep 1
    if [ -n "$ASSET_SIZE" ] && [ "$ASSET_SIZE" -gt 0 ] && [ -f "$ZIP_FILE" ]; then
        BYTES="$(stat -c %s "$ZIP_FILE" 2>/dev/null || echo 0)"
        PCT=$((BYTES * 100 / ASSET_SIZE))
        [ "$PCT" -gt 99 ] && PCT=99
        if [ "$PCT" -ne "$LAST_PCT" ]; then
            LAST_PCT="$PCT"
            JOB_DL_PERCENT="$PCT"; JOB_DL_BYTES="$BYTES"
            set_stage downloading $((5 + PCT * 30 / 100)) "скачивание $TARGET_TAG: $PCT%"
        fi
    fi
done
if ! wait "$CURL_PID" || [ ! -s "$ZIP_FILE" ]; then
    fail_update "ошибка скачивания $TARGET_TAG"
    exit 1
fi
JOB_DL_PERCENT=100; JOB_DL_BYTES="$(stat -c %s "$ZIP_FILE" 2>/dev/null || echo "$ASSET_SIZE")"

set_stage extracting 35 "распаковка архива"
if ! unzip -q "$ZIP_FILE" -d "$TMP_DIR/src" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
            "$ZIP_FILE" "$TMP_DIR/src" || {
            fail_update "ошибка распаковки архива"
            exit 1
        }
    else
        fail_update "нет unzip и python3 для распаковки"
        exit 1
    fi
fi

SRC_DIR="$(find "$TMP_DIR/src" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$SRC_DIR" ]; then
    fail_update "пустой архив"
    exit 1
fi

# zip собран через git archive — в нём нет .env, data/, .update_*;
# раскладываем поверх рабочей копии
set_stage copying 40 "копирование файлов"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude='.env' "$SRC_DIR/" "$REPO_DIR/"
else
    cp -a "$SRC_DIR/." "$REPO_DIR/"
fi

set_stage building 45 "сборка образов (может занять несколько минут)"
if ! docker compose build -q; then
    fail_update "ошибка сборки образов"
    exit 1
fi
set_stage migrating 80 "миграции базы данных"
if ! docker compose run --rm api alembic upgrade head; then
    fail_update "ошибка миграций базы данных"
    exit 1
fi
set_stage restarting 90 "перезапуск CRM"
if ! docker compose up -d; then
    fail_update "ошибка запуска контейнеров"
    exit 1
fi
# nginx помнит старые адреса пересозданных контейнеров
docker compose restart nginx >/dev/null 2>&1 || true

echo "$TARGET_TAG" >"$TAG_FILE"

if git rev-parse --git-dir >/dev/null 2>&1; then
    git add -A >/dev/null 2>&1 || true
    git -c user.name="auto-update" -c user.email="auto-update@local" \
        commit -q -m "chore: release $TARGET_TAG" --allow-empty >/dev/null 2>&1 || true
fi

rm -f "$REQUEST_FILE" "$REPO_DIR/.apply_force"
JOB_STAGE="done"; JOB_PROGRESS=100; JOB_FINISHED="$(now_utc)"
save_job
AVAIL_AFTER=false
[ "$LATEST_TAG" != "$TARGET_TAG" ] && AVAIL_AFTER=true
write_state false "установлена $TARGET_TAG" "$LATEST_TAG" "$AVAIL_AFTER"
log "обновлено до $TARGET_TAG"
