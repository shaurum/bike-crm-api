#!/usr/bin/env bash
# Автообновление CRM на VPS из GitHub Releases (не через git pull).
# Cron: * * * * * /opt/bike-crm/scripts/auto-update.sh >> /var/log/bike-crm-update.log 2>&1
#
# GITHUB_TOKEN берётся из /opt/bike-crm/.env (Fine-grained PAT, Contents: Read).
# Режим: backend/.update_mode = auto (по умолчанию) | manual.
#   manual: ставит обновление только по кнопке «Проверить и установить» в CRM
#   (файл backend/.update_requested).
# Состояние пишет в backend/.update_state.json — его читает API (/api/v1/system/version).
set -uo pipefail

REPO_DIR="/opt/bike-crm"
STATE_FILE="$REPO_DIR/backend/.update_state.json"
REQUEST_FILE="$REPO_DIR/backend/.update_requested"
MODE_FILE="$REPO_DIR/backend/.update_mode"
TAG_FILE="$REPO_DIR/.release_tag"
LOCK_FILE="/tmp/bike-crm-update.lock"
REPO_API="https://api.github.com/repos/shaurum/bike-crm-api"

cd "$REPO_DIR" 2>/dev/null || exit 0
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

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

write_state() { # $1: true|false (updating), $2: примечание, $3: latest_tag, $4: true|false (update_available)
    local updating="$1" note="$2" latest_tag="$3" avail="$4"
    local local_sha="null" local_date="null" cur_tag="null" remote="null"
    if git rev-parse --git-dir >/dev/null 2>&1; then
        local_sha="\"$(git rev-parse --short HEAD)\""
        local_date="\"$(git log -1 --format=%cI)\""
    fi
    local ct; ct="$(current_tag)"
    [ -n "$ct" ] && cur_tag="\"$ct\""
    [ -n "$latest_tag" ] && remote="\"$latest_tag\""
    local last_check mode
    last_check="$(date -u +%FT%TZ)"
    mode="$(read_mode)"
    mkdir -p "$REPO_DIR/backend"
    cat >"$STATE_FILE.tmp" <<EOF
{
  "current_sha": $local_sha,
  "current_date": $local_date,
  "current_tag": $cur_tag,
  "remote_sha": $remote,
  "update_available": $avail,
  "updating": $updating,
  "last_check": "$last_check",
  "auto_update": true,
  "mode": "$mode",
  "note": "$note"
}
EOF
    mv -f "$STATE_FILE.tmp" "$STATE_FILE"
}

TOKEN="$(read_env GITHUB_TOKEN)"
if [ -z "$TOKEN" ]; then
    write_state false "нет GITHUB_TOKEN в .env — обновления недоступны" "" false
    log "GITHUB_TOKEN не задан"
    exit 0
fi

if ! RELEASE_JSON="$(curl -fsS --max-time 30 \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$REPO_API/releases/latest" 2>/dev/null)"; then
    write_state false "нет связи с GitHub Releases" "" false
    log "releases/latest не ответил"
    exit 0
fi

LATEST_TAG="$(echo "$RELEASE_JSON" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
if [ -z "$LATEST_TAG" ]; then
    write_state false "релизов нет" "" false
    exit 0
fi

ASSET_URL="$(echo "$RELEASE_JSON" | tr ',' '\n' | grep -o '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*\.zip"' |
    head -n1 | sed 's/.*"\(https[^"]*\)".*/\1/')"
# Для приватного репо browser_download_url не работает — берём API-url ассета
ASSET_API_URL="$(echo "$RELEASE_JSON" | tr ',' '\n' | grep -o '"url"[[:space:]]*:[[:space:]]*"[^"]*\/releases\/assets\/[0-9]*"' |
    head -n1 | sed 's/.*"\(https[^"]*\)".*/\1/')"
DOWNLOAD_URL="${ASSET_API_URL:-$ASSET_URL}"

CUR_TAG="$(current_tag)"
AVAILABLE=false
[ "$LATEST_TAG" != "$CUR_TAG" ] && AVAILABLE=true
MODE="$(read_mode)"
REQUESTED=false
[ -f "$REQUEST_FILE" ] && REQUESTED=true

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

if [ "$AVAILABLE" = true ] && [ ! -f "$REPO_DIR/.apply_force" ] && git rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        write_state false "есть локальные изменения — автообновление пропущено" "$LATEST_TAG" true
        log "локальные правки, обновление не применено"
        exit 0
    fi
fi

if [ -z "$DOWNLOAD_URL" ]; then
    write_state false "в релизе $LATEST_TAG нет zip-артефакта" "$LATEST_TAG" true
    log "нет zip-артефакта в $LATEST_TAG"
    exit 1
fi

write_state true "установка $LATEST_TAG" "$LATEST_TAG" true
log "установка $LATEST_TAG"

TMP_DIR="$(mktemp -d /tmp/bike-crm-update.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
ZIP_FILE="$TMP_DIR/release.zip"

if ! curl -fsSL --max-time 300 \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/octet-stream" \
    -o "$ZIP_FILE" "$DOWNLOAD_URL"; then
    write_state false "ошибка скачивания $LATEST_TAG" "$LATEST_TAG" true
    log "скачивание не удалось"
    exit 1
fi

if ! unzip -q "$ZIP_FILE" -d "$TMP_DIR/src" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
            "$ZIP_FILE" "$TMP_DIR/src" || {
            write_state false "ошибка распаковки" "$LATEST_TAG" true
            log "распаковка не удалась"
            exit 1
        }
    else
        write_state false "нет unzip и python3 для распаковки" "$LATEST_TAG" true
        exit 1
    fi
fi

SRC_DIR="$(find "$TMP_DIR/src" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$SRC_DIR" ]; then
    write_state false "пустой архив" "$LATEST_TAG" true
    exit 1
fi

# zip собран через git archive — в нём нет .env, data/, .update_*;
# раскладываем поверх рабочей копии
if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude='.env' "$SRC_DIR/" "$REPO_DIR/"
else
    cp -a "$SRC_DIR/." "$REPO_DIR/"
fi

if ! docker compose build -q; then
    write_state false "ошибка сборки образов" "$LATEST_TAG" true
    log "build failed"
    exit 1
fi
if ! docker compose run --rm api alembic upgrade head; then
    write_state false "ошибка миграций" "$LATEST_TAG" true
    log "alembic failed"
    exit 1
fi
if ! docker compose up -d; then
    write_state false "ошибка запуска контейнеров" "$LATEST_TAG" true
    log "compose up failed"
    exit 1
fi

echo "$LATEST_TAG" >"$TAG_FILE"

if git rev-parse --git-dir >/dev/null 2>&1; then
    git add -A >/dev/null 2>&1 || true
    git -c user.name="auto-update" -c user.email="auto-update@local" \
        commit -q -m "chore: release $LATEST_TAG" --allow-empty >/dev/null 2>&1 || true
fi

rm -f "$REQUEST_FILE" "$REPO_DIR/.apply_force"
write_state false "обновлено до $LATEST_TAG ($(date -u +%FT%TZ))" "$LATEST_TAG" false
log "обновлено до $LATEST_TAG"
