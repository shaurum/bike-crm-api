"""Вложения сообщений: общие функции для всех каналов.

Путь к файлу в uploads/, полная публичная ссылка, вид вложения
(фото/голосовое/аудио/видео/документ) и безопасное имя файла.
"""

import mimetypes
import os
import re
from typing import Literal, Optional
from urllib.parse import quote

from app.core.config import settings

AttachmentKind = Literal["image", "animation", "voice", "audio", "video", "document"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VOICE_EXTS = {".ogg", ".oga", ".opus"}
AUDIO_EXTS = {".mp3", ".m4a"}
VIDEO_EXTS = {".mp4", ".mov"}

# Тип, который заголовок файлового сервера отдаёт, когда ничего не знает
_GENERIC_TYPES = {"", "application/octet-stream"}

_MAX_SAFE_NAME = 80

_BOT_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def mask_token(text: object) -> str:
    """Прячет токен бота Telegram в тексте (URL вида .../bot<TOKEN>/method)."""
    return _BOT_TOKEN_RE.sub("bot***", str(text))

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip


def resolve_upload(url: str, subdir: Optional[str] = None) -> Optional[str]:
    """Путь к файлу в uploads/ внутри контейнера (защита от ../).

    subdir — дополнительно требовать, чтобы файл лежал в uploads/<subdir>/.
    """
    if not url.startswith("/uploads/"):
        return None
    root = os.path.abspath(settings.UPLOAD_DIR)
    target = os.path.abspath(os.path.join(root, url[len("/uploads/") :]))
    if not target.startswith(root + os.sep):
        return None
    if subdir:
        sub_root = os.path.join(root, subdir)
        if not target.startswith(sub_root + os.sep):
            return None
    return target if os.path.isfile(target) else None


def public_url(url: str) -> Optional[str]:
    """Полная ссылка на вложение, доступная получателю.

    Внешние http(s) возвращаются как есть; файлы из /uploads/ собираются через
    PUBLIC_BASE_URL, без него отдавать нечего (None).
    """
    if url.startswith(("http://", "https://")):
        return url
    if not url.startswith("/uploads/"):
        return None
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return None
    path = "/".join(quote(part, safe="") for part in url.split("/"))
    return base + path


def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


def detect_kind(name: str, content_type: Optional[str]) -> AttachmentKind:
    """Вид вложения для выбора метода отправки (в первую очередь по расширению)."""
    ext = _ext(name)
    ctype = (content_type or "").split(";")[0].strip().lower()

    if ext == ".gif":
        return "animation"
    if ext == ".heic":
        # Telegram не показывает HEIC как фото
        return "document"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VOICE_EXTS:
        return "voice"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"

    if ctype == "image/gif":
        return "animation"
    if ctype in {"image/heic", "image/heif"}:
        return "document"
    if ctype.startswith("image/"):
        return "image"
    if ctype.startswith("audio/"):
        return "audio"
    if ctype.startswith("video/"):
        return "video"
    return "document"


def normalize_content_type(name: str, content_type: Optional[str]) -> str:
    """Если тип пустой или octet-stream — определяем по имени файла."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in _GENERIC_TYPES:
        return ctype
    if _ext(name) in VOICE_EXTS:
        return "audio/ogg"
    return mimetypes.guess_type(name or "")[0] or "application/octet-stream"


def _transliterate(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in _TRANSLIT:
            rep = _TRANSLIT[low]
            out.append(rep.capitalize() if ch != low else rep)
        else:
            out.append(ch)
    return "".join(out)


def safe_name(original: str, ext: str) -> str:
    """Имя файла на диске: латиница [A-Za-z0-9._-], до 80 символов, расширение ext.

    «Счёт март.pdf» -> «Schet_mart.pdf»; пустое имя -> «file<ext>».
    """
    stem = os.path.splitext(os.path.basename(original or ""))[0]
    stem = _transliterate(stem)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    stem = re.sub(r"_{2,}", "_", stem).strip("._-")
    stem = stem[: max(_MAX_SAFE_NAME - len(ext), 0)].strip("._-")
    return (stem or "file") + ext
