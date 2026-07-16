"""Extra rich-message commands for tournament operations."""
from __future__ import annotations

import html
from datetime import datetime, timedelta

from telegram.ext import ContextTypes
from telegram import Update

import database as db
from database import (
    get_active_tournament,
    get_match,
    get_overdue_matches,
    get_player,
    get_player_by_id,
    get_tournament,
    get_tournament_matches,
    get_upcoming_deadline_matches,
)
from handlers._helpers import _can_manage_tournament, _format_deadline_countdown, _resolve_tournament_from_args
from handlers.common import _fmt_minute_local, is_admin, mention, send, t_full_label, t_type_label
from rich_messages import RichMessageError, send_rich_html_message
from tournament import get_tournament_podium


def _player_label(pid: int | None) -> str:
    p = get_player_by_id(pid) if pid else None
    return mention(p["username"]) if p else f"id{pid or '?'}"


def _match_html(m: dict) -> str:
    t = get_tournament(m["tournament_id"]) if m.get("tournament_id") else None
    stage = html.escape(str(m.get("stage") or "—"))
    status = html.escape(str(m.get("status") or "pending"))
    score = "—"
    if m.get("score1") is not None and m.get("score2") is not None:
        score = f"{m['score1']}:{m['score2']}"
    deadline = _fmt_minute_local(m.get("deadline")) if m.get("deadline") else "—"
    tour = html.escape(t["name"]) if t else "Товарищеский матч"
    return f"""
<h2>⚔️ Матч #{m['id']}</h2>
<table bordered striped>
<tr><th>Параметр</th><th>Значение</th></tr>
<tr><td>Турнир</td><td>{tour}</td></tr>
<tr><td>Игроки</td><td>{_player_label(m.get('player1_id'))} vs {_player_label(m.get('player2_id'))}</td></tr>
<tr><td>Стадия</td><td>{stage}</td></tr>
<tr><td>Статус</td><td>{status}</td></tr>
<tr><td>Счёт</td><td>{score}</td></tr>
<tr><td>Дедлайн</td><td>{deadline}</td></tr>
</table>
<footer>Результат: /report 3:2 @opponent. Спор: /dispute.</footer>
""".strip()


async def _send_rich(update: Update, rich_html: str, plain: str):
    try:
        await send_rich_html_message(update.effective_chat.id, rich_html)
    except RichMessageError:
        await send(update, plain)


async def cmd_match_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await send(update, "Использование: <code>/match 123</code>")
        return
    raw = ctx.args[0].lstrip("#")
    if not raw.isdigit():
        await send(update, "❌ ID матча должен быть числом.")
        return
    m = get_match(int(raw))
    if not m:
        await send(update, "❌ Матч не найден.")
        return
    await _send_rich(update, _match_html(m), f"⚔️ Матч #{m['id']}: {_player_label(m.get('player1_id'))} vs {_player_label(m.get('player2_id'))}")


def _deadline_rows(matches: list[dict]) -> str:
    rows = []
    for m in matches[:30]:
        t = get_tournament(m["tournament_id"]) if m.get("tournament_id") else None
        rows.append(
            f"<tr><td>#{m['id']}</td><td>{_player_label(m.get('player1_id'))} vs {_player_label(m.get('player2_id'))}</td>"
            f"<td>{html.escape(t['name']) if t else '—'}</td><td>{html.escape(_format_deadline_countdown(m.get('deadline')))}</td></tr>"
        )
    return "".join(rows)


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = get_upcoming_deadline_matches(24)
    if not rows:
        await send(update, "✅ В ближайшие 24 часа дедлайнов нет.")
        return
    rich = (
        "<h2>📅 Дедлайны на сегодня</h2>"
        "<table bordered striped><tr><th>ID</th><th>Матч</th><th>Турнир</th><th>Срок</th></tr>"
        + _deadline_rows(rows)
        + "</table>"
    )
    await _send_rich(update, rich, f"📅 Дедлайны на сегодня: {len(rows)}")


async def cmd_overdue_rich(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await send(update, "❌ Только админ.")
        return
    rows = get_overdue_matches()
    if not rows:
        await send(update, "✅ Просроченных матчей нет.")
        return
    rich = (
        "<h2>⏰ Просроченные матчи</h2>"
        "<table bordered striped><tr><th>ID</th><th>Матч</th><th>Турнир</th><th>Срок</th></tr>"
        + _deadline_rows(rows)
        + "</table><footer>ТП: /walkover #ID @loser. Продлить: /set_deadline #ID +24</footer>"
    )
    await _send_rich(update, rich, f"⏰ Просроченных матчей: {len(rows)}")


async def cmd_tournament_admin_rich(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t, err = _resolve_tournament_from_args(update, ctx)
    if not t:
        await send(update, err or "❌ Нет активного турнира.")
        return
    if not _can_manage_tournament(update.effective_user.id, t):
        await send(update, "❌ Только создатель или админ турнира.")
        return
    matches = get_tournament_matches(t["id"])
    pending = sum(1 for m in matches if m.get("status") == "pending")
    confirmed = sum(1 for m in matches if m.get("status") == "confirmed")
    rich = f"""
<h2>⚙️ Админ-панель: {html.escape(t['name'])}</h2>
<table bordered striped>
<tr><th>Настройка</th><th>Значение</th></tr>
<tr><td>ID</td><td>{t['id']}</td></tr>
<tr><td>Тип</td><td>{t_full_label(t)}</td></tr>
<tr><td>Стадия</td><td>{html.escape(str(t.get('stage') or '—'))}</td></tr>
<tr><td>Регистрация</td><td>{'открыта' if int(t.get('open_signup') or 0) else 'закрыта'}</td></tr>
<tr><td>Автоподтверждение</td><td>{'вкл' if int(t.get('auto_confirm') or 0) else 'выкл'}</td></tr>
<tr><td>Матчи</td><td>{confirmed} подтверждено / {pending} ожидает</td></tr>
</table>
<footer>/settings {t['id']} — полная панель настроек.</footer>
""".strip()
    await _send_rich(update, rich, f"⚙️ Админ-панель турнира {html.escape(t['name'])}")


async def cmd_violation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await send(update, "❌ Только админ.")
        return
    if len(ctx.args or []) < 2:
        await send(update, "Использование: <code>/violation @user причина</code>")
        return
    player = ctx.args[0]
    reason = " ".join(ctx.args[1:])
    rich = f"""
<h2>🚫 Нарушение регламента</h2>
<table bordered striped>
<tr><th>Пункт</th><th>Значение</th></tr>
<tr><td>Игрок</td><td>{html.escape(player)}</td></tr>
<tr><td>Нарушение</td><td>{html.escape(reason)}</td></tr>
<tr><td>Наказание</td><td>по решению организатора</td></tr>
</table>
<footer>См. /reglament для правил турнира.</footer>
""".strip()
    await _send_rich(update, rich, f"🚫 Нарушение: {html.escape(player)} — {html.escape(reason)}")


def _top_period_rows(days: int) -> list[dict]:
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT p.username, COUNT(*) AS games,
               SUM(CASE WHEN (m.player1_id=p.id AND m.score1>m.score2)
                         OR (m.player2_id=p.id AND m.score2>m.score1) THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN m.player1_id=p.id THEN m.score1 ELSE m.score2 END) AS goals
        FROM players p
        JOIN matches m ON (m.player1_id=p.id OR m.player2_id=p.id)
        WHERE m.status='confirmed' AND COALESCE(m.played_at, m.created_at) >= ?
        GROUP BY p.id, p.username
        ORDER BY wins DESC, goals DESC, games DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def _cmd_top_period(update: Update, days: int, title: str):
    rows = _top_period_rows(days)
    if not rows:
        await send(update, f"ℹ️ Нет подтверждённых матчей за период: {title}.")
        return
    trs = "".join(
        f"<tr><td>{i}</td><td>{mention(r['username'])}</td><td>{r['games']}</td><td>{r['wins'] or 0}</td><td>{r['goals'] or 0}</td></tr>"
        for i, r in enumerate(rows, 1)
    )
    rich = f"<h2>🏅 {title}</h2><table bordered striped><tr><th>#</th><th>Игрок</th><th>И</th><th>В</th><th>Г</th></tr>{trs}</table>"
    await _send_rich(update, rich, title)


async def cmd_top_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _cmd_top_period(update, 7, "Топ недели")


async def cmd_top_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _cmd_top_period(update, 30, "Топ месяца")


async def cmd_match_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    me = db.get_player_by_telegram_id(update.effective_user.id)
    if not me or not ctx.args:
        await send(update, "Использование: <code>/match_preview @opponent</code>")
        return
    opp = get_player(ctx.args[0].lstrip("@").lower())
    if not opp:
        await send(update, "❌ Соперник не найден.")
        return
    rich = f"""
<h2>🔎 Превью матча</h2>
<table bordered striped>
<tr><th>Игрок</th><th>ELO</th><th>В/Н/П</th><th>Голы</th></tr>
<tr><td>{mention(me['username'])}</td><td>{round(me['elo'])}</td><td>{me['wins']}/{me['draws']}/{me['losses']}</td><td>{me['goals_scored']}:{me['goals_conceded']}</td></tr>
<tr><td>{mention(opp['username'])}</td><td>{round(opp['elo'])}</td><td>{opp['wins']}/{opp['draws']}/{opp['losses']}</td><td>{opp['goals_scored']}:{opp['goals_conceded']}</td></tr>
</table>
""".strip()
    await _send_rich(update, rich, "🔎 Превью матча")


async def cmd_final_post_rich(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t, err = _resolve_tournament_from_args(update, ctx)
    if not t:
        await send(update, err or "❌ Нет турнира.")
        return
    podium = get_tournament_podium(t["id"])
    champion = _player_label(podium.get("first")) if podium else "—"
    second = _player_label(podium.get("second")) if podium else "—"
    third = _player_label(podium.get("third")) if podium and podium.get("third") else "—"
    rich = f"""
<h2>🏁 Итоги турнира: {html.escape(t['name'])}</h2>
<table bordered striped>
<tr><th>Место</th><th>Игрок</th></tr>
<tr><td>🥇 Чемпион</td><td>{champion}</td></tr>
<tr><td>🥈 Серебро</td><td>{second}</td></tr>
<tr><td>🥉 Бронза</td><td>{third}</td></tr>
</table>
<footer>Полная сетка: /playoff_text {t['id']}. Таблица: /table_text {t['id']}.</footer>
""".strip()
    await _send_rich(update, rich, f"🏁 Итоги турнира {html.escape(t['name'])}")


__all__ = [
    "cmd_match_card",
    "cmd_today",
    "cmd_overdue_rich",
    "cmd_tournament_admin_rich",
    "cmd_violation",
    "cmd_top_week",
    "cmd_top_month",
    "cmd_match_preview",
    "cmd_final_post_rich",
]
