#!/usr/bin/env bash
# Автообновление CRM на VPS.
# Cron: * * * * * /opt/bike-crm/scripts/auto-update.sh >> /var/log/bike-crm-update.log 2>&1
# Состояние пишет в backend/.update_state.json — его читает API (/api/v1/system/version).
set -uo pipefail

REPO_DIR="/opt/bike-crm"
STATE_FILE="$REPO_DIR/backend/.update_state.json"
REQUEST_FILE="$REPO_DIR/backend/.update_requested"
LOCK_FILE="/tmp/bike-crm-update.lock"
export GIT_SSH_COMMAND="ssh -i /root/.ssh/bike_crm_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

cd "$REPO_DIR" 2>/dev/null || exit 0
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

write_state() { # $1: true|false (updating), $2: примечание
    local updating="$1" note="$2"
    local local_sha="null" local_date="null" remote_sha="null" update_available="false"
    if git rev-parse --git-dir >/dev/null 2>&1; then
        local_sha="\"$(git rev-parse --short HEAD)\""
        local_date="\"$(git log -1 --format=%cI)\""
        local remote
        remote="$(git rev-parse --short origin/main 2>/dev/null || true)"
        [ -n "$remote" ] && remote_sha="\"$remote\""
        if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main 2>/dev/null || git rev-parse HEAD)" ]; then
            update_available="true"
        fi
    fi
    local last_check
    last_check="$(date -u +%FT%TZ)"
    mkdir -p "$REPO_DIR/backend"
    cat >"$STATE_FILE.tmp" <<EOF
{
  "current_sha": $local_sha,
  "current_date": $local_date,
  "remote_sha": $remote_sha,
  "update_available": $update_available,
  "updating": $updating,
  "last_check": "$last_check",
  "auto_update": true,
  "note": "$note"
}
EOF
    mv -f "$STATE_FILE.tmp" "$STATE_FILE"
}

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    write_state false "репозиторий не клонирован"
    exit 0
fi

if ! git fetch -q origin main 2>/dev/null; then
    write_state false "нет связи с репозиторием"
    exit 0
fi

REMOTE_SHA="$(git rev-parse origin/main)"
LOCAL_SHA="$(git rev-parse HEAD)"
NEED_APPLY=false
[ "$LOCAL_SHA" != "$REMOTE_SHA" ] && NEED_APPLY=true
[ -f "$REQUEST_FILE" ] && NEED_APPLY=true

if [ "$NEED_APPLY" != true ]; then
    write_state false "актуальная версия"
    exit 0
fi

if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    write_state true "установка обновления"
    if ! git reset -q --hard origin/main; then
        write_state false "ошибка git reset"
        exit 1
    fi
    if ! docker compose build -q; then
        write_state false "ошибка сборки образов"
        exit 1
    fi
    if ! docker compose run --rm api alembic upgrade head; then
        write_state false "ошибка миграций"
        exit 1
    fi
    if ! docker compose up -d; then
        write_state false "ошибка запуска контейнеров"
        exit 1
    fi
fi

rm -f "$REQUEST_FILE"
write_state false "обновлено $(date -u +%FT%TZ)"
