"""Паспорт Гвардиолыча — player passport cards with notes and trophies.

* ``/passport [@username]``       — show passport card (photo).
* ``/passport_note @username <t>``— leave a public note.
* ``/passport_notes [@username]`` — list all notes for a player.
"""
from __future__ import annotations

import html
import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from database import (
    add_passport_note,
    get_passport_notes,
    get_player,
    get_player_by_telegram_id,
    get_titles_for_player,
    player_title_strings,
)
from handlers._helpers import _player_from_user
from handlers.common import mention, send

log = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

async def _download_avatar(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> bytes | None:
    try:
        photos = await ctx.bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            file = await photos.photos[0][-1].get_file()
            return await file.download_as_bytearray()
    except Exception as exc:
        log.debug("avatar download failed for user %s: %s", user_id, exc)
    return None


_STYLES = frozenset({"mafia", "mclovin", "криминал", "мактрахер"})


def _resolve_player_arg_or_user(
    args: list[str],
    update: Update,
) -> tuple[dict | None, str]:
    style = "default"
    if args:
        first = args[0].lstrip("@").lower()
        if first in _STYLES:
            p = _player_from_user(update.effective_user)
            style = "mclovin" if first in ("mclovin",) else "mafia"
            return p, style
        p = get_player(first)
        if not p:
            return None, style
        if len(args) > 1 and args[1].lower() in _STYLES:
            style = "mclovin" if args[1].lower() in ("mclovin",) else "mafia"
        return p, style
    return _player_from_user(update.effective_user), style


def _build_trophy_counts(player_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ttype in ("main", "fantasy", "vsa", "supercup"):
        titles = get_titles_for_player(player_id, tournament_type=ttype)
        counts[ttype] = len(titles)
    return counts


# ── commands ─────────────────────────────────────────────────────────────────

async def cmd_passport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p, style = _resolve_player_arg_or_user(ctx.args, update)
    if not p:
        await send(update, "❌ Игрок не найден.\n/passport [@user] — обычный\n/mafia [@user] — мактрахер\n/mclovin [@user] — mclovin style")
        return

    from passport_image import render_passport_png

    trophy_counts = _build_trophy_counts(p["id"])
    titles = player_title_strings(p["id"])
    notes = get_passport_notes(p["id"], limit=3)

    tid = p.get("telegram_id")
    avatar_bytes = None
    if tid:
        avatar_bytes = await _download_avatar(int(tid), ctx)

    try:
        png_bytes = render_passport_png(
            p, trophy_counts, titles, notes,
            avatar_bytes=avatar_bytes,
            style=style,
        )
    except Exception as exc:
        log.exception("passport render failed for player %s: %s", p["id"], exc)
        await send(update, "❌ Ошибка при создании паспорта.")
        return

    photo = BytesIO(png_bytes)
    photo.name = "passport.png"

    if style == "default":
        emoji, label = "📋", "Паспорт"
    elif style == "mafia":
        emoji, label = "🚨", "Криминальный паспорт"
    else:
        emoji, label = "🆔", "McLovin ID"
    caption = (
        f"{emoji} {label} {mention(p['username'])}"
        f"{' (' + html.escape(p['game_nickname']) + ')' if p.get('game_nickname') else ''}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 Оставить заметку: /passport_note {mention(p['username'])} [текст]\n"
        f"📖 Все заметки: /passport_notes {mention(p['username'])}"
    )

    await update.effective_message.reply_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
    )


async def cmd_passport_mafia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.args = (ctx.args or []) + ["mafia"]  # type: ignore[attr-defined]
    await cmd_passport(update, ctx)


async def cmd_passport_mclovin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.args = (ctx.args or []) + ["mclovin"]  # type: ignore[attr-defined]
    await cmd_passport(update, ctx)


async def cmd_passport_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 2:
        await send(update, "❌ Использование: /passport_note @username [текст заметки]")
        return

    target_raw = ctx.args[0].lstrip("@").lower()
    target = get_player(target_raw)
    if not target:
        await send(update, f"❌ Игрок @{target_raw} не найден.")
        return

    author = _player_from_user(update.effective_user)
    if not author:
        await send(update, "❌ Ты не зарегистрирован. Используй /register.")
        return

    note_text = " ".join(ctx.args[1:]).strip()
    if len(note_text) < 1:
        await send(update, "❌ Текст заметки не может быть пустым.")
        return
    if len(note_text) > 500:
        note_text = note_text[:500]

    add_passport_note(target["id"], author["id"], note_text)
    await send(
        update,
        f"✅ Заметка для {mention(target['username'])} добавлена!\n"
        f"📖 Все заметки: /passport_notes {mention(target['username'])}",
    )


async def cmd_passport_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p, _style = _resolve_player_arg_or_user(ctx.args, update)
    if not p:
        await send(update, "❌ Игрок не найден.\nИспользование: /passport_notes [@username]")
        return

    notes = get_passport_notes(p["id"], limit=20)
    if not notes:
        await send(update, f"📭 У {mention(p['username'])} пока нет заметок.")
        return

    lines = [
        f"📋 <b>Заметки для {mention(p['username'])}</b>",
        f"Всего: {len(notes)}",
        "━━━━━━━━━━━━━━━━",
    ]
    for n in notes:
        au = html.escape(n.get("author_username") or "?")
        nt = html.escape(n.get("note_text") or "")
        from_ = f"@{au}" if au else "—"
        lines.append(f"💬 {nt}\n   — {from_}")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("📝 Оставить: /passport_note @username [текст]")

    await send(update, "\n".join(lines))
