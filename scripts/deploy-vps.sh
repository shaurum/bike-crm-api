#!/bin/sh
# Деплой релиза на VPS. Запускает .github/workflows/deploy.yml по SSH:
#   ssh root@сервер 'sh -s' -- v1.2.3 < scripts/deploy-vps.sh
#
# На VPS работает облачный шлюз интеграций (Telegram, Авито) — контейнер
# integration-gateway. Скрипт находит его папку, кладёт туда код шлюза из
# релиза и пересобирает контейнер. docker-compose.yml, .env, data/ и certs/
# на сервере не трогаются. Если после пересборки шлюз не отвечает на /health,
# возвращается прежний код.
# Если на сервере есть и CRM (/opt/bike-crm), её обновляет её же скрипт.
set -eu

REPO="shaurum/bike-crm-api"
TAG="${1:-}"
CONTAINER="${GATEWAY_CONTAINER:-integration-gateway}"
CRM_UPDATE="${CRM_UPDATE_SCRIPT:-/opt/bike-crm/scripts/auto-update.sh}"
# Файлы шлюза, которые приходят из релиза
GATEWAY_FILES="requirements.txt Dockerfile entrypoint.sh"

say() { echo "[deploy] $*"; }
fail() { echo "::error::$*"; exit 1; }

latest_tag() {
    curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" |
        sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}

if [ -z "$TAG" ]; then
    TAG="$(latest_tag)" || true
    [ -n "$TAG" ] || fail "не удалось узнать последнюю версию на GitHub"
fi
say "версия $TAG"

# --- CRM: только если она установлена на этом сервере --------------------------
if [ -f "$CRM_UPDATE" ]; then
    say "обновляю CRM ($CRM_UPDATE)"
    bash "$CRM_UPDATE" || fail "скрипт обновления CRM завершился с ошибкой"
else
    say "CRM на этом сервере нет, пропускаю"
fi

# --- Шлюз ------------------------------------------------------------------------
GW_DIR="$(docker inspect "$CONTAINER" \
    --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)"
if [ -z "$GW_DIR" ] || [ ! -d "$GW_DIR" ]; then
    say "контейнер $CONTAINER не найден, шлюз не обновляю"
    exit 0
fi
say "шлюз в $GW_DIR"

TMP="$(mktemp -d /tmp/gateway-deploy.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# Release и Deploy стартуют от одного тега одновременно: ждём, пока появится архив
URL="https://github.com/$REPO/releases/download/$TAG/bike-crm-$TAG.zip"
i=0
until curl -fsSL -o "$TMP/release.zip" "$URL"; do
    i=$((i + 1))
    [ "$i" -ge 20 ] && fail "архив релиза $TAG не появился: $URL"
    say "архив ещё не готов, жду ($i/20)"
    sleep 15
done

mkdir -p "$TMP/src"
if command -v unzip >/dev/null 2>&1; then
    unzip -q "$TMP/release.zip" -d "$TMP/src"
else
    python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
        "$TMP/release.zip" "$TMP/src"
fi
SRC="$(find "$TMP/src" -mindepth 2 -maxdepth 2 -type d -name gateway | head -n1)"
[ -n "$SRC" ] && [ -d "$SRC/app" ] || fail "в архиве $TAG нет папки gateway"

changed=0
diff -rq "$SRC/app" "$GW_DIR/app" >/dev/null 2>&1 || changed=1
for f in $GATEWAY_FILES; do
    cmp -s "$SRC/$f" "$GW_DIR/$f" || changed=1
done
if [ "$changed" -eq 0 ]; then
    say "код шлюза не изменился"
    exit 0
fi

BACKUP="$GW_DIR/.deploy-backup"
rm -rf "$BACKUP"
mkdir -p "$BACKUP"
[ -d "$GW_DIR/app" ] && cp -a "$GW_DIR/app" "$BACKUP/app"
for f in $GATEWAY_FILES; do
    [ -f "$GW_DIR/$f" ] && cp -a "$GW_DIR/$f" "$BACKUP/$f"
done

install_from() { # $1: папка с кодом шлюза
    rm -rf "$GW_DIR/app"
    cp -a "$1/app" "$GW_DIR/app"
    for f in $GATEWAY_FILES; do
        [ -f "$1/$f" ] && cp -a "$1/$f" "$GW_DIR/$f"
    done
    chmod +x "$GW_DIR/entrypoint.sh" 2>/dev/null || true
    (cd "$GW_DIR" && docker compose up -d --build)
}

healthy() {
    docker exec "$CONTAINER" python -c '
import ssl, sys, urllib.request
ctx = ssl._create_unverified_context()
for url in ("https://127.0.0.1:8443/health", "http://127.0.0.1:8443/health"):
    try:
        urllib.request.urlopen(url, context=ctx, timeout=5)
        sys.exit(0)
    except Exception:
        pass
sys.exit(1)
' >/dev/null 2>&1
}

wait_healthy() {
    i=0
    while [ "$i" -lt 30 ]; do
        healthy && return 0
        i=$((i + 1))
        sleep 2
    done
    return 1
}

say "ставлю код шлюза из $TAG"
if install_from "$SRC" && wait_healthy; then
    say "шлюз обновлён до $TAG и отвечает на /health"
    exit 0
fi

say "шлюз не поднялся, возвращаю прежний код"
docker logs --tail 40 "$CONTAINER" 2>&1 || true
install_from "$BACKUP" || true
if wait_healthy; then
    fail "обновление шлюза до $TAG откатано: новый код не запустился"
fi
fail "шлюз не отвечает и после отката, нужна ручная проверка"
