"""
НЕ РЕДАКТИРУЕМ ТЕКСТЫ ЗДЕСЬ.
Единственный источник текстов: app/texts_data.json (меняется через админку).

Этот модуль — тонкий адаптер:
- грузит JSON в память,
- отдаёт get_text()/get_button_text(),
- по желанию сохраняет назад (save_texts), если админка изменила TEXTS в памяти.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

# Публичный API модуля (удобно для IDE/линтеров)
__all__ = [
    "get_text",
    "get_button_text",
    "save_texts",
    "load_texts",
    "get_media_id",
    "set_media_id",
    "TEXTS",
]

# Глобальное хранилище текстов в памяти (заполняется из JSON)
TEXTS: Dict[str, Any] = {}

# Кэш времени последней модификации файла, чтобы не читать его лишний раз
_LAST_MTIME: Optional[float] = None

logger = logging.getLogger(__name__)


# ---------------------------
# ВНУТРЕННИЕ СЛУЖЕБНЫЕ ШТУКИ
# ---------------------------

def _json_path() -> str:
    """Абсолютный путь до app/texts_data.json."""
    return os.path.join(os.path.dirname(__file__), "texts_data.json")


def _deep_update(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """
    Глубокое объединение словарей:
    - если по ключу в обоих местах dict — сливаем рекурсивно,
    - иначе просто перезаписываем значением из src.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)  # type: ignore[index]
        else:
            dst[k] = v


def _resolve_key(key: str, data: Dict[str, Any]) -> Any:
    """
    Достаёт значение по ключу вида 'a.b.c' из словаря data.
    Возвращает либо найденный узел, либо строку "[Текст не найден: key]".
    """
    node: Any = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return f"[Текст не найден: {key}]"
    return node


# ---------------------------
# ЗАГРУЗКА / СОХРАНЕНИЕ JSON
# ---------------------------

def load_texts(force: bool = False) -> None:
    """
    Загружает тексты из JSON в TEXTS.
    По умолчанию читает файл только если он изменился (по mtime).
    force=True — принудительно перечитать.
    """
    global _LAST_MTIME

    path = _json_path()
    if not os.path.exists(path):
        # Нет файла — оставляем TEXTS как есть (пустой или предыдущий)
        return

    mtime = os.path.getmtime(path)
    if not force and _LAST_MTIME == mtime:
        return  # файл не менялся — ничего не делаем

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            # на всякий случай не перетираем TEXTS неправильным типом
            return
        TEXTS.clear()
        _deep_update(TEXTS, data)
        _LAST_MTIME = mtime
    except Exception:
        logger.exception("Failed to load texts from %s", path)


def save_texts() -> bool:
    """
    Сохраняет текущее содержимое TEXTS обратно в JSON.
    Обычно вызывает админка после правок.
    """
    path = _json_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(TEXTS, f, ensure_ascii=False, indent=2)
        # После записи актуализируем mtime-кэш
        try:
            global _LAST_MTIME
            _LAST_MTIME = os.path.getmtime(path)
        except OSError:
            pass
        return True
    except Exception:
        logger.exception("Failed to save texts to %s", path)
        return False


# ---------------------------
# ПУБЛИЧНЫЙ API ДЛЯ КОДА БОТА
# ---------------------------

def get_text(key: str, **kwargs: Any) -> str:
    """
    Возвращает строку по ключу, поддерживает вложенные ключи ('a.b.c').
    Если узел — dict и в нём есть 'text', берём его.
    Плейсхолдеры подставляются через .format(**kwargs).
    """
    load_texts()  # подхватываем изменения из JSON «на лету»

    node = _resolve_key(key, TEXTS)

    # Если узел — словарь с полем 'text', берём его
    if isinstance(node, dict):
        node = node.get("text", f"[Текст не найден: {key}]")

    if isinstance(node, str):
        try:
            return node.format(**kwargs)  # безопасная подстановка
        except KeyError:
            # Если не передали какой-то плейсхолдер — возвращаем как есть
            return node

    # На крайний случай приводим к строке (например, если в JSON лежит число)
    return str(node)


def get_button_text(key: str) -> str:
    """
    Возвращает подпись кнопки по ключу из блока 'buttons'.
    Пример: get_button_text('calculate_kbju')
    """
    load_texts()
    return TEXTS.get("buttons", {}).get(key, f"[Кнопка не найдена: {key}]")


# Первичная загрузка при импорте модуля
load_texts()


def _resolve_optional(key: str, data: Dict[str, Any]) -> Any | None:
    """Вернуть значение по ключу вида 'a.b.c', либо None, если его нет."""
    node: Any = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _normalize_file_id(value: Any) -> Optional[str]:
    """Привести значение file_id к чистому идентификатору без префиксов."""
    if value is None:
        return None

    # Допускаем, что администратор может прислать значение нестрокой
    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered.startswith("file_id") or lowered.startswith("id"):
        # Удаляем популярные префиксы вида "file_id: ..." или "id: ..."
        _, _, remainder = text.partition(":")
        text = remainder.strip() or text

    # В некоторых ответах бота file_id берётся в кавычки — снимаем их
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()

    return text or None


def get_media_id(key: str) -> Optional[str]:
    """Получить сохранённый file_id медиа по ключу (или None)."""
    load_texts()
    value = _resolve_optional(key, TEXTS)
    if value is None:
        return None
    return _normalize_file_id(value)


def set_media_id(key: str, value: Optional[str]) -> None:
    """Сохранить/удалить file_id медиа в JSON."""
    load_texts()

    target: Dict[str, Any] = TEXTS
    parts = key.split(".")
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]  # type: ignore[assignment]

    normalized = _normalize_file_id(value)

    if normalized is None:
        target.pop(parts[-1], None)
    else:
        target[parts[-1]] = normalized

    if not save_texts():
        raise RuntimeError(f"Failed to persist media id for key {key}")
