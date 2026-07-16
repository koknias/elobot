"""Helpers for Telegram Bot API rich messages.

python-telegram-bot 21.3 predates Bot API 10.1/10.2, so it doesn't expose
``sendRichMessage`` yet. Keep the integration small and isolated: callers pass
already-built rich HTML and this module talks to Telegram directly.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import json
import os
import urllib.error
import urllib.request
from typing import Callable


class RichMessageError(RuntimeError):
    """Raised when Telegram rejects a rich message request."""


def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RichMessageError(raw or str(exc)) from exc
    except urllib.error.URLError as exc:
        raise RichMessageError(str(exc)) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RichMessageError(f"Bad Telegram response: {raw[:300]}") from exc
    if not parsed.get("ok"):
        raise RichMessageError(parsed.get("description") or raw[:300])
    return parsed


async def send_rich_html_message(
    chat_id: int | str,
    html: str,
    *,
    token: str | None = None,
    disable_notification: bool | None = None,
    reply_markup=None,
) -> dict:
    """Send a Bot API 10.x rich message using rich HTML markup."""
    bot_token = (token or os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        raise RichMessageError("BOT_TOKEN is not configured")

    payload: dict = {
        "chat_id": chat_id,
        "rich_message": {
            "html": html,
            "skip_entity_detection": True,
        },
    }
    if disable_notification is not None:
        payload["disable_notification"] = disable_notification
    if reply_markup is not None:
        payload["reply_markup"] = (
            reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
        )

    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    return await asyncio.to_thread(_post_json, url, payload)


def build_tournament_announcement_html(
    t: dict,
    *,
    type_label: Callable[[str], str],
    registered_count: int | None = None,
    deadline: str | None = None,
    signup_link: str | None = None,
    footer: str | None = None,
) -> str:
    """Build rich HTML with a Telegram-native table and regulation blocks."""
    name = html_lib.escape(str(t.get("name") or "Турнир"))
    t_type = html_lib.escape(type_label(t.get("tournament_type") or "vsa"))
    groups = html_lib.escape(str(t.get("groups_count") or "авто"))
    group_size = html_lib.escape(str(t.get("target_group_size") or "авто"))
    playoff_slots = html_lib.escape(str(t.get("playoff_slots") or "по решению организаторов"))
    group_matches = html_lib.escape(str(t.get("group_matches_per_pair") or 1))
    playoff_matches = html_lib.escape(str(t.get("playoff_matches_per_pair") or 1))
    description = html_lib.escape((t.get("description") or "").strip())
    intro = (
        description
        or "Регистрация открыта. Собрали ключевую информацию в одном сообщении."
    )

    extra_rows: list[str] = []
    if registered_count is not None:
        extra_rows.append(
            f"<tr><td>Уже записалось</td><td>{int(registered_count)}</td></tr>"
        )
    if deadline:
        extra_rows.append(
            f"<tr><td>Дедлайн записи</td><td>{html_lib.escape(deadline)}</td></tr>"
        )
    if signup_link:
        extra_rows.append(
            f"<tr><td>Где регаться</td><td>{html_lib.escape(signup_link)}</td></tr>"
        )
    footer_html = (
        f"\n<footer>{html_lib.escape(footer)}</footer>" if footer else ""
    )

    return f"""
<h2>{name}</h2>
<p><b>Регистрация открыта.</b> Собрали ключевую информацию в одном сообщении.</p>
<table bordered striped>
<caption>Ключевые данные</caption>
<tr><th>Параметр</th><th>Значение</th></tr>
<tr><td>Тип</td><td>{t_type}</td></tr>
<tr><td>Группы</td><td>{groups}</td></tr>
<tr><td>Команд в группе</td><td>{group_size}</td></tr>
<tr><td>Матчей в группе</td><td>{group_matches}</td></tr>
<tr><td>Матчей в плей-офф</td><td>{playoff_matches}</td></tr>
<tr><td>Слотов плей-офф</td><td>{playoff_slots}</td></tr>
{''.join(extra_rows)}
</table>
<details open><summary>🏆 Формат турнира</summary>
<p>Турнир начинается с группового этапа. Количество групп определяется в зависимости от общего числа участников.</p>
<p>По итогам группового этапа лучшие команды выходят в плей-офф. Плей-офф проводится по системе на выбывание до определения чемпиона турнира.</p>
</details>
<details><summary>⚽ Регламент</summary>
<p>{intro}</p>
<ul>
<li>Перед регистрацией проверьте данные профиля и привязку Telegram.</li>
<li>Следите за сообщениями организаторов по правилам, дедлайнам и спорным ситуациям.</li>
</ul>
</details>{footer_html}
""".strip()


def build_plain_tournament_announcement(
    t: dict,
    *,
    type_label: Callable[[str], str],
    registered_count: int | None = None,
    deadline: str | None = None,
    signup_link: str | None = None,
    footer: str | None = None,
) -> str:
    """Fallback announcement for old Bot API paths."""
    name = html_lib.escape(str(t.get("name") or "Турнир"))
    desc = html_lib.escape((t.get("description") or "").strip())
    lines = [
        f"🏆 <b>{name}</b>",
        "Регистрация открыта. Собрали ключевую информацию в одном сообщении.",
        "",
        f"📋 Тип: <b>{html_lib.escape(type_label(t.get('tournament_type') or 'vsa'))}</b>",
        f"👥 Группы: <b>{html_lib.escape(str(t.get('groups_count') or 'авто'))}</b>",
        f"🏁 Плей-офф: <b>{html_lib.escape(str(t.get('playoff_slots') or 'по решению организаторов'))}</b>",
    ]
    if registered_count is not None:
        lines.append(f"🙋 Уже записалось: <b>{int(registered_count)}</b>")
    if deadline:
        lines.append(f"📅 Дедлайн записи: <b>{html_lib.escape(deadline)}</b>")
    if signup_link:
        lines.append(f"🔗 Где регаться: {html_lib.escape(signup_link)}")
    if desc:
        lines.extend(["", f"📝 {desc}"])
    lines.extend(["", "Проверьте данные профиля и привязку Telegram перед регистрацией."])
    if footer:
        lines.append(html_lib.escape(footer))
    return "\n".join(lines)


def should_auto_rich_text(text: str) -> bool:
    """Return True for ordinary bot messages worth rendering as rich cards."""
    stripped = (text or "").strip()
    if not stripped or "\n" not in stripped:
        return False
    if len(stripped) < 80:
        return False
    first = stripped.lstrip()[:2]
    if first in ("❌", "⚠️", "✅", "ℹ️", "🔍"):
        return False
    return True


def build_auto_rich_html(text: str) -> str:
    """Convert existing HTML-ish bot text into a richer Telegram card.

    The bot already escapes user-provided fragments before passing them through
    parse_mode=HTML, so this intentionally preserves existing inline tags.
    """
    raw_lines = [line.rstrip() for line in (text or "").splitlines()]
    lines = [line for line in raw_lines if line.strip()]
    if not lines:
        return ""

    title = lines[0].strip()
    body = lines[1:]
    table_rows: list[str] = []
    paragraphs: list[str] = []
    list_items: list[str] = []

    for line in body:
        s = line.strip()
        if not s:
            continue
        bullet = s.startswith(("• ", "- ", "* "))
        if bullet:
            list_items.append(s[2:].strip())
            continue
        if ":" in s and len(s) <= 180:
            left, right = s.split(":", 1)
            if left.strip() and right.strip() and len(left.strip()) <= 45:
                table_rows.append(
                    f"<tr><td>{left.strip()}</td><td>{right.strip()}</td></tr>"
                )
                continue
        paragraphs.append(s)

    parts = [f"<h3>{title}</h3>"]
    if table_rows:
        parts.append(
            "<table bordered striped><caption>Детали</caption>"
            "<tr><th>Пункт</th><th>Значение</th></tr>"
            + "".join(table_rows)
            + "</table>"
        )
    if paragraphs:
        parts.extend(f"<p>{p}</p>" for p in paragraphs)
    if list_items:
        parts.append("<details open><summary>Подробнее</summary><ul>")
        parts.extend(f"<li>{item}</li>" for item in list_items)
        parts.append("</ul></details>")
    return "\n".join(parts)
