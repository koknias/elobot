"""
Render a "Паспорт Гвардиолыча" (Guardiola's Passport) player card as PNG.

Public entry point: ``render_passport_png(player, trophy_counts, titles, notes,
avatar_bytes, style) -> bytes``

Styles:
  * ``default`` / ``book`` — паспорт-книжка (базовый стиль, используется по
    умолчанию командой ``/passport``): бордовая обложка с золотым гербом,
    фото в рамке, поля как у настоящего паспорта и машиночитаемая зона MRZ.
  * ``mafia`` / ``mclovin`` — горизонтальная ID-карта в стиле McLovin.
"""
from __future__ import annotations

import os as _os
import re
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
    style: str = "book",
) -> bytes:
    if style in ("mafia", "mclovin"):
        return _render_passport_mafia_png(
            player, trophy_counts, titles, notes, avatar_bytes,
        )
    if style == "card":
        return _render_passport_card_png(
            player, trophy_counts, titles, notes, avatar_bytes,
        )
    return _render_passport_book_png(
        player, trophy_counts, titles, notes, avatar_bytes,
    )


def _render_passport_card_png(
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


# ── Passport-book style (базовый) ────────────────────────────────────────────
# Классический паспорт-книжка: бордовая обложка с золотым гербом и тиснением,
# страница с фото в овальной/прямоугольной рамке, полями как у настоящего
# паспорта и машиночитаемой зоной (MRZ) в самом низу.

PB_COVER     = (58, 30, 42)   # тёмный бордо обложки
PB_COVER_DK  = (38, 18, 28)   # глубокая тень обложки
PB_PAGE      = (246, 240, 226)  # тёплая бумажная страница
PB_PAGE_DK   = (230, 222, 204)  # затенение страницы (корешок)
PB_GOLD      = (212, 175, 55)  # золотое тиснение
PB_GOLD_DK   = (160, 128, 35)
PB_INK       = (48, 36, 36)    # цвет типографской краски
PB_INK_SOFT  = (110, 88, 80)
PB_FIELD_LBL = (120, 100, 90)
PB_STAMP     = (150, 40, 40)   # красный штамп


def _emboss_label(img: Image.Image,
                  cx: int, y: int, text: str, *,
                  font: ImageFont.ImageFont,
                  fill: tuple,
                  shadow: tuple | None = None) -> None:
    """Imitation of gold letterpress: faint shadow + main fill."""
    if shadow is not None:
        tw = measure_text_with_emoji(text, font)
        draw_text_with_emoji(img, (cx - tw // 2 + _s(1), y + _s(1)),
                             text, font=font, fill=shadow)
    _draw_centered(img, cx, y, text, font=font, fill=fill)


def _book_emblem(img: Image.Image, cx: int, cy: int, r: int) -> None:
    """Герб на обложке: настоящая эмблема лиги в круглом золотом медальоне,
    либо (если файл эмблемы недоступен) запасной рисованный герб."""
    emblem = _load_emblem()
    if emblem is None:
        _book_emblem_fallback(img, cx, cy, r)
        return
    # Вписываем квадратную эмблему в круг радиуса r, оставляя золотое кольцо.
    inner_r = r - _s(4)
    diam = inner_r * 2
    medallion = emblem.resize((diam, diam), Image.LANCZOS)
    # Круглая маска со сглаженным краем
    mask = Image.new("L", (diam, diam), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diam - 1, diam - 1], fill=255)
    medallion.putalpha(mask)
    img.paste(medallion, (cx - inner_r, cy - inner_r), medallion)
    # Внешнее золотое кольцо-кант
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - r, cy - r, cx + r - 1, cy + r - 1],
                 outline=PB_GOLD, width=_s(3))
    draw.ellipse([cx - r + _s(2), cy - r + _s(2),
                  cx + r - _s(2) - 1, cy + r - _s(2) - 1],
                 outline=PB_GOLD_DK, width=1)


_EMBLEM_CACHE: Image.Image | None = None
_EMBLEM_TRIED = False


def _load_emblem() -> Image.Image | None:
    """Центральный квадратный кроп эмблемы лиги (RGBA). Кэшируется."""
    global _EMBLEM_CACHE, _EMBLEM_TRIED
    if _EMBLEM_TRIED:
        return _EMBLEM_CACHE
    _EMBLEM_TRIED = True
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                         "assets", "gvardiol_emblem.png")
    try:
        with Image.open(path) as src:
            src = src.convert("RGB")
        w, h = src.size
        s = min(w, h)
        left, top = (w - s) // 2, (h - s) // 2
        _EMBLEM_CACHE = src.crop((left, top, left + s, top + s))
    except Exception:
        _EMBLEM_CACHE = None
    return _EMBLEM_CACHE


def _book_emblem_fallback(img: Image.Image, cx: int, cy: int, r: int) -> None:
    """Запасной герб, если файл эмблемы недоступен: круг + ромб + звезда."""
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=PB_GOLD, width=_s(3))
    rh = int(r * 0.62)
    draw.polygon([(cx, cy - rh), (cx + rh, cy),
                  (cx, cy + rh), (cx - rh, cy)],
                 outline=PB_GOLD, width=_s(2))
    _draw_star(draw, cx, cy, int(r * 0.42), points=5,
               fill=PB_GOLD, outline=PB_GOLD_DK)


def _draw_star(draw: ImageDraw.ImageDraw,
               cx: int, cy: int, r: int, *,
               points: int = 5,
               fill: tuple = PB_GOLD,
               outline: tuple | None = None) -> None:
    import math
    pts = []
    for i in range(points * 2):
        angle = -math.pi / 2 + i * math.pi / points
        radius = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(angle) * radius,
                    cy + math.sin(angle) * radius))
    draw.polygon(pts, fill=fill, outline=outline)


def _mrz_block(player: dict, pid: int) -> list[str]:
    """Две строки машиночитаемой зоны (ICAO-подобный формат, безопасный для PIL)."""
    def ascii_pad(s: str, n: int) -> str:
        s = re.sub(r"[^A-Z0-9<]", "<", (s or "").upper())
        return (s + "<" * n)[:n]

    country = "GL"            # GUARDIOLA LEAGUE
    doc = ascii_pad(f"GP{pid:05d}", 9)
    name = ascii_pad((player.get("game_nickname") or player.get("username") or "PLAYER"),
                     0)
    surname = ascii_pad("GUARDIOLA", 0)
    holder = f"{surname}<<{name}"

    line1 = f"{country}{doc}<<<<<<<<<<<<<<<"[:44]
    line2 = (ascii_pad("", 0) + "<<" + holder + "<<<<<<<<<<<<<<<<<<<<<<<<")[:44]
    # Гарантируем ровно 44 символа в каждой строке.
    line1 = (line1 + "<" * 44)[:44]
    line2 = (line2 + "<" * 44)[:44]
    return [line1, line2]


def _render_passport_book_png(
    player: dict,
    trophy_counts: dict[str, int],
    titles: list[str],
    notes: list[dict],
    avatar_bytes: bytes | None = None,
) -> bytes:
    """Базовый стиль — паспорт-книжка с обложкой и разворотом страницы."""
    CARD_W = _s(760)
    CARD_H = _s(540)
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

    img = Image.new("RGB", (w, h), (24, 22, 22))
    draw = ImageDraw.Draw(img)

    ox = _s(12)
    oy = _s(12)

    # ── Обложка (левая страница) ─────────────────────────────────────────
    cover_w = CARD_W // 2 - _s(6)
    cover_x = ox
    cover_y = oy
    _draw_rounded_rect(img, draw, cover_x, cover_y, cover_w, CARD_H,
                       radius=_s(10), fill=PB_COVER)
    # Текстура: тонкие диагональные линии для «бархата»
    for i in range(-CARD_H, cover_w, _s(8)):
        draw.line([(cover_x + i, cover_y),
                   (cover_x + i + CARD_H, cover_y + CARD_H)],
                  fill=PB_COVER_DK, width=1)

    # Внутренняя золотая рамка обложки
    inset = _s(14)
    draw.rounded_rectangle(
        [cover_x + inset, cover_y + inset,
         cover_x + cover_w - inset, cover_y + CARD_H - inset],
        radius=_s(6), outline=PB_GOLD, width=_s(2))
    draw.rounded_rectangle(
        [cover_x + inset + _s(4), cover_y + inset + _s(4),
         cover_x + cover_w - inset - _s(4), cover_y + CARD_H - inset - _s(4)],
        radius=_s(4), outline=PB_GOLD_DK, width=1)

    cover_cx = cover_x + cover_w // 2
    # Герб
    _book_emblem(img, cover_cx, cover_y + _s(110), _s(42))
    # Надписи на обложке
    cover_title_f = _font(_s(26), bold=True)
    _emboss_label(img, cover_cx, cover_y + _s(180), "GUARDIOLA",
                  font=cover_title_f, fill=PB_GOLD, shadow=PB_GOLD_DK)
    _emboss_label(img, cover_cx, cover_y + _s(212), "LEAGUE",
                  font=cover_title_f, fill=PB_GOLD, shadow=PB_GOLD_DK)
    sub_f = _font(_s(12), bold=False)
    _draw_centered(img, cover_cx, cover_y + _s(246),
                   "ПАСПОРТ ГВАРДИОЛЫЧА", font=sub_f, fill=PB_GOLD_DK)
    _draw_centered(img, cover_cx, cover_y + _s(264),
                   "FC MOBILE LEAGUE", font=_font(_s(10)), fill=PB_GOLD_DK)
    _draw_centered(img, cover_cx, cover_y + _s(280),
                   "OFFICIAL PLAYER PASSPORT", font=_font(_s(9)),
                   fill=PB_GOLD_DK)

    # Нижний блок обложки: номер документа
    draw.line([(cover_x + inset + _s(20), cover_y + CARD_H - _s(78)),
               (cover_x + cover_w - inset - _s(20), cover_y + CARD_H - _s(78))],
              fill=PB_GOLD_DK, width=1)
    _draw_centered(img, cover_cx, cover_y + CARD_H - _s(62),
                   "PASSPORT • ПАСПОРТ", font=_font(_s(9)), fill=PB_GOLD_DK)
    doc_str = f"№ GL{pid:05d}"
    doc_f = _font(_s(18), bold=True)
    _emboss_label(img, cover_cx, cover_y + CARD_H - _s(44), doc_str,
                  font=doc_f, fill=PB_GOLD, shadow=PB_GOLD_DK)

    # Тёмный «корешок» между страницами
    spine_x = cover_x + cover_w
    draw.rectangle([spine_x, cover_y, spine_x + _s(12), cover_y + CARD_H],
                   fill=PB_COVER_DK)
    for sx in range(_s(12)):
        shade = 30 + int(20 * abs(sx - _s(6)) / max(_s(6), 1))
        draw.line([(spine_x + sx, cover_y), (spine_x + sx, cover_y + CARD_H)],
                  fill=(PB_COVER_DK[0] + shade,
                        PB_COVER_DK[1] + shade,
                        PB_COVER_DK[2] + shade))

    # ── Страница (правая) ────────────────────────────────────────────────
    page_x = spine_x + _s(12)
    page_w = ox + CARD_W - page_x
    page_y = oy
    _draw_rounded_rect(img, draw, page_x, page_y, page_w, CARD_H,
                       radius=_s(10), fill=PB_PAGE)
    # Лёгкая тень от корешка на странице
    for sx in range(_s(14)):
        a = int(60 * (1 - sx / _s(14)))
        _vline_alpha(img, page_x + sx, page_y, CARD_H, (0, 0, 0), a)

    # Шапка страницы
    head_f = _font(_s(13), bold=True)
    _draw_centered(img, page_x + page_w // 2, page_y + _s(18),
                   "GUARDIOLA LEAGUE", font=head_f, fill=PB_INK)
    _draw_centered(img, page_x + page_w // 2, page_y + _s(34),
                   "РЕСПУБЛИКА ГВАРДИОЛА • OFFICIAL ID",
                   font=_font(_s(9)), fill=PB_INK_SOFT)
    draw.line([(page_x + _s(20), page_y + _s(52)),
               (page_x + page_w - _s(20), page_y + _s(52))],
              fill=PB_GOLD_DK, width=1)

    # ── Фото (слева на странице) в прямоугольной рамке ───────────────────
    photo_x = page_x + _s(24)
    photo_y = page_y + _s(68)
    photo_w = _s(120)
    photo_h = _s(150)
    _draw_rounded_rect(img, draw, photo_x, photo_y, photo_w, photo_h,
                       radius=_s(4), fill=(225, 220, 205))
    draw.rectangle([photo_x, photo_y, photo_x + photo_w, photo_y + photo_h],
                   outline=PB_INK, width=_s(2))
    # Внутренняя золотая окантовка фото
    draw.rectangle([photo_x + _s(2), photo_y + _s(2),
                    photo_x + photo_w - _s(2), photo_y + photo_h - _s(2)],
                   outline=PB_GOLD_DK, width=1)
    av_r = min(photo_w, photo_h) // 2 - _s(8)
    _draw_circle_avatar(img,
                        photo_x + photo_w // 2,
                        photo_y + photo_h // 2 - _s(4),
                        av_r, avatar_bytes)
    # Подпись под фото
    _draw_centered(img, photo_x + photo_w // 2, photo_y + photo_h + _s(6),
                   "PHOTO / ФОТО", font=_font(_s(8)), fill=PB_FIELD_LBL)

    # ── Поля справа от фото ──────────────────────────────────────────────
    fx = photo_x + photo_w + _s(22)
    fy = photo_y
    field_w = page_x + page_w - fx - _s(20)

    def _field(label: str, value: str, y: int, *,
               v_font_size: int = _s(13)) -> int:
        draw_text_with_emoji(img, (fx, y), label,
                             font=_font(_s(8), bold=True), fill=PB_FIELD_LBL)
        draw.line([(fx, y + _s(22)), (fx + field_w, y + _s(22))],
                  fill=PB_INK_SOFT, width=1)
        vt = _trunc(value, _font(v_font_size, bold=True), field_w)
        draw_text_with_emoji(img, (fx, y + _s(8)), vt,
                             font=_font(v_font_size, bold=True), fill=PB_INK)
        return y + _s(34)

    fy = _field("SURNAME / ФАМИЛИЯ", "GUARDIOLA", fy)
    fy = _field("GIVEN NAMES / ИМЯ", game_nick or username, fy)
    fy = _field("NATIONALITY / ГРАЖДАНСТВО", "GUARDIOLA LEAGUE", fy,
                v_font_size=_s(11))
    fy = _field("PASSPORT № / НОМЕР", f"GL{pid:05d}", fy)

    # ── Нижний блок страницы: статы + трофеи ─────────────────────────────
    stat_y = photo_y + photo_h + _s(36)
    draw.line([(page_x + _s(20), stat_y - _s(8)),
               (page_x + page_w - _s(20), stat_y - _s(8))],
              fill=PB_GOLD_DK, width=1)

    stat_lbl_f = _font(_s(8), bold=True)
    stat_val_f = _font(_s(15), bold=True)
    cols = [
        ("ELO", str(int(elo))),
        ("W/L/D", f"{w_}/{l_}/{d_}"),
        ("GF/GA", f"{gf}/{ga}"),
        ("CUPS", str(total_trophies)),
    ]
    col_w = (page_w - _s(40)) // len(cols)
    for i, (label, value) in enumerate(cols):
        cx = page_x + _s(20) + col_w // 2 + col_w * i
        _draw_centered(img, cx, stat_y, label,
                       font=stat_lbl_f, fill=PB_FIELD_LBL)
        _draw_centered(img, cx, stat_y + _s(14), value,
                       font=stat_val_f, fill=PB_INK)

    # Трофеи строкой
    trop_y = stat_y + _s(44)
    type_labels = {"main": "Чемпион", "vsa": "VSA",
                   "fantasy": "Фэнтези", "supercup": "СК"}
    trop_items = [(type_labels[t], trophy_counts.get(t, 0))
                  for t in type_labels if trophy_counts.get(t, 0) > 0]
    trop_str = "  •  ".join(f"{lbl} ×{c}" for lbl, c in trop_items) or "—"
    draw_text_with_emoji(img, (page_x + _s(20), trop_y),
                         "ТРОФЕИ / TROPHIES",
                         font=_font(_s(8), bold=True), fill=PB_FIELD_LBL)
    trop_val_f = _font(_s(11), bold=True)
    tt = _trunc(trop_str, trop_val_f, page_w - _s(40))
    draw_text_with_emoji(img, (page_x + _s(20), trop_y + _s(12)), tt,
                         font=trop_val_f, fill=PB_INK)

    # Звания
    if titles:
        badge_y = trop_y + _s(34)
        draw_text_with_emoji(img, (page_x + _s(20), badge_y),
                             "ЗВАНИЯ / BADGES",
                             font=_font(_s(8), bold=True), fill=PB_FIELD_LBL)
        b_font = _font(_s(10), bold=False)
        bt = _trunc(" • ".join(titles[:5]), b_font, page_w - _s(40))
        draw_text_with_emoji(img, (page_x + _s(20), badge_y + _s(12)), bt,
                             font=b_font, fill=PB_INK)

    # ── Заметки (мини-блок) + печать ─────────────────────────────────────
    notes_y = page_y + CARD_H - _s(120)
    # Заметки занимают левую часть, печать — правую; они не пересекаются.
    notes_w = page_w - _s(40) - _s(80)
    if notes:
        n_font = _font(_s(9), bold=False)
        _draw_centered(img, page_x + notes_w // 2 + _s(10), notes_y,
                       "— ЗАМЕТКИ / NOTES —", font=_font(_s(8), bold=True),
                       fill=PB_FIELD_LBL)
        ny = notes_y + _s(12)
        for note in notes[:2]:
            au = note.get("author_username", "?") or "?"
            nt = (note.get("note_text", "") or "")[:40]
            line = f"“{nt}” — @{au}"
            lt = _trunc(line, n_font, notes_w)
            draw_text_with_emoji(img, (page_x + _s(20), ny), lt,
                                 font=n_font, fill=PB_INK_SOFT)
            ny += _s(14)

    # Круглая «печать» в правой части страницы, на уровне заметок.
    _draw_stamp(img, page_x + page_w - _s(48),
                notes_y + _s(20), _s(26))

    # ── Машиночитаемая зона (MRZ) ────────────────────────────────────────
    mrz_lines = _mrz_block(player, pid)
    mrz_y = page_y + CARD_H - _s(48)
    draw.line([(page_x + _s(20), mrz_y - _s(6)),
               (page_x + page_w - _s(20), mrz_y - _s(6))],
              fill=PB_GOLD_DK, width=1)
    # Шрифт подбираем так, чтобы 44 символа точно вошли в ширину страницы.
    mrz_avail = page_w - _s(40)
    mrz_f = _font(_s(9), bold=True)
    mrz_line_h = _s(14)
    # Подстраиваем размер вниз, если строка всё ещё шире доступной ширины.
    for size in (_s(9), _s(8), _s(7)):
        f = _font(size, bold=True)
        if measure_text_with_emoji(mrz_lines[0], f) <= mrz_avail:
            mrz_f, mrz_line_h = f, size + _s(4)
            break
    for i, line in enumerate(mrz_lines):
        draw.text((page_x + _s(20), mrz_y + i * mrz_line_h), line,
                  font=mrz_f, fill=PB_INK)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _vline_alpha(img: Image.Image, x: int, y: int, height: int,
                 color: tuple, alpha: int) -> None:
    """Вертикальная полупрозрачная линия (для мягких теней на странице)."""
    if alpha <= 0:
        return
    overlay = Image.new("RGBA", (1, height), color + (alpha,))
    img.paste(Image.alpha_composite(
        img.crop((x, y, x + 1, y + height)).convert("RGBA"), overlay
    ).convert("RGB"), (x, y))


def _draw_stamp(img: Image.Image, cx: int, cy: int, r: int) -> None:
    """Полупрозрачная круглая «печать» с надписью — эффект штампа approval."""
    layer = Image.new("RGBA", (r * 2 + _s(8), r * 2 + _s(8)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    gcx = layer.width // 2
    gcy = layer.height // 2
    d.ellipse([gcx - r, gcy - r, gcx + r, gcy + r],
              outline=PB_STAMP + (180,), width=_s(2))
    d.ellipse([gcx - r + _s(4), gcy - r + _s(4),
               gcx + r - _s(4), gcy + r - _s(4)],
              outline=PB_STAMP + (140,), width=1)
    f = _font(_s(8), bold=True)
    txt = "APPROVED"
    tw = measure_text_with_emoji(txt, f)
    draw_text_with_emoji(layer, (gcx - tw // 2, gcy - _s(4)), txt,
                         font=f, fill=PB_STAMP + (200,))
    # Поворот для живости
    layer = layer.rotate(-14, resample=Image.BICUBIC, expand=False)
    img.paste(layer,
              (cx - layer.width // 2, cy - layer.height // 2),
              layer)


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
