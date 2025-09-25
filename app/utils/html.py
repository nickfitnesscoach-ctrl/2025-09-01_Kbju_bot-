"""Helpers for working with short HTML snippets."""

from __future__ import annotations

import html
import re

__all__ = [
    "CAPTION_LIMIT",
    "DEFAULT_TRUNCATE_LIMIT",
    "split_html_by_len",
    "strip_html",
]

CAPTION_LIMIT = 1024
DEFAULT_TRUNCATE_LIMIT = 1000

_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"<[^>]+>|[^<]+")
_SELF_CLOSING_TAGS = {"br", "img", "hr", "input", "meta", "link"}


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""

    no_tags = _TAG_RE.sub("", text)
    return html.unescape(no_tags)


def split_html_by_len(
    text: str,
    caption_limit: int = CAPTION_LIMIT,
    truncate_limit: int = DEFAULT_TRUNCATE_LIMIT,
) -> tuple[str, str]:
    """Split HTML text into caption-sized head and the remainder."""

    if caption_limit <= 0:
        return "", text

    if len(strip_html(text)) <= caption_limit:
        return text, ""

    truncate_limit = min(truncate_limit, caption_limit)

    open_tags: list[tuple[str, str]] = []
    split_pos: int | None = None
    consumed_plain = 0

    for match in _TOKEN_RE.finditer(text):
        token = match.group()
        start, end = match.span()

        if token.startswith("<"):
            if consumed_plain < truncate_limit:
                tag_name = _extract_tag_name(token)
                if tag_name is None:
                    continue
                if _is_self_closing(token, tag_name):
                    continue
                if token.startswith("</"):
                    _pop_tag(open_tags, tag_name)
                else:
                    open_tags.append((tag_name, token))
            continue

        if consumed_plain >= truncate_limit:
            split_pos = start
            break

        token_plain_len = len(html.unescape(token))
        if consumed_plain + token_plain_len < truncate_limit:
            consumed_plain += token_plain_len
            continue

        if consumed_plain + token_plain_len == truncate_limit:
            consumed_plain += token_plain_len
            split_pos = end
            break

        need = truncate_limit - consumed_plain
        before, _after, consumed = _split_text_token(token, need)
        split_pos = start + len(before)
        consumed_plain += consumed
        break
    else:
        split_pos = len(text)

    if split_pos is None:
        split_pos = len(text)

    head_raw = text[:split_pos]
    tail_raw = text[split_pos:]

    closing_tags = "".join(f"</{name}>" for name, _ in reversed(open_tags))
    head = f"{head_raw}…{closing_tags}"
    tail_prefix = "".join(token for _, token in open_tags)
    tail = f"{tail_prefix}{tail_raw}".strip()

    return head, tail


def _extract_tag_name(token: str) -> str | None:
    body = token[1:-1].strip()
    if not body:
        return None
    if body.startswith("/"):
        body = body[1:].strip()
    if body.endswith("/"):
        body = body[:-1].strip()
    if not body:
        return None
    return body.split()[0].lower()


def _is_self_closing(token: str, tag_name: str | None = None) -> bool:
    if token.endswith("/>"):
        return True
    if tag_name is None:
        tag_name = _extract_tag_name(token)
    if not tag_name:
        return False
    return tag_name in _SELF_CLOSING_TAGS


def _pop_tag(stack: list[tuple[str, str]], tag_name: str) -> None:
    for idx in range(len(stack) - 1, -1, -1):
        if stack[idx][0] == tag_name:
            stack.pop(idx)
            break


def _split_text_token(token: str, limit: int) -> tuple[str, str, int]:
    if limit <= 0:
        return "", token, 0

    consumed = 0
    index = 0
    length = len(token)

    while index < length and consumed < limit:
        char = token[index]
        if char == "&":
            semicolon = token.find(";", index + 1)
            if semicolon != -1:
                entity = token[index : semicolon + 1]
                unescaped = html.unescape(entity)
                plain_len = len(unescaped) or 1
                if consumed + plain_len > limit:
                    break
                consumed += plain_len
                index = semicolon + 1
                continue
        consumed += 1
        index += 1

    return token[:index], token[index:], consumed
