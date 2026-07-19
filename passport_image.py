"""
Render a "Паспорт Гвардиолыча" (Guardiola's Passport) player card as PNG.

Public entry point: ``render_passport_png(player, trophy_counts, titles, notes,
avatar_bytes) -> bytes``
"""
from __future__ import annotations

import os as _os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from bg_helper import make_canvas
from emoji_helper import draw_text_with_emoji, measure_text_with_emoji, truncate_text_with_emoji


# ── palette ──────────────────────────────────────────────────────────────────
BG          = (20, 22, 30)
CARD_BG     = (30, 33, 42)
HEADER_BG   = (40, 65, 110)
HEADER_TXT  = (255, 255, 255)
TEXT        = (235, 238, 245)
MUTED       = (150, 160, 175)
ACCENT      = (255, 215, 0)
DIM_ACCENT  = (200, 170, 50)
SUBTLE      = (80, 90, 110)
GREEN       = (80, 200, 120)
RED         = (220, 80, 80)

SCALE = 2

AVATAR_SIZE = 90  # diameter at 1x


def _s(v: int) -> int:
    return int(v * SCALE)


# ── font cache ───────────────────────────────────────────────────────────────
_FONT_CACHE: dict[tuple[int, bool], ImageFont.ImageFont] = {}

_BOLD_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)
_REG_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    key = (size, bold)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    for path in (_BOLD_PATHS if bold else _REG_PATHS):
        try:
            f = ImageFont.truetype(path, size)
            _FONT_CACHE[key] = f
            return f
        except (OSError, IOError):
            continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _trunc(text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    return truncate_text_with_emoji(text, font, max_w, suffix="...")


def _draw_rounded_rect(
    img: Image.Image, draw: ImageDraw.ImageDraw,
    x: int, y: int, w: int, h: int, *,
    radius: int, fill: tuple, outline: tuple | None = None,
    width: int = 1, alpha: int = 255,
) -> None:
    if alpha >= 255:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                               fill=fill, outline=outline, width=width)
        return
    if alpha <= 0:
        if outline and width > 0:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                                   fill=None, outline=outline, width=width)
        return
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        [0, 0, w, h], radius=radius, fill=fill + (alpha,))
    img.paste(
        Image.alpha_composite(
            img.crop((x, y, x + w, y + h)).convert("RGBA"), overlay
        ).convert("RGB"), (x, y))
    if outline and width > 0:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                               fill=None, outline=outline, width=width)


def _draw_centered(
    img: Image.Image,
    cx: int, y: int, text: str, *,
    font: ImageFont.ImageFont,
    fill: tuple = TEXT,
) -> None:
    tw = measure_text_with_emoji(text, font)
    draw_text_with_emoji(img, (cx - tw // 2, y), text, font=font, fill=fill)


def _draw_circle_avatar(
    img: Image.Image,
    cx: int, cy: int, radius: int,
    avatar_bytes: bytes | None,
) -> None:
    diam = radius * 2
    if avatar_bytes:
        try:
            av = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            av = av.resize((diam, diam), Image.LANCZOS)
            mask = Image.new("L", (diam, diam), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, diam, diam], fill=255)
            av.putalpha(mask)
            img.paste(av, (cx - radius, cy - radius), av)
            return
        except Exception:
            pass
    temp = Image.new("RGBA", (diam, diam), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.ellipse([0, 0, diam, diam], fill=SUBTLE)
    name_f = _font(_s(28), bold=True)
    temp_draw.text((diam // 2, diam // 2), "?", font=name_f,
                   fill=MUTED, anchor="mm")
    img.paste(temp, (cx - radius, cy - radius), temp)


# ── public API ───────────────────────────────────────────────────────────────

def render_passport_png(
    player: dict,
    trophy_counts: dict[str, int],
    titles: list[str],
    notes: list[dict],
    avatar_bytes: bytes | None = None,
    style: str = "mclovin",
) -> bytes:
    if style in ("mafia", "mclovin"):
        return _render_passport_mafia_png(
            player, trophy_counts, titles, notes, avatar_bytes,
        )
    return _render_passport_default_png(
        player, trophy_counts, titles, notes, avatar_bytes,
    )


def _render_passport_default_png(
    player: dict,
    trophy_counts: dict[str, int],
    titles: list[str],
    notes: list[dict],
    avatar_bytes: bytes | None = None,
) -> bytes:
    w = _s(440)
    h = _s(780)

    pid = player.get("id", 0)
    username = player.get("username", "unknown") or "unknown"
    game_nick = player.get("game_nickname") or ""
    elo = float(player.get("elo") or 0)
    w_ = int(player.get("wins") or 0)
    l_ = int(player.get("losses") or 0)
    d_ = int(player.get("draws") or 0)
    gf = int(player.get("goals_scored") or 0)
    ga = int(player.get("goals_conceded") or 0)
    raw_reg = player.get("registered_at")
    if isinstance(raw_reg, str):
        reg = raw_reg[:10]
    elif hasattr(raw_reg, "strftime"):
        reg = raw_reg.strftime("%Y-%m-%d")
    else:
        reg = str(raw_reg or "")[:10]

    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    _draw_rounded_rect(img, draw, _s(12), _s(12), w - _s(24), h - _s(24),
                       radius=_s(20), fill=CARD_BG)

    # ── Subtle background decoration ─────────────────────────────────────
    deco = _font(_s(60), bold=True)
    _draw_centered(img, w // 2, _s(360), "GP", font=deco, fill=(28, 30, 40))

    # ── Header band ──────────────────────────────────────────────────────
    _draw_rounded_rect(img, draw, _s(12), _s(12), w - _s(24), _s(70),
                       radius=_s(20), fill=HEADER_BG)
    draw.rounded_rectangle(
        [_s(12), _s(50), w - _s(12), _s(70)],
        radius=0, fill=HEADER_BG)
    header_font = _font(_s(28), bold=True)
    _draw_centered(img, w // 2, _s(24), "ПАСПОРТ ГВАРДИОЛЫЧА",
                   font=header_font, fill=HEADER_TXT)
    sub_font = _font(_s(12), bold=False)
    _draw_centered(img, w // 2, _s(52), "FC Mobile League",
                   font=sub_font, fill=MUTED)

    # ── Avatar ───────────────────────────────────────────────────────────
    av_cx = w // 2
    av_cy = _s(135)
    av_r = _s(AVATAR_SIZE // 2)
    draw.ellipse([av_cx - av_r - _s(3), av_cy - av_r - _s(3),
                  av_cx + av_r + _s(3), av_cy + av_r + _s(3)],
                 outline=ACCENT, width=_s(3))
    _draw_circle_avatar(img, av_cx, av_cy, av_r, avatar_bytes)

    # ── ID badge ─────────────────────────────────────────────────────────
    id_y = _s(195)
    id_font = _font(_s(14), bold=True)
    id_str = f"#{pid}"
    id_bg_w = measure_text_with_emoji(id_str, id_font) + _s(16)
    id_bg_x = w // 2 - id_bg_w // 2
    _draw_rounded_rect(img, draw, id_bg_x, id_y - _s(2),
                       id_bg_w, _s(26), radius=_s(13), fill=SUBTLE)
    _draw_centered(img, w // 2, id_y, id_str, font=id_font, fill=ACCENT)

    # ── Username ─────────────────────────────────────────────────────────
    name_y = _s(235)
    name_font = _font(_s(22), bold=True)
    _draw_centered(img, w // 2, name_y, f"@{username}", font=name_font, fill=TEXT)

    if game_nick:
        nick_y = name_y + _s(30)
        nick_font = _font(_s(15), bold=False)
        _draw_centered(img, w // 2, nick_y, f"«{game_nick}»",
                       font=nick_font, fill=MUTED)

    # ── Divider ──────────────────────────────────────────────────────────
    div_y = _s(290)
    draw.line([_s(40), div_y, w - _s(40), div_y], fill=SUBTLE, width=_s(1))

    # ── Stats row ────────────────────────────────────────────────────────
    stat_y = div_y + _s(16)
    stat_font = _font(_s(14), bold=False)
    stat_val_font = _font(_s(18), bold=True)

    cols = [
        ("ELO", str(int(elo))),
        ("W / L / D", f"{w_}/{l_}/{d_}"),
        ("GF/GA", f"{gf}/{ga}"),
    ]
    col_w = w // 3
    for i, (label, value) in enumerate(cols):
        cx = col_w // 2 + col_w * i
        draw_text_with_emoji(img, (cx, stat_y), label, font=stat_font, fill=MUTED)
        draw_text_with_emoji(img, (cx, stat_y + _s(22)), value,
                             font=stat_val_font, fill=TEXT)

    # ── Trophies ─────────────────────────────────────────────────────────
    trop_y = stat_y + _s(65)
    trop_font = _font(_s(14), bold=False)
    trop_val_font = _font(_s(14), bold=True)
    type_labels = {"main": "Чемпион", "vsa": "VSA",
                   "fantasy": "Фэнтези", "supercup": "Суперкубок"}
    trop_items = []
    total_trophies = 0
    for ttype, tlabel in type_labels.items():
        cnt = trophy_counts.get(ttype, 0)
        if cnt > 0:
            trop_items.append((tlabel, cnt))
            total_trophies += cnt

    if trop_items:
        _draw_centered(img, w // 2, trop_y, "— ТРОФЕИ —",
                       font=_font(_s(13)), fill=MUTED)
        row_y = trop_y + _s(22)
        per_row = 2
        for idx, (tlabel, cnt) in enumerate(trop_items):
            col = idx % per_row
            row = idx // per_row
            cx = w // (per_row * 2) + col * (w // per_row)
            cy = row_y + row * _s(28)
            line = f"  {tlabel}: "
            lw = measure_text_with_emoji(line, trop_font)
            draw_text_with_emoji(img, (cx, cy), line, font=trop_font, fill=MUTED)
            draw_text_with_emoji(img, (cx + lw, cy), str(cnt),
                                 font=trop_val_font, fill=ACCENT)
    else:
        _draw_centered(img, w // 2, trop_y + _s(8),
                       "Пока нет трофеев", font=_font(_s(13)), fill=MUTED)

    # ── Titles / badges ──────────────────────────────────────────────────
    badge_y = trop_y + _s(75)
    if titles:
        _draw_centered(img, w // 2, badge_y, "— ЗВАНИЯ —",
                       font=_font(_s(13)), fill=MUTED)
        b_font = _font(_s(12), bold=False)
        b_y = badge_y + _s(22)
        badge_text = " • ".join(titles[:4])
        if len(titles) > 4:
            badge_text += f" … +{len(titles) - 4}"
        bt = _trunc(badge_text, b_font, w - _s(60))
        _draw_centered(img, w // 2, b_y, bt, font=b_font, fill=TEXT)

    # ── Notes ────────────────────────────────────────────────────────────
    note_base_y = badge_y + _s(50) if titles else badge_y + _s(30)
    if notes:
        _draw_centered(img, w // 2, note_base_y, "— ЗАМЕТКИ —",
                       font=_font(_s(13)), fill=MUTED)
        n_font = _font(_s(12), bold=False)
        n_y = note_base_y + _s(22)
        for note in notes[:3]:
            au = note.get("author_username", "?") or "?"
            nt = (note.get("note_text", "") or "")[:50]
            line = f"  \"{nt}\" — @{au}"
            lt = _trunc(line, n_font, w - _s(60))
            draw_text_with_emoji(img, (_s(30), n_y), lt, font=n_font, fill=TEXT)
            n_y += _s(19)
    else:
        _draw_centered(img, w // 2, note_base_y + _s(8),
                       "Пока нет заметок", font=_font(_s(12)), fill=MUTED)

    # ── Footer ───────────────────────────────────────────────────────────
    foot_font = _font(_s(10), bold=False)
    _draw_centered(img, w // 2, h - _s(20),
                   f"Зарегистрирован: {reg}", font=foot_font, fill=MUTED)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── McLovin (mafia) style ─────────────────────────────────────────────────────
# Horizontal ID card inspired by the McLovin fake ID from Superbad.
ML_BG_TOP    = (20, 80, 160)
ML_BG_BOT    = (10, 50, 120)
ML_ACCENT    = (255, 200, 50)
ML_GOLD      = (200, 160, 30)
ML_CARD_BG   = (240, 240, 245)
ML_TEXT      = (20, 20, 30)
ML_MUTED     = (100, 110, 130)
ML_FIELD     = (180, 185, 195)


def _draw_gradient_bar(img: Image.Image, y: int, h: int,
                       color_top: tuple, color_bot: tuple) -> None:
    w = img.width
    for row in range(h):
        t = row / max(h - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        draw = ImageDraw.Draw(img)
        draw.line([(0, y + row), (w, y + row)], fill=(r, g, b))


def _render_passport_mafia_png(
    player: dict,
    trophy_counts: dict[str, int],
    titles: list[str],
    notes: list[dict],
    avatar_bytes: bytes | None = None,
) -> bytes:
    CARD_W = _s(720)
    CARD_H = _s(450)
    w = CARD_W + _s(24)
    h = CARD_H + _s(24)

    pid = player.get("id", 0)
    username = player.get("username", "unknown") or "unknown"
    game_nick = player.get("game_nickname") or ""
    elo = float(player.get("elo") or 0)
    w_ = int(player.get("wins") or 0)
    l_ = int(player.get("losses") or 0)
    d_ = int(player.get("draws") or 0)
    gf = int(player.get("goals_scored") or 0)
    ga = int(player.get("goals_conceded") or 0)
    raw_reg = player.get("registered_at")
    if isinstance(raw_reg, str):
        reg = raw_reg[:10]
    elif hasattr(raw_reg, "strftime"):
        reg = raw_reg.strftime("%Y-%m-%d")
    else:
        reg = str(raw_reg or "")[:10]

    total_trophies = sum(trophy_counts.values())

    img = make_canvas(w, h, bg_color=(10, 10, 14),
                      bg_image_path="assets/passport_bg.jpg",
                      overlay_alpha=120)
    draw = ImageDraw.Draw(img)

    # ── Card body with gradient top bar ───────────────────────────────────
    cx = _s(12)
    cy_card = _s(12)
    _draw_rounded_rect(img, draw, cx, cy_card, CARD_W, CARD_H,
                       radius=_s(16), fill=ML_CARD_BG, alpha=215)
    # Blue gradient top band
    bar_h = _s(90)
    _draw_gradient_bar(img, cy_card, bar_h, ML_BG_TOP, ML_BG_BOT)
    # Gold bottom border on bar
    draw.rectangle([cx, cy_card + bar_h - _s(3), cx + CARD_W, cy_card + bar_h],
                   fill=ML_GOLD)

    # ── Header ───────────────────────────────────────────────────────────
    header_font = _font(_s(26), bold=True)
    _draw_centered(img, cx + CARD_W // 2, cy_card + _s(18),
                   "GUARDIOLA LEAGUE", font=header_font, fill=(255, 255, 255))
    sub_font = _font(_s(12), bold=False)
    _draw_centered(img, cx + CARD_W // 2, cy_card + _s(52),
                   "ИДЕНТИФИКАЦИОННАЯ КАРТА • OFFICIAL ID",
                   font=sub_font, fill=(200, 215, 240))
    _draw_centered(img, cx + CARD_W // 2, cy_card + _s(70),
                   f"#{pid}", font=_font(_s(13), bold=True), fill=ML_GOLD)

    # ── Photo (left side) ────────────────────────────────────────────────
    photo_x = cx + _s(30)
    photo_y = cy_card + _s(110)
    photo_w = _s(140)
    photo_h = _s(180)

    # Photo background
    _draw_rounded_rect(img, draw, photo_x, photo_y, photo_w, photo_h,
                       radius=_s(8), fill=(220, 225, 235))
    # Gold border around photo
    draw.rounded_rectangle([photo_x, photo_y, photo_x + photo_w, photo_y + photo_h],
                           radius=_s(8), outline=ML_GOLD, width=_s(3))

    # Avatar inside photo area
    av_cy = photo_y + photo_h // 2 - _s(5)
    av_cx = photo_x + photo_w // 2
    av_r = _s(50)
    _draw_circle_avatar(img, av_cx, av_cy, av_r, avatar_bytes)
    # Under-photo label
    _draw_centered(img, av_cx, photo_y + photo_h - _s(18),
                   f"@{username}", font=_font(_s(9)), fill=ML_MUTED)

    # ── Info fields (right side) ─────────────────────────────────────────
    info_x = photo_x + photo_w + _s(24)
    field_w = cx + CARD_W - info_x - _s(24)
    row_y = photo_y

    def _field(label: str, value: str, y: int) -> int:
        f_font = _font(_s(9), bold=False)
        v_font = _font(_s(16), bold=True)
        draw_text_with_emoji(img, (info_x, y), label, font=f_font, fill=ML_MUTED)
        vy = y + _s(14)
        draw_text_with_emoji(img, (info_x, vy), value, font=v_font, fill=ML_TEXT)
        return vy + _s(32)

    row_y = _field("NAME / ИМЯ", game_nick or username, row_y) + _s(2)
    row_y = _field("ALIAS / КЛИЧКА", f"@{username}", row_y)
    row_y = _field("STATUS / СТАТУС", f"ELO {int(elo)}", row_y)

    # Trophies as fake "CRIMES / НАРУШЕНИЯ"
    crimes = ", ".join(
        f"{v}x{k}" for k, v in [("Чемпион", trophy_counts.get("main", 0)),
                                 ("VSA", trophy_counts.get("vsa", 0)),
                                 ("Фэнтези", trophy_counts.get("fantasy", 0)),
                                 ("СК", trophy_counts.get("supercup", 0))]
        if v > 0
    ) or "Нет"
    row_y = _field("CRIMES / НАРУШЕНИЯ", crimes, row_y)

    # W/L/D
    row_y = _field("W / L / D", f"{w_}/{l_}/{d_}", row_y)

    # Titles
    if titles:
        joined = " • ".join(titles[:3])
        if len(titles) > 3:
            joined += f" +{len(titles) - 3}"
    else:
        joined = "—"
    t_y = row_y + _s(6)
    f_font = _font(_s(9))
    draw_text_with_emoji(img, (info_x, t_y), "BADGES / ЗВАНИЯ",
                         font=f_font, fill=ML_MUTED)
    draw_text_with_emoji(img, (info_x, t_y + _s(14)), joined,
                         font=_font(_s(11), bold=False), fill=ML_TEXT)

    # ── Notes below photo ────────────────────────────────────────────────
    note_y = photo_y + photo_h + _s(16)
    line_h = _s(18)
    if notes:
        n_font = _font(_s(10), bold=False)
        _draw_centered(img, cx + CARD_W // 2, note_y, "— NOTES / ЗАМЕТКИ —",
                       font=_font(_s(9)), fill=ML_MUTED)
        ny = note_y + _s(16)
        for note in notes[:2]:
            au = note.get("author_username", "?") or "?"
            nt = (note.get("note_text", "") or "")[:45]
            line = f"  \"{nt}\" — @{au}"
            lt = _trunc(line, n_font, CARD_W - _s(60))
            draw_text_with_emoji(img, (_s(24), ny), lt, font=n_font, fill=ML_TEXT)
            ny += line_h
    else:
        _draw_centered(img, cx + CARD_W // 2, note_y + _s(8),
                       "Нет заметок", font=_font(_s(10)), fill=ML_MUTED)

    # ── Footer bar ───────────────────────────────────────────────────────
    foot_y = cy_card + CARD_H - _s(28)
    draw.rectangle([cx, foot_y, cx + CARD_W, cy_card + CARD_H],
                   fill=ML_BG_TOP)
    _draw_centered(img, cx + CARD_W // 2, foot_y + _s(4),
                   f"ISSUED / ВЫДАН: {reg}   |   CLASS: M-LEAGUE",
                   font=_font(_s(10), bold=True), fill=(255, 255, 255))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
