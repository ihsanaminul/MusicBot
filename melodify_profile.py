# ==============================================================================
#
#   ███╗   ███╗███████╗██╗      ██████╗ ██████╗ ██╗███████╗██╗   ██╗
#   ████╗ ████║██╔════╝██║     ██╔═══██╗██╔══██╗██║██╔════╝╚██╗ ██╔╝
#   ██╔████╔██║█████╗  ██║     ██║   ██║██║  ██║██║█████╗   ╚████╔╝
#   ██║╚██╔╝██║██╔══╝  ██║     ██║   ██║██║  ██║██║██╔══╝    ╚██╔╝
#   ██║ ╚═╝ ██║███████╗███████╗╚██████╔╝██████╔╝██║██║        ██║
#   ╚═╝     ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝╚═╝        ╚═╝
#
#   Melodify Profile Card System
#   Fitur: /profile — menampilkan statistik musik user per guild
#
#   HOW TO INTEGRATE:
#   1. Copy file ini ke folder yang sama dengan melodify.py (atau main bot kamu)
#   2. Di bagian atas melodify.py, tambahkan:
#        from melodify_profile import setup_profile, track_play
#   3. Di dalam on_ready event, tambahkan:
#        await setup_profile(bot)
#   4. Di dalam play_audio(), setelah `mp.voice_client.play(...)`, tambahkan:
#        asyncio.create_task(track_play(guild_id, mp.current_info, interaction_user_id))
#      Atau bisa dipanggil dari command /play setelah song berhasil di-queue.
#
#   DATABASE:
#   File: melodify_profile.db (terpisah dari melodify_state.db)
#
# ==============================================================================

import asyncio
import io
import json
import math
import os
import sqlite3
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ==============================================================================
# SECTION 1 ▸ CONFIGURATION
# ==============================================================================

PROFILE_DB_PATH = "melodify_profile.db"

# Font paths (Poppins sudah tersedia di server)
FONT_DIR = "/usr/share/fonts/truetype/google-fonts"
FONT_BOLD = os.path.join(FONT_DIR, "Poppins-Bold.ttf")
FONT_MEDIUM = os.path.join(FONT_DIR, "Poppins-Medium.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "Poppins-Regular.ttf")
FONT_LIGHT = os.path.join(FONT_DIR, "Poppins-Light.ttf")

# Fallback ke DejaVu jika Poppins tidak ada
if not os.path.exists(FONT_BOLD):
    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_MEDIUM = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_LIGHT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Card dimensions
CARD_W = 900
CARD_H = 520

# Color palette (Jockie Music style — dark red/maroon)
COLOR_BG_DARK = (28, 12, 12)  # background luar
COLOR_BG_CARD = (45, 18, 18)  # card utama
COLOR_BG_SECTION = (62, 25, 25)  # section boxes
COLOR_BG_HEADER = (120, 20, 20)  # header kanan "MELODIFY"
COLOR_ACCENT = (200, 50, 50)  # accent merah
COLOR_NUMBER = (200, 80, 80)  # nomor ranking
COLOR_LABEL = (230, 200, 200)  # text label
COLOR_VALUE = (255, 245, 245)  # text nilai utama
COLOR_DIM = (170, 140, 140)  # text sekunder / waktu
COLOR_WHITE = (255, 255, 255)
COLOR_GOLD = (255, 215, 100)  # rank #1
COLOR_SILVER = (200, 200, 200)  # rank #2
COLOR_BRONZE = (205, 140, 80)  # rank #3


# ==============================================================================
# SECTION 2 ▸ DATABASE
# ==============================================================================


@contextmanager
def profile_db():
    """Short-lived SQLite connection untuk profile DB."""
    conn = sqlite3.connect(PROFILE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_profile_db():
    """Buat tabel jika belum ada."""
    with profile_db() as conn:
        conn.executescript(
            """
            -- Statistik play per user per guild
            CREATE TABLE IF NOT EXISTS play_stats (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                track_title TEXT    NOT NULL,
                play_count  INTEGER NOT NULL DEFAULT 1,
                total_ms    INTEGER NOT NULL DEFAULT 0,
                last_played INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id, track_title)
            );

            -- Waktu bermain total per user per guild (untuk leaderboard)
            CREATE TABLE IF NOT EXISTS guild_time (
                user_id    INTEGER NOT NULL,
                guild_id   INTEGER NOT NULL,
                total_ms   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );

            -- Waktu bersama antar dua user (co-listen tracking)
            CREATE TABLE IF NOT EXISTS co_listen (
                user_a    INTEGER NOT NULL,
                user_b    INTEGER NOT NULL,
                guild_id  INTEGER NOT NULL,
                total_ms  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_a, user_b, guild_id),
                CHECK (user_a < user_b)
            );

            -- Avatar cache (simpan URL terakhir per user)
            CREATE TABLE IF NOT EXISTS avatar_cache (
                user_id    INTEGER PRIMARY KEY,
                avatar_url TEXT,
                cached_at  INTEGER NOT NULL DEFAULT 0
            );
        """
        )
    print("[Profile] Database initialized.")


# ==============================================================================
# SECTION 3 ▸ TRACKING FUNCTIONS
# ==============================================================================


async def track_play(
    guild_id: int,
    track_info: dict,
    requester_id: int,
    duration_ms: int = 0,
    voice_member_ids: Optional[list] = None,
):
    """
    Catat satu play event ke database.
    Dipanggil setelah lagu selesai dimainkan (di after_playing callback).

    Args:
        guild_id        : ID server
        track_info      : dict dari mp.current_info
        requester_id    : ID user yang request lagu
        duration_ms     : durasi sebenarnya yang diputar (ms)
        voice_member_ids: list user_id yang ada di voice channel saat itu
    """
    if not track_info:
        return

    title = track_info.get("title", "Unknown")[:200]
    if not duration_ms:
        raw_dur = track_info.get("duration", 0) or 0
        duration_ms = int(raw_dur * 1000)

    if duration_ms <= 0:
        return

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        _write_play_event,
        guild_id,
        requester_id,
        title,
        duration_ms,
        voice_member_ids or [],
    )


def _write_play_event(guild_id, requester_id, title, duration_ms, member_ids):
    """Sync DB write untuk play event."""
    with profile_db() as conn:
        # Update play_stats untuk requester
        conn.execute(
            """
            INSERT INTO play_stats (user_id, guild_id, track_title, play_count, total_ms, last_played)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id, guild_id, track_title) DO UPDATE SET
                play_count  = play_count + 1,
                total_ms    = total_ms + excluded.total_ms,
                last_played = excluded.last_played
        """,
            (requester_id, guild_id, title, duration_ms, int(time.time())),
        )

        # Update total guild time untuk semua member di VC
        all_users = set(member_ids)
        all_users.add(requester_id)
        for uid in all_users:
            conn.execute(
                """
                INSERT INTO guild_time (user_id, guild_id, total_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_ms = total_ms + excluded.total_ms
            """,
                (uid, guild_id, duration_ms),
            )

        # Update co-listen untuk semua pasangan member yang ada di VC
        members = sorted(all_users)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                ua, ub = min(a, b), max(a, b)
                conn.execute(
                    """
                    INSERT INTO co_listen (user_a, user_b, guild_id, total_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_a, user_b, guild_id) DO UPDATE SET
                        total_ms = total_ms + excluded.total_ms
                """,
                    (ua, ub, guild_id, duration_ms),
                )


# ==============================================================================
# SECTION 4 ▸ DATA QUERIES
# ==============================================================================


def get_user_top_tracks(user_id: int, guild_id: int, limit: int = 3) -> list:
    """Ambil top tracks user di sebuah guild berdasarkan total waktu dengar."""
    with profile_db() as conn:
        rows = conn.execute(
            """
            SELECT track_title, play_count, total_ms
            FROM play_stats
            WHERE user_id = ? AND guild_id = ?
            ORDER BY total_ms DESC
            LIMIT ?
        """,
            (user_id, guild_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_top_guilds(user_id: int, limit: int = 3, bot=None) -> list:
    """Ambil top server user berdasarkan total waktu dengar."""
    with profile_db() as conn:
        rows = conn.execute(
            """
            SELECT guild_id, total_ms
            FROM guild_time
            WHERE user_id = ?
            ORDER BY total_ms DESC
            LIMIT ?
        """,
            (user_id, limit),
        ).fetchall()

    result = []
    for r in rows:
        gid = r["guild_id"]
        guild_name = f"Server {gid}"
        if bot:
            g = bot.get_guild(gid)
            if g:
                guild_name = g.name
        result.append(
            {"guild_id": gid, "guild_name": guild_name, "total_ms": r["total_ms"]}
        )
    return result


def get_user_top_friends(user_id: int, guild_id: int, limit: int = 3, bot=None) -> list:
    """Ambil top teman (berdasarkan co-listen time) di sebuah guild."""
    with profile_db() as conn:
        rows = conn.execute(
            """
            SELECT
                CASE WHEN user_a = ? THEN user_b ELSE user_a END AS friend_id,
                total_ms
            FROM co_listen
            WHERE (user_a = ? OR user_b = ?) AND guild_id = ?
            ORDER BY total_ms DESC
            LIMIT ?
        """,
            (user_id, user_id, user_id, guild_id, limit),
        ).fetchall()

    result = []
    for r in rows:
        fid = r["friend_id"]
        display = f"User {fid}"
        if bot:
            u = bot.get_user(fid)
            if u:
                display = u.display_name
        result.append(
            {"user_id": fid, "display_name": display, "total_ms": r["total_ms"]}
        )
    return result


def get_total_user_time(user_id: int) -> int:
    """Total ms semua guild untuk user ini."""
    with profile_db() as conn:
        row = conn.execute(
            "SELECT SUM(total_ms) as t FROM guild_time WHERE user_id = ?", (user_id,)
        ).fetchone()
    return (row["t"] or 0) if row else 0


def get_guild_rank(user_id: int, guild_id: int) -> tuple[int, int]:
    """
    Kembalikan (rank, total_members) user di guild ini berdasarkan total waktu.
    """
    with profile_db() as conn:
        rows = conn.execute(
            """
            SELECT user_id, total_ms,
                   RANK() OVER (ORDER BY total_ms DESC) as rnk
            FROM guild_time
            WHERE guild_id = ?
        """,
            (guild_id,),
        ).fetchall()

    total = len(rows)
    for r in rows:
        if r["user_id"] == user_id:
            return r["rnk"], total
    return 0, total


# ==============================================================================
# SECTION 5 ▸ UTILITY HELPERS
# ==============================================================================


def ms_to_human(ms: int) -> str:
    """Convert milliseconds ke string yang mudah dibaca."""
    if ms <= 0:
        return "0m"
    seconds = ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days >= 1:
        h = hours % 24
        return f"{days}d {h}h" if h else f"{days}d"
    if hours >= 1:
        m = minutes % 60
        return f"{hours}h {m}m" if m else f"{hours}h"
    return f"{minutes}m"


def truncate(text: str, max_len: int) -> str:
    """Potong teks jika terlalu panjang."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def fetch_avatar_bytes(avatar_url: str) -> Optional[bytes]:
    """Download avatar dari URL (sync, dijalankan di executor)."""
    if not avatar_url:
        return None
    try:
        req = urllib.request.Request(
            avatar_url,
            headers={"User-Agent": "MelodifyBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()
    except Exception:
        return None


def make_circle_avatar(img_bytes: bytes, size: int) -> Image.Image:
    """Crop gambar jadi lingkaran dengan ukuran tertentu."""
    img = (
        Image.open(io.BytesIO(img_bytes))
        .convert("RGBA")
        .resize((size, size), Image.LANCZOS)
    )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font dengan fallback."""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def rank_color(rank: int):
    """Warna berdasarkan peringkat."""
    return (
        [COLOR_GOLD, COLOR_SILVER, COLOR_BRONZE][rank - 1]
        if 1 <= rank <= 3
        else COLOR_DIM
    )


# ==============================================================================
# SECTION 6 ▸ CARD GENERATOR
# ==============================================================================


def draw_rounded_rect(
    draw: ImageDraw.Draw, xy, radius: int, fill, outline=None, outline_width=1
):
    """Gambar kotak dengan sudut membulat."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(
        [x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=outline_width
    )


def draw_section_label(draw: ImageDraw.Draw, x: int, y: int, text: str, font):
    """Gambar label section dengan garis di kiri."""
    draw.rectangle([x, y + 3, x + 3, y + font.size - 3], fill=COLOR_ACCENT)
    draw.text((x + 10, y), text, font=font, fill=COLOR_DIM)


def generate_profile_card(
    username: str,
    discriminator: str,
    avatar_bytes: Optional[bytes],
    top_tracks: list,
    top_guilds: list,
    top_friends: list,
    total_ms: int,
    guild_rank: int,
    guild_total: int,
) -> io.BytesIO:
    """
    Generate profile card image.
    Returns BytesIO PNG yang siap dikirim ke Discord.
    """

    # ── Canvas ────────────────────────────────────────────────────────────────
    img = Image.new("RGB", (CARD_W, CARD_H), COLOR_BG_DARK)
    draw = ImageDraw.Draw(img)

    # ── Background card utama ─────────────────────────────────────────────────
    draw_rounded_rect(
        draw, [16, 16, CARD_W - 16, CARD_H - 16], radius=18, fill=COLOR_BG_CARD
    )

    # Subtle texture: garis-garis diagonal samar
    for i in range(0, CARD_W + CARD_H, 28):
        draw.line([(i, 0), (0, i)], fill=(60, 25, 25), width=1)

    # ── Header kanan — "MELODIFY" badge ───────────────────────────────────────
    badge_w = 180
    draw_rounded_rect(
        draw,
        [CARD_W - 16 - badge_w, 16, CARD_W - 16, 16 + 42],
        radius=0,
        fill=COLOR_BG_HEADER,
    )
    # Buat rounded hanya sudut kanan
    draw_rounded_rect(
        draw,
        [CARD_W - 16 - badge_w, 16, CARD_W - 16, 16 + 42],
        radius=12,
        fill=COLOR_BG_HEADER,
    )

    fn_badge = load_font(FONT_BOLD, 16)
    draw.text(
        (CARD_W - 16 - badge_w + 14, 25), "✦ MELODIFY", font=fn_badge, fill=COLOR_WHITE
    )

    # ── Avatar + info user (panel kiri atas) ──────────────────────────────────
    AV_SIZE = 90
    AV_X, AV_Y = 40, 40

    # Lingkaran avatar placeholder
    draw.ellipse(
        [AV_X - 3, AV_Y - 3, AV_X + AV_SIZE + 3, AV_Y + AV_SIZE + 3], fill=COLOR_ACCENT
    )
    draw.ellipse([AV_X, AV_Y, AV_X + AV_SIZE, AV_Y + AV_SIZE], fill=COLOR_BG_SECTION)

    if avatar_bytes:
        try:
            av_img = make_circle_avatar(avatar_bytes, AV_SIZE)
            img.paste(av_img, (AV_X, AV_Y), av_img)
        except Exception:
            pass

    # Nama user
    fn_name = load_font(FONT_BOLD, 26)
    fn_disc = load_font(FONT_REGULAR, 14)
    fn_sub = load_font(FONT_MEDIUM, 13)

    name_x = AV_X + AV_SIZE + 18
    draw.text(
        (name_x, AV_Y + 4), truncate(username, 22), font=fn_name, fill=COLOR_WHITE
    )

    # Rank badge
    if guild_rank > 0:
        rank_txt = f"  #{guild_rank} of {guild_total}"
        draw.text((name_x, AV_Y + 36), rank_txt, font=fn_disc, fill=COLOR_DIM)

    # Total listening time
    total_txt = f"⏱  {ms_to_human(total_ms)} total"
    draw.text((name_x, AV_Y + 56), total_txt, font=fn_sub, fill=COLOR_LABEL)

    # ── Ikon musik kecil di bawah nama (dekorasi) ──────────────────────────────
    icons = ["♫", "♪", "♬"]
    icon_x = name_x
    fn_icon = load_font(FONT_REGULAR, 18)
    for ic in icons:
        draw.text((icon_x, AV_Y + AV_SIZE - 2), ic, font=fn_icon, fill=COLOR_ACCENT)
        icon_x += 26

    # ── SEPARATOR horizontal ───────────────────────────────────────────────────
    sep_y = 148
    draw.line([(32, sep_y), (CARD_W - 32, sep_y)], fill=(80, 35, 35), width=1)

    # ── Tiga kolom konten ─────────────────────────────────────────────────────
    #    Col 1: Top Servers (kiri)
    #    Col 2: Top Friends (tengah)
    #    Col 3: Top Tracks  (kanan)

    col_y_start = sep_y + 18
    col_h = CARD_H - col_y_start - 24
    col_pad = 14

    col_w = (CARD_W - 32 - 32 - 2 * 12) // 3  # 3 kolom + 2 gap
    col1_x = 32
    col2_x = col1_x + col_w + 12
    col3_x = col2_x + col_w + 12

    fn_sect_title = load_font(FONT_BOLD, 13)
    fn_rank_num = load_font(FONT_BOLD, 18)
    fn_item_name = load_font(FONT_MEDIUM, 13)
    fn_item_sub = load_font(FONT_LIGHT, 11)

    def draw_section_box(x, y, w, h, title, items, value_key, name_key, value_fmt=None):
        """
        Gambar sebuah section box dengan daftar item.

        items: list of dict
        name_key: key untuk nama item
        value_key: key untuk nilai (ms)
        value_fmt: fungsi format nilai, default ms_to_human
        """
        # Box background
        draw_rounded_rect(draw, [x, y, x + w, y + h], radius=10, fill=COLOR_BG_SECTION)

        # Title
        draw_section_label(draw, x + col_pad, y + col_pad, title, fn_sect_title)

        # Items
        item_y = y + col_pad + fn_sect_title.size + 10
        row_h = 48

        for idx, item in enumerate(items[:3], start=1):
            rank = idx
            rcolor = rank_color(rank)
            name = truncate(str(item.get(name_key, "—")), 18)
            raw_val = item.get(value_key, 0)
            val_str = value_fmt(raw_val) if value_fmt else ms_to_human(raw_val)

            # Nomor rank
            draw.text(
                (x + col_pad, item_y + 6), str(rank), font=fn_rank_num, fill=rcolor
            )

            # Garis kecil di kiri nomor (accent)
            draw.rectangle(
                [
                    x + col_pad - 4,
                    item_y + 8,
                    x + col_pad - 2,
                    item_y + 8 + fn_rank_num.size - 8,
                ],
                fill=rcolor,
            )

            # Nama & nilai
            text_x = x + col_pad + 24
            draw.text((text_x, item_y + 4), name, font=fn_item_name, fill=COLOR_VALUE)
            draw.text((text_x, item_y + 22), val_str, font=fn_item_sub, fill=COLOR_DIM)

            item_y += row_h

        # Jika tidak ada data
        if not items:
            draw.text(
                (x + col_pad, y + col_pad + fn_sect_title.size + 14),
                "No data yet",
                font=fn_item_sub,
                fill=COLOR_DIM,
            )

    # ── TOP SERVERS ────────────────────────────────────────────────────────────
    draw_section_box(
        col1_x,
        col_y_start,
        col_w,
        col_h,
        title="TOP SERVERS",
        items=top_guilds,
        name_key="guild_name",
        value_key="total_ms",
    )

    # ── TOP FRIENDS ────────────────────────────────────────────────────────────
    draw_section_box(
        col2_x,
        col_y_start,
        col_w,
        col_h,
        title="TOP FRIENDS",
        items=top_friends,
        name_key="display_name",
        value_key="total_ms",
    )

    # ── TOP TRACKS ─────────────────────────────────────────────────────────────
    draw_section_box(
        col3_x,
        col_y_start,
        col_w,
        col_h,
        title="TOP TRACKS",
        items=top_tracks,
        name_key="track_title",
        value_key="total_ms",
    )

    # ── Footer watermark ──────────────────────────────────────────────────────
    fn_footer = load_font(FONT_LIGHT, 10)
    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    draw.text(
        (CARD_W - 32 - 120, CARD_H - 28),
        f"melodify.bot  •  {ts}",
        font=fn_footer,
        fill=COLOR_DIM,
    )

    # ── Subtle vignette ────────────────────────────────────────────────────────
    vignette = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    for i in range(20):
        alpha = int(60 * (i / 20) ** 2)
        vd.rectangle([i, i, CARD_W - i, CARD_H - i], outline=(0, 0, 0, alpha), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")

    # ── Serialize ke BytesIO ───────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


# ==============================================================================
# SECTION 7 ▸ DISCORD COMMAND
# ==============================================================================


async def build_and_send_profile(
    interaction: discord.Interaction, target: discord.Member
):
    """Public function to build and send profile card."""
    return await _build_and_send_profile(interaction, target)


async def _build_and_send_profile(
    interaction: discord.Interaction, target: discord.Member
):
    """Core logic: ambil data → generate gambar → kirim."""
    guild_id = interaction.guild.id
    user_id = target.id

    loop = asyncio.get_running_loop()

    # Ambil semua data dari DB secara paralel (semuanya sync, jadi pakai executor)
    top_tracks, top_guilds, top_friends, total_ms, (g_rank, g_total) = (
        await asyncio.gather(
            loop.run_in_executor(None, get_user_top_tracks, user_id, guild_id, 3),
            loop.run_in_executor(
                None, lambda: get_user_top_guilds(user_id, 3, interaction.client)
            ),
            loop.run_in_executor(
                None,
                lambda: get_user_top_friends(user_id, guild_id, 3, interaction.client),
            ),
            loop.run_in_executor(None, get_total_user_time, user_id),
            loop.run_in_executor(None, get_guild_rank, user_id, guild_id),
        )
    )

    # Download avatar
    av_url = target.display_avatar.with_size(256).url
    av_bytes = await loop.run_in_executor(None, fetch_avatar_bytes, av_url)

    # Generate gambar (CPU-bound)
    buf = await loop.run_in_executor(
        None,
        generate_profile_card,
        target.display_name,
        str(target.discriminator),
        av_bytes,
        top_tracks,
        top_guilds,
        top_friends,
        total_ms,
        g_rank,
        g_total,
    )

    # Kirim
    file = discord.File(buf, filename=f"profile_{target.id}.png")
    await interaction.followup.send(file=file)


def setup_profile_command(bot: discord.ext.commands.Bot):
    """Daftarkan slash command /profile ke bot tree."""

    @bot.tree.command(
        name="profile", description="Tampilkan statistik musik kamu atau member lain."
    )
    @app_commands.describe(member="Member yang ingin dilihat profilnya (default: kamu)")
    async def profile_cmd(
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Command ini hanya bisa digunakan di server.", ephemeral=True
            )

        await interaction.response.defer()
        target = member or interaction.guild.get_member(interaction.user.id)
        if not target:
            return await interaction.followup.send(
                "Member tidak ditemukan.", ephemeral=True
            )

        try:
            await _build_and_send_profile(interaction, target)
        except Exception as e:
            import traceback

            traceback.print_exc()
            await interaction.followup.send(
                f"Gagal generate profile card: {e}", ephemeral=True
            )

    return profile_cmd


# ==============================================================================
# SECTION 8 ▸ INTEGRATION HELPERS
# ==============================================================================


async def setup_profile(bot):
    """
    Inisialisasi sistem profile.
    Panggil ini di on_ready event bot kamu:

        from melodify_profile import setup_profile
        await setup_profile(bot)
    """
    import discord.ext.commands

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, init_profile_db)
    # setup_profile_command(bot)  # Command now registered directly in melodify.py
    print("[Profile] Profile system initialized.")


# ==============================================================================
# SECTION 9 ▸ AUTO-TRACKING INTEGRATION
# ==============================================================================

"""
CARA INTEGRASI KE play_audio() DI MELODIFY.PY:
================================================

Di bagian after_playing callback, setelah `mp.current_info = None`, tambahkan:

    # ── Profile tracking ───────────────────────────────────────────────────────
    if finished and mp.voice_client:
        try:
            from melodify_profile import track_play
            # Hitung durasi yang benar-benar diputar
            played_ms = 0
            if mp.playback_started_at:
                played_ms = int((time.time() - (mp.playback_started_at or time.time())) * 1000)
            
            # Ambil semua user di voice channel saat lagu selesai
            vc_members = []
            if mp.voice_client and mp.voice_client.channel:
                vc_members = [
                    m.id for m in mp.voice_client.channel.members
                    if not m.bot
                ]
            
            requester = finished.get("requester")
            req_id = requester.id if hasattr(requester, "id") else bot.user.id
            
            bot.loop.create_task(
                track_play(guild_id, finished, req_id, played_ms, vc_members)
            )
        except Exception as _track_err:
            logger.warning(f"[Profile] track_play error: {_track_err}")
    # ── End profile tracking ───────────────────────────────────────────────────
"""


# ==============================================================================
# SECTION 10 ▸ STANDALONE TEST
# ==============================================================================

# ==============================================================================
# END OF FILE
# ==============================================================================
