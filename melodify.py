# ════════════════════════════════════════════════════════════════════════════
# ▌ MELODIFY BOT - Music Discord Bot (Optimized)
# ════════════════════════════════════════════════════════════════════════════

# ── IMPORTS & CONFIGURATION ──
import asyncio
import datetime
import json
import logging
import math
import os
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from typing import Optional, List
from urllib.parse import urlparse, parse_qs
from melodify_profile import setup_profile, track_play, build_and_send_profile

import aiohttp
import discord
import lyricsgenius
import psutil
import syncedlyrics
import yt_dlp
from cachetools import TTLCache
from discord import Embed, ButtonStyle, app_commands
from discord.ext import commands
from discord.app_commands import Choice
from discord.ui import View, Button
from dotenv import load_dotenv
from i18n_translator import I18nTranslator, Locale
from playwright.async_api import async_playwright
from spotify_scraper import SpotifyClient

load_dotenv()

# ── REGEX PATTERNS ──
SPOTIFY_REGEX = re.compile(r"^(https?://)?(open\.spotify\.com)/.+$")
DEEZER_REGEX = re.compile(
    r"^(https?://)?((www\.)?deezer\.com/(?:[a-z]{2}/)?(track|playlist|album|artist)/.+|(link\.deezer\.com)/s/.+)$"
)
APPLE_MUSIC_REGEX = re.compile(r"^(https?://)?(music\.apple\.com)/.+$")
TIDAL_REGEX = re.compile(r"^(https?://)?(www\.)?tidal\.com/.+$")
AMAZON_MUSIC_REGEX = re.compile(
    r"^(https?://)?(music\.amazon\.(fr|com|co\.uk|de|es|it|jp))/.+$"
)
YOUTUBE_REGEX = re.compile(
    r"^(https?://)?((www|m)\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+$"
)
SOUNDCLOUD_REGEX = re.compile(r"^(https?://)?(www\.)?(soundcloud\.com)/.+$")
DIRECT_LINK_REGEX = re.compile(
    r"^(https?://).+\.(mp3|wav|ogg|m4a|mp4|webm|flac)(\?.+)?$", re.IGNORECASE
)
TIME_TAG_RE = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")

# ── CONSTANTS ──
SILENT_MESSAGES = True
IS_PUBLIC_VERSION = False
AVAILABLE_COOKIES = [f"cookies_{i}.txt" for i in range(1, 6)]

AUDIO_FILTERS = {
    "slowed": "asetrate=44100*0.8",
    "spedup": "asetrate=44100*1.2",
    "nightcore": "asetrate=44100*1.25,atempo=1.0",
    "reverb": "aecho=0.8:0.9:40|50|60:0.4|0.3|0.2",
    "8d": "apulsator=hz=0.08",
    "muffled": "lowpass=f=500",
    "bassboost": "bass=g=10",
    "earrape": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1",
    "distant": "lowpass=f=800,aecho=0.8:0.88:60|200|500:0.4|0.3|0.2,bass=g=6,volume=1.4",
    "iem": (
        "highpass=f=35,"
        "equalizer=f=80:width_type=q:width=1.0:g=2,"
        "equalizer=f=250:width_type=q:width=1.0:g=-2,"
        "equalizer=f=1500:width_type=q:width=1.0:g=1,"
        "equalizer=f=3500:width_type=q:width=1.0:g=4,"
        "equalizer=f=8000:width_type=q:width=1.0:g=2.5,"
        "equalizer=f=13000:width_type=q:width=1.0:g=2,"
        "acompressor=threshold=0.4:ratio=2.5:attack=5:release=80:makeup=1"
    ),
}

# ── LOGGING ──
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── API CLIENTS ──
import multiprocessing as _mp

_IS_MAIN_PROCESS = _mp.current_process().name == "MainProcess"

GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")
genius = None
spotify_scraper_client = None

if _IS_MAIN_PROCESS:
    if GENIUS_TOKEN and GENIUS_TOKEN != "YOUR_GENIUS_TOKEN_HERE":
        genius = lyricsgenius.Genius(
            GENIUS_TOKEN, verbose=False, remove_section_headers=True
        )
        logger.info("LyricsGenius client initialized.")

    try:
        spotify_scraper_client = SpotifyClient(browser_type="requests")
        logger.info("SpotifyScraper initialized.")
    except Exception as e:
        logger.error(f"SpotifyScraper init failed: {e}")

# ── CACHES & TRANSLATOR ──
url_cache = TTLCache(maxsize=75_000, ttl=7_200)  # metadata cache
stream_url_cache = TTLCache(maxsize=5_000, ttl=300)  # stream URLs (5 min)

I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")
translator = I18nTranslator(default_locale=Locale.EN_US, translations_dir=I18N_DIR)

# ── PROCESS POOL ──
try:
    process_pool = ProcessPoolExecutor(max_workers=psutil.cpu_count(logical=False))
except NotImplementedError:
    process_pool = ProcessPoolExecutor(max_workers=os.cpu_count())

# ════════════════════════════════════════════════════════════════════════════
# ▌ DATABASE - WAL Mode + Context Manager
# ════════════════════════════════════════════════════════════════════════════
DB_PATH = "melodify_state.db"


@contextmanager
def db_connection():
    """Yield a short-lived connection; always closes on exit."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads while writing
    conn.execute("PRAGMA synchronous=NORMAL")  # safe + faster than FULL
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id              INTEGER PRIMARY KEY,
            kawaii_mode           BOOLEAN NOT NULL DEFAULT 0,
            controller_channel_id INTEGER,
            controller_message_id INTEGER,
            is_24_7               BOOLEAN NOT NULL DEFAULT 0,
            autoplay              BOOLEAN NOT NULL DEFAULT 0,
            volume                REAL    NOT NULL DEFAULT 1.0
        );
        CREATE TABLE IF NOT EXISTS allowlist (
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        );
        CREATE TABLE IF NOT EXISTS playback_state (
            guild_id              INTEGER PRIMARY KEY,
            voice_channel_id      INTEGER,
            current_song_json     TEXT,
            queue_json            TEXT,
            history_json          TEXT,
            radio_playlist_json   TEXT,
            loop_current          BOOLEAN NOT NULL DEFAULT 0,
            playback_timestamp    REAL    NOT NULL DEFAULT 0
        );
        """
        )
    logger.info("Database initialized (WAL mode).")


# ════════════════════════════════════════════════════════════════════════════
# ▌ CORE CLASSES - Memory Efficient: __slots__
# ════════════════════════════════════════════════════════════════════════════


class MusicPlayer:
    __slots__ = (
        "voice_client",
        "current_task",
        "queue",
        "history",
        "radio_playlist",
        "current_url",
        "current_info",
        "text_channel",
        "loop_current",
        "autoplay_enabled",
        "last_was_single",
        "start_time",
        "playback_started_at",
        "active_filter",
        "seek_info",
        "lyrics_task",
        "lyrics_message",
        "synced_lyrics",
        "is_seeking",
        "playback_speed",
        "is_reconnecting",
        "is_current_live",
        "hydration_task",
        "hydration_lock",
        "suppress_next_now_playing",
        "is_auto_promoting",
        "is_cleaning",
        "is_resuming_after_clean",
        "resume_info",
        "is_resuming_live",
        "silence_task",
        "is_playing_silence",
        "volume",
        "controller_message_id",
        "duration_hydration_lock",
        "queue_lock",
        "silence_management_lock",
        "is_paused_by_leave",
        "manual_stop",
    )

    def __init__(self):
        self.voice_client = None
        self.current_task = None
        self.queue = asyncio.Queue(maxsize=5000)  # ← Prevent unbounded growth
        self.history = []
        self.radio_playlist = []
        self.current_url = None
        self.current_info = None
        self.text_channel = None
        self.loop_current = False
        self.autoplay_enabled = False
        self.last_was_single = False
        self.start_time = 0
        self.playback_started_at = None
        self.active_filter = None
        self.seek_info = None
        self.lyrics_task = None
        self.lyrics_message = None
        self.synced_lyrics = None
        self.is_seeking = False
        self.playback_speed = 1.0
        self.is_reconnecting = False
        self.is_current_live = False
        self.hydration_task = None
        self.hydration_lock = asyncio.Lock()
        self.suppress_next_now_playing = False
        self.is_auto_promoting = False
        self.is_cleaning = False
        self.is_resuming_after_clean = False
        self.resume_info = None
        self.is_resuming_live = False
        self.silence_task = None
        self.is_playing_silence = False

        self.volume = 1.0
        self.controller_message_id = None
        self.duration_hydration_lock = asyncio.Lock()
        self.queue_lock = asyncio.Lock()
        self.silence_management_lock = asyncio.Lock()
        self.is_paused_by_leave = False
        self.manual_stop = False


class GuildModel:
    __slots__ = (
        "guild_id",
        "music_player",
        "locale",
        "server_filters",
        "karaoke_disclaimer_shown",
        "_24_7_mode",
        "allowed_channels",
        "controller_channel_id",
        "controller_message_id",
        "_controller_update_task",  # NEW: per-guild debounce task
        "_status_update_task",  # NEW: per-guild VC-status debounce
    )

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.music_player = MusicPlayer()
        self.locale = Locale.EN_US
        self.server_filters = set()
        self.karaoke_disclaimer_shown = False
        self._24_7_mode = False
        self.allowed_channels = set()
        self.controller_channel_id = None
        self.controller_message_id = None
        self._controller_update_task = None
        self._status_update_task = None


# ── GUILD STATE REGISTRY ──
guild_states: dict[int, GuildModel] = {}
_guild_states_lock = threading.Lock()


def get_guild_state(guild_id: int) -> GuildModel:
    """Thread-safe retrieval or creation of guild state."""
    with _guild_states_lock:
        if guild_id not in guild_states:
            guild_states[guild_id] = GuildModel(guild_id)
        return guild_states[guild_id]


def get_player(guild_id: int) -> MusicPlayer:
    return get_guild_state(guild_id).music_player


def get_mode(guild_id: int) -> bool:
    return get_guild_state(guild_id).locale == Locale.EN_X_KAWAII


# ════════════════════════════════════════════════════════════════════════════
# ▌ DATABASE PERSISTENCE - UPSERT
# ════════════════════════════════════════════════════════════════════════════


async def save_all_states():
    """Persist all guild states using UPSERT (no full-table delete)."""
    logger.info("Saving all guild states...")
    rows_settings, rows_allowlist, rows_playback = [], [], []

    for guild_id, state in guild_states.items():
        player = state.music_player
        rows_settings.append(
            (
                guild_id,
                state.locale == Locale.EN_X_KAWAII,
                state.controller_channel_id,
                state.controller_message_id,
                state._24_7_mode,
                player.autoplay_enabled,
                player.volume,
            )
        )

        for ch_id in state.allowed_channels:
            rows_allowlist.append((guild_id, ch_id))

        if not (player.voice_client and player.voice_client.is_connected()):
            continue

        ts = 0
        if player.playback_started_at:
            ts = (
                player.start_time
                + (time.time() - player.playback_started_at) * player.playback_speed
            )
        elif player.start_time:
            ts = player.start_time

        rows_playback.append(
            (
                guild_id,
                player.voice_client.channel.id,
                json.dumps(player.current_info) if player.current_info else None,
                (
                    json.dumps(list(player.queue._queue))
                    if not player.queue.empty()
                    else None
                ),
                json.dumps(player.history),
                json.dumps(player.radio_playlist),
                player.loop_current,
                ts,
            )
        )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, _write_states, rows_settings, rows_allowlist, rows_playback
    )
    logger.info("State save complete.")


def _write_states(rows_settings, rows_allowlist, rows_playback):
    """Synchronous DB write — runs in executor thread."""
    with db_connection() as conn:
        conn.executemany(
            """
            INSERT INTO guild_settings
                (guild_id,kawaii_mode,controller_channel_id,controller_message_id,is_24_7,autoplay,volume)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(guild_id) DO UPDATE SET
                kawaii_mode=excluded.kawaii_mode,
                controller_channel_id=excluded.controller_channel_id,
                controller_message_id=excluded.controller_message_id,
                is_24_7=excluded.is_24_7,
                autoplay=excluded.autoplay,
                volume=excluded.volume
        """,
            rows_settings,
        )

        conn.execute("DELETE FROM allowlist")
        if rows_allowlist:
            conn.executemany(
                "INSERT OR IGNORE INTO allowlist VALUES (?,?)", rows_allowlist
            )

        conn.executemany(
            """
            INSERT INTO playback_state
                (guild_id,voice_channel_id,current_song_json,queue_json,
                 history_json,radio_playlist_json,loop_current,playback_timestamp)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(guild_id) DO UPDATE SET
                voice_channel_id=excluded.voice_channel_id,
                current_song_json=excluded.current_song_json,
                queue_json=excluded.queue_json,
                history_json=excluded.history_json,
                radio_playlist_json=excluded.radio_playlist_json,
                loop_current=excluded.loop_current,
                playback_timestamp=excluded.playback_timestamp
        """,
            rows_playback,
        )


async def load_states_on_startup():
    logger.info("Loading states from DB...")

    def _read_db():
        with db_connection() as conn:
            return (
                conn.execute("SELECT * FROM guild_settings").fetchall(),
                conn.execute("SELECT * FROM allowlist").fetchall(),
                conn.execute("SELECT * FROM playback_state").fetchall(),
            )

    loop = asyncio.get_running_loop()
    settings_rows, allowlist_rows, playback_rows = await loop.run_in_executor(
        None, _read_db
    )

    for row in settings_rows:
        gid = row["guild_id"]
        state = get_guild_state(gid)
        mp = state.music_player
        state.locale = Locale.EN_X_KAWAII if row["kawaii_mode"] else Locale.EN_US
        state.controller_channel_id = row["controller_channel_id"]
        state.controller_message_id = row["controller_message_id"]
        state._24_7_mode = row["is_24_7"]
        mp.autoplay_enabled = row["autoplay"]
        mp.volume = row["volume"]

    for row in allowlist_rows:
        get_guild_state(row["guild_id"]).allowed_channels.add(row["channel_id"])

    for row in playback_rows:
        gid = row["guild_id"]
        guild = bot.get_guild(gid)
        if not guild:
            continue
        state = get_guild_state(gid)
        mp = state.music_player
        try:
            mp.current_info = (
                json.loads(row["current_song_json"])
                if row["current_song_json"]
                else None
            )
            mp.history = json.loads(row["history_json"]) if row["history_json"] else []
            mp.radio_playlist = (
                json.loads(row["radio_playlist_json"])
                if row["radio_playlist_json"]
                else []
            )
            mp.loop_current = row["loop_current"]

            for item in json.loads(row["queue_json"]) if row["queue_json"] else []:
                await mp.queue.put(item)

            if row["voice_channel_id"] and mp.current_info:
                ch = guild.get_channel(row["voice_channel_id"])
                if ch and isinstance(ch, discord.VoiceChannel):
                    mp.voice_client = await ch.connect()
                    mp.text_channel = bot.get_channel(state.controller_channel_id or 0)
                    bot.loop.create_task(
                        play_audio(
                            gid, seek_time=row["playback_timestamp"], is_a_loop=True
                        )
                    )
        except Exception as e:
            logger.error(f"Failed to restore state for guild {gid}: {e}")

    logger.info("State loading complete.")


# ════════════════════════════════════════════════════════════════════════════
# ▌ YT-DLP HELPERS - Stream URL Caching
# ════════════════════════════════════════════════════════════════════════════


def ydl_worker(ydl_opts: dict, query: str, cookies_file: Optional[str] = None) -> dict:
    """Runs in subprocess — low priority, returns serialisable dict."""
    p = psutil.Process()
    try:
        if platform.system() == "Windows":
            p.nice(psutil.IDLE_PRIORITY_CLASS)
        else:
            p.nice(19)
    except Exception:
        pass

    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return {"status": "ok", "data": ydl.extract_info(query, download=False)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def run_ydl_with_low_priority(
    ydl_opts: dict,
    query: str,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    specific_cookie_file: Optional[str] = None,
) -> dict:
    if loop is None:
        loop = asyncio.get_running_loop()

    cookie_path = None
    if specific_cookie_file:
        candidate = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), specific_cookie_file
        )
        if os.path.exists(candidate):
            cookie_path = candidate

    result = await loop.run_in_executor(
        process_pool, ydl_worker, ydl_opts, query, cookie_path
    )
    if result["status"] == "error":
        raise yt_dlp.utils.DownloadError(result["message"])
    return result["data"]


async def fetch_video_info_with_retry(
    query: str, ydl_opts_override: Optional[dict] = None
) -> dict:
    """Fetch info; retry with cookie rotation on bot detection or age-restriction."""
    base_opts = {
        "format": "bestaudio[acodec=opus]/bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "socket_timeout": 15,
    }
    opts = {**base_opts, **(ydl_opts_override or {})}

    _COOKIE_TRIGGERS = (
        "sign in to confirm",
        "age-restricted",
        "age restricted",
        "confirm you're not a bot",
        "bot detection",
        "inappropriate for some users",
        "this video is not available",
        "private video",
    )

    def _needs_cookies(err_str: str) -> bool:
        el = err_str.lower()
        return any(t in el for t in _COOKIE_TRIGGERS)

    try:
        return await run_ydl_with_low_priority(opts, query)
    except yt_dlp.utils.DownloadError as e:
        if _needs_cookies(str(e)):
            cookies = AVAILABLE_COOKIES.copy()
            random.shuffle(cookies)
            last_exc = e
            for cookie in cookies:
                try:
                    return await run_ydl_with_low_priority(
                        opts, query, specific_cookie_file=cookie
                    )
                except (yt_dlp.utils.DownloadError, Exception) as ce:
                    last_exc = ce
                    continue
            raise last_exc
        raise


async def fetch_meta(url: str, _) -> Optional[dict]:
    """Lightweight metadata fetch for queue hydration — uses cache."""
    if url in url_cache:
        return url_cache[url]
    try:
        data = await fetch_video_info_with_retry(url)
        result = {
            "url": url,
            "title": data.get("title", "Unknown Title"),
            "webpage_url": data.get("webpage_url", url),
            "thumbnail": data.get("thumbnail"),
            "duration": data.get("duration", 0),
            "is_single": False,
        }
        url_cache[url] = result
        return result
    except Exception as e:
        logger.warning(f"fetch_meta failed for {url}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# ▌ UTILITY HELPERS
# ════════════════════════════════════════════════════════════════════════════


def get_messages(key: str, guild_id: int, **kwargs) -> str:
    """Get localized message for guild with parameters."""
    state = get_guild_state(guild_id)
    return translator.t(key, locale=state.locale.value, **kwargs)


def format_duration(seconds: Optional[float]) -> str:
    """Format seconds to HH:MM:SS or MM:SS format."""
    if seconds is None or seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def create_progress_bar(
    current: int, total: int, guild_id: int, bar_length: int = 10
) -> str:
    """Create visual progress bar with unicode characters."""
    if not total:
        return (
            f"`[{'▬' * bar_length}]` {get_messages('player.live_indicator', guild_id)}"
        )
    filled = int(bar_length * current / total)
    return f"`[{'█' * filled}{'─' * (bar_length - filled)}]`"


def parse_time(time_str: str) -> Optional[int]:
    """Parse time string (MM:SS, HH:MM:SS, or seconds) to total seconds."""
    if not time_str:
        return None
    parts = time_str.strip().split(":")
    if not all(p.isdigit() for p in parts):
        return None
    parts = [int(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def sanitize_query(query: str) -> str:
    """Remove control characters and normalize whitespace in search query."""
    query = re.sub(r"[\x00-\x1F\x7F]", "", query)
    return re.sub(r"\s+", " ", query).strip()


def get_video_id(url: str) -> Optional[str]:
    p = urlparse(url)
    if p.hostname in ("youtube.com", "www.youtube.com"):
        if p.path == "/watch":
            return parse_qs(p.query).get("v", [None])[0]
    elif p.hostname == "youtu.be":
        return p.path[1:]
    return None


def get_mix_playlist_url(video_url: str) -> Optional[str]:
    vid = get_video_id(video_url)
    return f"https://www.youtube.com/watch?v={vid}&list=RD{vid}" if vid else None


def get_speed_multiplier_from_filters(active_filters: set) -> float:
    pitch = tempo = 1.0
    for f in active_filters:
        fv = AUDIO_FILTERS.get(f, "")
        if m := re.search(r"atempo=([\d.]+)", fv):
            tempo *= float(m.group(1))
        if m := re.search(r"asetrate=[\d.]+\*([\d.]+)", fv):
            pitch *= float(m.group(1))
    return pitch * tempo


def get_file_duration(file_path: str) -> float:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except Exception:
        return 0.0


# Regex patterns for title cleaning
TITLE_CLEAN_PATTERNS = [
    re.compile(r"\[.*?\]"),
    re.compile(r"\(.*?\)"),
    re.compile(r"(?i)official\s*(video|audio|lyric|music)?"),
    re.compile(r"(?i)lyric\s*video"),
    re.compile(r"(?i)music\s*video"),
    re.compile(r"(?i)(hd|4k|uhd|1080p|720p)"),
    re.compile(r"(?i)remastered"),
    re.compile(r"(?i)audio\s*only"),
    re.compile(r"(?i)full\s*song"),
    re.compile(r"(?i)radio\s*edit"),
    re.compile(r"(?i)clean\s*(version)?"),
    re.compile(r"(?i)explicit"),
    re.compile(r"\+"),
    re.compile(r"-\s*$"),
    re.compile(r"^\s*-"),
]
WHITESPACE_REGEX = re.compile(r"\s+")


def clean_display_title(title: str) -> str:
    """Clean title by removing unnecessary brackets and info (using pre-compiled regexes)."""
    if not title:
        return "Unknown Title"

    out = title
    for pattern in TITLE_CLEAN_PATTERNS:
        out = pattern.sub("", out)

    out = WHITESPACE_REGEX.sub(" ", out).strip(" -—–")
    return out if len(out) >= 3 else title.strip()


def get_cleaned_song_info(info: dict, guild_id: int) -> tuple[str, str]:
    title = info.get("title", get_messages("player.unknown_title", guild_id))
    artist = info.get("uploader", get_messages("player.unknown_artist", guild_id))
    _NOISE = [
        "xoxo",
        "official",
        "beats",
        "prod",
        "music",
        "records",
        "tv",
        "lyrics",
        "archive",
        "- Topic",
    ]
    clean_artist = artist
    for n in _NOISE:
        clean_artist = re.sub(r"(?i)" + re.escape(n), "", clean_artist).strip()

    _PAT = [
        r"\[.*?\]",
        r"\(.*?\)",
        r"\s*feat\..*",
        r"\s*ft\..*",
        r"\s*w/.*",
        r"(?i)official video",
        r"(?i)lyric video",
        r"(?i)audio",
        r"(?i)hd",
        r"4K",
        r"\+",
    ]
    clean_title = title
    for p in _PAT:
        clean_title = re.sub(p, "", clean_title)
    clean_title = clean_title.replace(clean_artist, "").replace(artist, "").strip(" -")
    if not clean_title:
        clean_title = re.sub(r"\[.*?\]|\(.*?\)", "", title).strip()
    return clean_title, clean_artist


def get_track_display_info(track, guild_id: int = 0) -> dict:
    if isinstance(track, LazySearchItem):
        if track.resolved_info and not track.resolved_info.get("error"):
            return {
                "title": track.resolved_info.get(
                    "title", get_messages("player.unknown_title", guild_id)
                ),
                "duration": track.resolved_info.get("duration", 0),
                "webpage_url": track.resolved_info.get("webpage_url", "#"),
                "source_type": "lazy-resolved",
            }
        return {
            "title": track.title
            or get_messages("player.loading_placeholder", guild_id),
            "duration": 0,
            "webpage_url": "#",
            "source_type": "lazy",
        }
    if isinstance(track, dict):
        return {
            "title": track.get("title", get_messages("player.unknown_title", guild_id)),
            "duration": track.get("duration", 0),
            "webpage_url": track.get("webpage_url", track.get("url", "#")),
            "source_type": track.get("source_type", "default"),
        }
    return {
        "title": get_messages("player.invalid_track", guild_id),
        "duration": 0,
        "webpage_url": "#",
        "source_type": "invalid",
    }


def create_queue_item_from_info(info: dict, guild_id: int) -> dict:
    if info.get("source_type") == "file":
        return {
            "url": info.get("url"),
            "title": info.get("title", get_messages("player.unknown_file", guild_id)),
            "webpage_url": None,
            "thumbnail": None,
            "is_single": False,
            "source_type": "file",
            "requester": info.get("requester"),
        }
    return {
        "url": info.get("webpage_url", info.get("url")),
        "title": info.get("title", get_messages("player.unknown_title", guild_id)),
        "webpage_url": info.get("webpage_url", info.get("url")),
        "thumbnail": info.get("thumbnail"),
        "is_single": False,
        "source_type": info.get("source_type"),
        "requester": info.get("requester"),
    }


def create_loading_bar(progress, width=12) -> str:
    progress = max(0.0, min(1.0, float(progress or 0)))
    filled = int(width * progress)
    pct = int(progress * 100)
    indicator = (
        "✅"
        if pct == 100
        else (
            "🔵"
            if pct >= 75
            else ("🟡" if pct >= 50 else ("🟠" if pct >= 25 else "🔴"))
        )
    )
    bar = "".join(["▰" if i < filled else "▱" for i in range(width)])
    return f"{indicator} `{bar}` **{pct}%**"


def format_lyrics_display(
    lyrics_lines: list, current_line_index: int, guild_id: int
) -> str:
    def clean(text):
        return text.replace("`", "'").replace("\r", "")

    parts = []
    if current_line_index == -1:
        parts.append(
            get_messages("karaoke.display.waiting_for_first_line", guild_id) + "\n"
        )
        for lo in lyrics_lines[:5]:
            for sub in clean(lo["text"]).split("\n"):
                if sub.strip():
                    parts.append(f"`{sub}`")
    else:
        start = max(0, current_line_index - 4)
        end = min(len(lyrics_lines), current_line_index + 5)
        for i in range(start, end):
            for idx, sub in enumerate(clean(lyrics_lines[i]["text"]).split("\n")):
                if not sub.strip():
                    continue
                prefix = "**»** " if i == current_line_index and idx == 0 else ""
                parts.append(f"{prefix}`{sub}`")
    return "\n".join(parts)[:4000]


def clear_audio_cache(guild_id: int):
    path = os.path.join("audio_cache", str(guild_id))
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            logger.error(f"Cache delete failed for {guild_id}: {e}")


# ════════════════════════════════════════════════════════════════════════════
# ▌ VOICE & AUDIO HELPERS
# ════════════════════════════════════════════════════════════════════════════


async def safe_stop(vc: discord.VoiceClient) -> None:
    """Kill FFmpeg process + call discord.py stop() cleanly."""
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return
    src = vc.source
    if isinstance(src, discord.PCMVolumeTransformer):
        src = src.original
    if (
        isinstance(src, discord.FFmpegPCMAudio)
        and hasattr(src, "_process")
        and src._process
    ):
        try:
            src._process.kill()
        except Exception:
            pass
    vc.stop()
    await asyncio.sleep(0.05)


_vc_status_pending: dict[int, str] = {}


async def update_voice_channel_status(guild_id: int, status_text: Optional[str] = None):
    """Debounced voice-channel status update (max 1 per 3 s per guild)."""
    state = get_guild_state(guild_id)

    async def _do_update():
        await asyncio.sleep(3)
        txt = _vc_status_pending.pop(guild_id, None)
        mp = state.music_player
        if not (mp.voice_client and mp.voice_client.channel):
            return
        try:
            await mp.voice_client.channel.edit(status=txt)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.error(f"[{guild_id}] VC status update error: {e}")
        finally:
            state._status_update_task = None

    _vc_status_pending[guild_id] = status_text  # overwrite with latest value
    if state._status_update_task is None or state._status_update_task.done():
        state._status_update_task = asyncio.create_task(_do_update())


async def ensure_voice_connection(
    interaction: discord.Interaction,
) -> Optional[discord.VoiceClient]:
    """Ensure voice connection with robust error handling and zombie connection cleanup."""
    guild_id = interaction.guild.id
    state = get_guild_state(guild_id)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    member = interaction.guild.get_member(interaction.user.id)
    if not member or not member.voice or not member.voice.channel:
        embed = Embed(
            description=get_messages("no_voice_channel", guild_id),
            color=0xFF9AA2 if is_kw else discord.Color.red(),
        )
        _send = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )
        await _send(embed=embed, ephemeral=True, silent=SILENT_MESSAGES)
        return None

    vc = interaction.guild.voice_client

    # Stale client → reset
    if vc and not vc.is_connected():
        mp.voice_client = None
        vc = None

    # Sync internal state
    if vc and mp.voice_client != vc:
        mp.voice_client = vc

    if not vc:
        try:
            vc = await member.voice.channel.connect()
            mp.voice_client = vc

            if mp.is_resuming_after_clean and mp.resume_info:
                info_r, time_r = mp.resume_info["info"], mp.resume_info["time"]
                mp.current_info, mp.current_url = info_r, info_r.get("url")
                bot.loop.create_task(
                    play_audio(guild_id, seek_time=time_r, is_a_loop=True)
                )
                mp.is_resuming_after_clean = False
                mp.resume_info = None

        except discord.ClientException as e:
            if "Already connected" in str(e):
                # Zombie connection — force-heal with recovery
                if mp.voice_client and mp.current_info:
                    elapsed = (
                        (time.time() - mp.playback_started_at) * mp.playback_speed
                        if mp.playback_started_at
                        else 0
                    )
                    mp.resume_info = {
                        "info": mp.current_info.copy(),
                        "time": mp.start_time + elapsed,
                    }
                    mp.is_resuming_after_clean = True
                try:
                    mp.is_cleaning = True
                    await mp.voice_client.disconnect(force=True)
                    await asyncio.sleep(0.5)
                finally:
                    mp.is_cleaning = False
                return await ensure_voice_connection(interaction)
            raise
        except Exception as e:
            embed = Embed(
                description=get_messages("connection_error", guild_id),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            )
            await interaction.followup.send(
                embed=embed, ephemeral=True, silent=SILENT_MESSAGES
            )
            logger.error(f"Voice connection error: {e}", exc_info=True)
            return None

    elif vc.channel != member.voice.channel:
        await vc.move_to(member.voice.channel)
        await asyncio.sleep(0.3)

    if isinstance(vc.channel, discord.StageChannel):
        if interaction.guild.me.voice and interaction.guild.me.voice.suppress:
            try:
                await interaction.guild.me.edit(suppress=False)
            except Exception:
                pass

    if not state.controller_channel_id:
        state.controller_channel_id = interaction.channel.id
        state.controller_message_id = None

    mp.text_channel = interaction.channel
    mp.voice_client = vc
    return vc


async def play_silence_loop(guild_id: int) -> None:
    """Play silence to keep bot in voice channel during 24/7 mode."""
    state = get_guild_state(guild_id)
    mp = state.music_player
    vc = mp.voice_client
    if not vc or not vc.is_connected():
        return

    logger.info(f"[{guild_id}] Starting silence loop.")
    mp.is_playing_silence = True
    source = "anullsrc=channel_layout=stereo:sample_rate=48000"
    ff_opts = {
        "before_options": "-re -f lavfi",
        "options": "-vn -f s16le -ar 48000 -ac 2",
    }

    try:
        while vc.is_connected():
            if not vc.is_playing():
                vc.play(discord.FFmpegPCMAudio(source, **ff_opts), after=lambda e: None)
            await asyncio.sleep(
                15
            )  # Check every 15s instead of 20s for better responsiveness
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[{guild_id}] Silence loop error: {e}")
    finally:
        if vc.is_connected() and mp.is_playing_silence:
            bot.loop.create_task(safe_stop(vc))
        mp.is_playing_silence = False


# ════════════════════════════════════════════════════════════════════════════
# ▌ CONTROLLER - Per-Guild Debounce
# ════════════════════════════════════════════════════════════════════════════


async def update_controller(
    bot_ref, guild_id: int, interaction: Optional[discord.Interaction] = None
):
    """Schedule a debounced controller update (100 ms coalescing window)."""
    state = get_guild_state(guild_id)

    async def _run():
        await asyncio.sleep(0.1)  # coalesce rapid calls
        state._controller_update_task = None
        await _do_update_controller(bot_ref, guild_id, interaction)

    # Cancel pending task so only the latest wins
    if state._controller_update_task and not state._controller_update_task.done():
        state._controller_update_task.cancel()

    state._controller_update_task = asyncio.create_task(_run())


async def _do_update_controller(
    bot_ref, guild_id: int, interaction: Optional[discord.Interaction]
):
    state = get_guild_state(guild_id)
    ch_id = state.controller_channel_id
    if not ch_id:
        return

    channel = bot_ref.get_channel(ch_id)
    if not channel:
        state.controller_channel_id = None
        state.controller_message_id = None
        return

    try:
        embed = await create_controller_embed(bot_ref, guild_id)
        view = MusicControllerView(bot_ref, guild_id)

        if interaction:
            await interaction.edit_original_response(
                content=None, embed=embed, view=view
            )
            msg = await interaction.original_response()
            old_id = state.controller_message_id
            if old_id and old_id != msg.id:
                try:
                    await (await channel.fetch_message(old_id)).delete()
                except Exception:
                    pass
            state.controller_message_id = msg.id
        else:
            msg_id = state.controller_message_id
            if msg_id:
                try:
                    msg = await channel.fetch_message(msg_id)
                    await msg.edit(embed=embed, view=view)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    new_msg = await channel.send(embed=embed, view=view, silent=True)
                    state.controller_message_id = new_msg.id
            else:
                new_msg = await channel.send(embed=embed, view=view, silent=True)
                state.controller_message_id = new_msg.id

    except discord.Forbidden:
        state.controller_channel_id = None
        state.controller_message_id = None
    except Exception as e:
        logger.error(
            f"Controller update failed for guild {guild_id}: {e}", exc_info=True
        )


# ════════════════════════════════════════════════════════════════════════════
# ▌ CONTROLLER EMBED
# ════════════════════════════════════════════════════════════════════════════


async def create_controller_embed(bot_ref, guild_id: int) -> Embed:
    state = get_guild_state(guild_id)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    vc = mp.voice_client
    is_conn = vc and vc.is_connected()
    is_play = is_conn and mp.current_info

    if not is_play:
        desc = get_messages(
            (
                "controller.idle.not_connected"
                if not is_conn
                else "controller.idle.description"
            ),
            guild_id,
        )
        embed = Embed(
            title=get_messages("controller.title", guild_id),
            description=desc,
            color=0x36393F,
        )
        embed.set_image(url="https://i.ibb.co/WvVpwbjm/download-1.jpg")
        embed.set_footer(text=get_messages("controller.footer.idle", guild_id))
        return embed

    info = mp.current_info
    title = clean_display_title(
        info.get("title", get_messages("player.unknown_title", guild_id))
    )
    artist = clean_display_title(
        info.get("uploader", get_messages("player.unknown_artist", guild_id))
    )
    # Use get_cleaned_song_info to avoid double artist names
    clean_title, clean_artist = get_cleaned_song_info(info, guild_id)
    title = clean_display_title(clean_title)
    artist = clean_display_title(clean_artist)
    thumb = info.get("thumbnail")
    req = info.get("requester", bot_ref.user)

    is_247n = state._24_7_mode and not mp.autoplay_enabled
    if is_247n and mp.radio_playlist:
        cur_url = info.get("url")
        try:
            ci = [t.get("url") for t in mp.radio_playlist].index(cur_url)
            queue_snap = mp.radio_playlist[ci + 1 :] + mp.radio_playlist[:ci]
        except (ValueError, IndexError):
            queue_snap = list(mp.queue._queue)
    else:
        queue_snap = list(mp.queue._queue)

    display_tracks = queue_snap[:5]

    # --- Selective hydration: only items missing duration/title ---
    lazy_to_resolve = [
        t
        for t in display_tracks
        if isinstance(t, LazySearchItem) and not t.resolved_info
    ]
    if lazy_to_resolve:
        await asyncio.gather(*[t.resolve() for t in lazy_to_resolve])

    need_hydrate = [
        t
        for t in display_tracks
        if isinstance(t, dict)
        and not t.get("duration", 0)
        and t.get("source_type") != "file"
        and t.get("url") not in url_cache
    ]
    if need_hydrate:
        results = await asyncio.gather(
            *[fetch_meta(t["url"], None) for t in need_hydrate]
        )
        for r in results:
            if r:
                url_cache[r["url"]] = r
        for t in display_tracks:
            if isinstance(t, dict) and t.get("url") in url_cache:
                t.update(url_cache[t["url"]])

    # Next-up
    next_text = get_messages("controller.nothing_next.title", guild_id)
    if display_tracks:
        nxt = display_tracks[0]
        ni = get_track_display_info(nxt)
        ntitle = clean_display_title(ni.get("title", ""))
        ndur = format_duration(ni.get("duration"))
        nurl = ni.get("webpage_url")
        fmt_k = f"controller.next_up.format.{ni.get('source_type','default')}"
        if translator.t(fmt_k, locale=state.locale.value) == fmt_k:
            fmt_k = "controller.next_up.format.default"
        next_text = get_messages(fmt_k, guild_id, title=ntitle, url=nurl, duration=ndur)

    # Queue lines 2-5
    q_lines = []
    for i, item in enumerate(display_tracks[1:5], start=2):
        di = get_track_display_info(item)
        it = clean_display_title(di.get("title", ""))[:40]
        idur = format_duration(di.get("duration"))
        iurl = di.get("webpage_url", "#")
        lk = f"controller.queue.line_display.{di.get('source_type','default')}"
        if translator.t(lk, locale=state.locale.value) == lk:
            lk = "controller.queue.line_display.default"
        dl = get_messages(lk, guild_id, title=it, duration=idur, url=iurl)
        q_lines.append(
            get_messages(
                "controller.queue_list.line_format.default",
                guild_id,
                i=i,
                display_line=dl,
            )
        )

    if not display_tracks:
        q_lines.append(get_messages("controller.queue_empty.title", guild_id))
    elif len(display_tracks) == 1:
        q_lines.append(get_messages("controller.no_other_songs.title", guild_id))

    q_lines.reverse()
    embed = Embed(
        title=get_messages("controller.title", guild_id),
        description="\n".join(q_lines),
        color=0xB5EAD7 if is_kw else discord.Color.blue(),
    )
    embed.add_field(
        name=get_messages("controller.next_up.title", guild_id),
        value=next_text,
        inline=False,
    )

    # Now playing
    if info.get("source_type") == "file":
        np_display = get_messages(
            "queue.now_playing_format.file", guild_id, title=title
        )
    else:
        np_display = f"**[{title}]({info.get('webpage_url', info.get('url','#'))})**"

    embed.add_field(
        name=get_messages("controller.now_playing.title", guild_id),
        value=get_messages(
            "controller.now_playing.value",
            guild_id,
            now_playing_title_display=np_display,
            artist=artist,
            requester_mention=req.mention,
            channel_name=vc.channel.name,
        ),
        inline=False,
    )

    if thumb:
        embed.set_thumbnail(url=thumb)

    # Status lines
    sl = []
    if mp.loop_current:
        sl.append(get_messages("queue_status_loop", guild_id))
    if state._24_7_mode:
        sl.append(
            get_messages("queue_status_24_7", guild_id).format(
                mode="Auto" if mp.autoplay_enabled else "Normal"
            )
        )
    elif mp.autoplay_enabled:
        sl.append(get_messages("queue_status_autoplay", guild_id))
    if sl:
        embed.add_field(
            name=get_messages("queue_status_title", guild_id),
            value="\n".join(sl),
            inline=False,
        )

    # Footer
    cnt = len(mp.radio_playlist) if is_247n and mp.radio_playlist else len(queue_snap)
    vol = int(mp.volume * 100)
    dinfo = _build_footer_dynamic_info(state, guild_id)
    if cnt == 0 and mp.current_info:
        ftxt = get_messages(
            "controller.footer.format_last_song",
            guild_id,
            dynamic_info=dinfo,
            volume=vol,
        )
    elif cnt > 0:
        ftxt = get_messages(
            "controller.footer.format",
            guild_id,
            count=cnt,
            dynamic_info=dinfo,
            volume=vol,
        )
    else:
        ftxt = get_messages("controller.footer.idle", guild_id)
    embed.set_footer(text=ftxt)
    return embed


def _build_footer_dynamic_info(state: GuildModel, guild_id: int) -> str:
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    if state.server_filters:
        fn = get_messages(f"filter.name.{next(iter(state.server_filters))}", guild_id)
        s = get_messages("controller.footer.filter", guild_id, filter_name=fn)
        return s + (" ✨" if is_kw else "")

    info = mp.current_info
    if not info:
        return get_messages(
            "controller.footer.ping", guild_id, ping_ms=round(bot.latency * 1000)
        )

    if info.get("source_type") == "file":
        return get_messages("controller.footer.file_source", guild_id)

    op = info.get("original_platform")
    if op:
        mode = "kaomoji" if is_kw else "display"
        k = f"platform.{mode}.{op.lower().replace(' ', '_')}"
        return get_messages(
            "controller.footer.source", guild_id, platform=get_messages(k, guild_id)
        )

    url = info.get("webpage_url", "").lower()
    if "youtube.com" in url or "youtu.be" in url:
        return get_messages("controller.footer.youtube_source", guild_id)
    if "soundcloud.com" in url:
        return get_messages("controller.footer.soundcloud_source", guild_id)
    if "twitch.tv" in url:
        return get_messages("controller.footer.twitch_source", guild_id)
    if "bandcamp.com" in url:
        return get_messages("controller.footer.bandcamp_source", guild_id)
    return get_messages(
        "controller.footer.ping", guild_id, ping_ms=round(bot.latency * 1000)
    )


# ════════════════════════════════════════════════════════════════════════════
# ▌ BOT INIT
# ════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True


class PlayifyBot(commands.Bot):
    async def close(self):
        await save_all_states()
        await super().close()


bot = PlayifyBot(command_prefix="!", intents=intents)

# ════════════════════════════════════════════════════════════════════════════
# ▌ LAZY SEARCH ITEM
# ════════════════════════════════════════════════════════════════════════════


class LazySearchItem:
    __slots__ = (
        "query_dict",
        "requester",
        "resolved_info",
        "search_lock",
        "original_platform",
        "title",
        "artist",
        "url",
        "webpage_url",
        "duration",
        "thumbnail",
        "source_type",
    )

    def __init__(
        self, query_dict: dict, requester, original_platform: str = "SoundCloud"
    ):
        self.query_dict = query_dict
        self.requester = requester
        self.resolved_info = None
        self.search_lock = asyncio.Lock()
        self.original_platform = original_platform
        self.title = query_dict.get("name", "Pending resolution...")
        self.artist = query_dict.get("artist", "Unknown Artist")
        self.url = "#"
        self.webpage_url = "#"
        self.duration = 0
        self.thumbnail = None
        self.source_type = "lazy"

    async def resolve(self):
        async with self.search_lock:
            if self.resolved_info:
                return self.resolved_info

            # Strip CJK brackets & special chars yang merusak YouTube search
            def _clean(s: str) -> str:
                s = re.sub(r"[（）《》【】「」『』〔〕〈〉\[\]]", " ", s)
                return re.sub(r"\s+", " ", s).strip()

            clean_title = _clean(self.title)
            clean_artist = _clean(self.artist)

            # Urutan strategi: dari paling spesifik ke paling generik
            search_terms = [
                f"{clean_title} {clean_artist}",
                f"{clean_title}",
                f"{self.title} {self.artist}",  # fallback: query asli tanpa "official"
            ]

            last_exc: Exception = ValueError("No results")
            for term in search_terms:
                try:
                    info = await fetch_video_info_with_retry(
                        f"ytsearch5:{sanitize_query(term)}",
                        {"noplaylist": True, "extract_flat": True},
                    )
                    entries = info.get("entries", [])
                    if not entries:
                        continue

                    best = entries[0]
                    url = best.get("webpage_url") or best.get("url", "")
                    if not url:
                        continue
                    if not url.startswith("http"):
                        url = f"https://www.youtube.com/watch?v={url}"

                    full = await asyncio.wait_for(
                        fetch_video_info_with_retry(url, {"noplaylist": True}),
                        timeout=20.0,
                    )
                    full["requester"] = self.requester
                    full["original_platform"] = self.original_platform
                    self.resolved_info = full
                    return full
                except Exception as e:
                    last_exc = e
                    continue

            logger.error(
                f"[LazyResolve] Failed '{self.title} {self.artist}': {last_exc}"
            )
            self.resolved_info = {"error": True, "title": f"{self.title} {self.artist}"}
            return self.resolved_info


# ════════════════════════════════════════════════════════════════════════════
# ▌ CORE PLAYBACK
# ════════════════════════════════════════════════════════════════════════════


async def handle_playback_error(guild_id: int, error: Exception):
    state = get_guild_state(guild_id)
    mp = state.music_player
    if not mp.text_channel:
        return
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    logger.error(f"Unhandled playback error in {guild_id}:\n{tb}")

    embed = Embed(
        title=get_messages("critical_error_title", guild_id),
        description=get_messages("critical_error_description", guild_id),
        color=0xFF9AA2 if state.locale == Locale.EN_X_KAWAII else discord.Color.red(),
    )
    embed.add_field(
        name=get_messages("critical_error_report_field", guild_id),
        value=get_messages("critical_error_report_value", guild_id),
        inline=False,
    )
    embed.add_field(
        name=get_messages("critical_error_details_field", guild_id),
        value=f"```\n{get_messages('error.critical.details_format', guild_id, url=mp.current_url, error_summary=str(error)[:500])}\n```",
        inline=False,
    )
    try:
        await mp.text_channel.send(embed=embed, silent=SILENT_MESSAGES)
    except Exception:
        pass

    # Full reset
    mp.current_task = mp.current_info = mp.current_url = None
    while not mp.queue.empty():
        mp.queue.get_nowait()
    if mp.voice_client:
        await mp.voice_client.disconnect()
    get_guild_state(guild_id).music_player = MusicPlayer()


async def play_audio(
    guild_id: int,
    seek_time: float = 0,
    is_a_loop: bool = False,
    song_that_just_ended=None,
):
    state = get_guild_state(guild_id)  # single lookup
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    if (
        mp.voice_client
        and mp.voice_client.is_playing()
        and not is_a_loop
        and not seek_time
    ):
        return

    # ------------------------------------------------------------------
    async def after_playing(error):
        """Handles playback completion with comprehensive error handling."""
        if error:
            logger.error(f"[{guild_id}] after_playing error: {error}")
            if (
                not mp.manual_stop
                and not mp.is_paused_by_leave
                and mp.current_info
                and mp.seek_info is None
                and (mp.voice_client and mp.voice_client.is_connected())
            ):
                retry_pos = mp.start_time
                if mp.playback_started_at:
                    retry_pos = (
                        mp.start_time
                        + (time.time() - mp.playback_started_at) * mp.playback_speed
                    )
                # Nonaktifkan semua filter agar tidak loop crash terus
                state.server_filters.clear()
                mp.playback_speed = 1.0
                mp.seek_info = retry_pos
                logger.warning(
                    f"[{guild_id}] FFmpeg crash detected — clearing filters and replaying from {retry_pos:.1f}s"
                )
                bot.loop.create_task(
                    play_audio(guild_id, seek_time=retry_pos, is_a_loop=True)
                )
                return

        try:
            if mp.is_paused_by_leave:
                return

            finished = mp.current_info
            if finished and mp.voice_client and mp.voice_client.channel:
                played_ms = int(
                    (time.time() - (mp.playback_started_at or time.time())) * 1000
                )
                vc_members = [
                    m.id for m in mp.voice_client.channel.members if not m.bot
                ]
                req = finished.get("requester")
                req_id = req.id if hasattr(req, "id") else bot.user.id
                bot.loop.create_task(
                    track_play(guild_id, finished, req_id, played_ms, vc_members)
                )

            if mp.manual_stop:
                mp.manual_stop = False
                bot.loop.create_task(
                    play_audio(guild_id, is_a_loop=False, song_that_just_ended=finished)
                )
                return

            if (
                not (mp.voice_client and mp.voice_client.is_connected())
                or mp.is_reconnecting
            ):
                return

            if mp.seek_info is not None:
                st, mp.seek_info = mp.seek_info, None
                bot.loop.create_task(play_audio(guild_id, seek_time=st, is_a_loop=True))
                return

            if mp.loop_current:
                bot.loop.create_task(play_audio(guild_id, is_a_loop=True))
                return

            mp.current_info = None
            if finished and state._24_7_mode and not mp.autoplay_enabled:
                await mp.queue.put(create_queue_item_from_info(finished, guild_id))

            bot.loop.create_task(
                play_audio(guild_id, is_a_loop=False, song_that_just_ended=finished)
            )
        except Exception as e:
            logger.error(
                f"[{guild_id}] Exception in after_playing callback: {e}", exc_info=True
            )
            # Attempt recovery by queuing next song
            try:
                bot.loop.create_task(
                    play_audio(guild_id, is_a_loop=False, song_that_just_ended=None)
                )
            except Exception as recovery_error:
                logger.critical(
                    f"[{guild_id}] Failed to recover from after_playing error: {recovery_error}",
                    exc_info=True,
                )

    # ------------------------------------------------------------------

    try:
        if not (is_a_loop or seek_time):
            # Cancel lyrics
            if mp.lyrics_task and not mp.lyrics_task.done():
                mp.lyrics_task.cancel()

            if mp.queue.empty():
                await _handle_empty_queue(
                    state, mp, guild_id, is_kw, song_that_just_ended
                )
                if mp.queue.empty():
                    mp.current_task = None
                    bot.loop.create_task(update_controller(bot, guild_id))
                    if not state._24_7_mode:
                        await asyncio.sleep(60)
                        if (
                            mp.voice_client
                            and not mp.voice_client.is_playing()
                            and len(mp.voice_client.channel.members) == 1
                        ):
                            await mp.voice_client.disconnect()
                    return

            next_item = await mp.queue.get()

            if isinstance(next_item, LazySearchItem):
                resolved = await next_item.resolve()
                if not resolved or resolved.get("error"):
                    ftitle = resolved.get("title", "unknown") if resolved else "unknown"
                    logger.warning(
                        f"[{guild_id}] Lazy resolve failed '{ftitle}', skipping."
                    )
                    if mp.text_channel:
                        try:
                            await mp.text_channel.send(
                                embed=Embed(
                                    title=get_messages(
                                        "lazy_resolve.error.title", guild_id
                                    ),
                                    description=get_messages(
                                        "lazy_resolve.error.description",
                                        guild_id,
                                        title=ftitle,
                                    ),
                                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                                ),
                                silent=SILENT_MESSAGES,
                            )
                        except discord.Forbidden:
                            pass
                    bot.loop.create_task(
                        play_audio(guild_id, song_that_just_ended=mp.current_info)
                    )
                    return
                next_item = resolved

            next_item.setdefault("requester", bot.user)
            if next_item.pop("skip_now_playing", False):
                mp.suppress_next_now_playing = True

            mp.current_info = next_item
            if not mp.loop_current:
                mp.history.append(next_item)

        if not (mp.voice_client and mp.voice_client.is_connected() and mp.current_info):
            return

        url_for_fetch = mp.current_info.get("webpage_url") or mp.current_info.get("url")

        # Refresh stream URL (skip for local files)
        if mp.current_info.get("source_type") != "file":
            # Check stream cache first
            cached_stream = stream_url_cache.get(url_for_fetch)
            if cached_stream and cached_stream.get("url"):
                mp.current_info.update(cached_stream)
            else:
                for attempt in range(3):
                    try:
                        refreshed = await asyncio.wait_for(
                            fetch_video_info_with_retry(url_for_fetch), timeout=15.0
                        )
                        mp.current_info.update(refreshed)
                        stream_url = refreshed.get("url")
                        if stream_url:
                            stream_url_cache[url_for_fetch] = {"url": stream_url}
                        break
                    except asyncio.TimeoutError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)

        audio_url = mp.current_info.get("url")
        if not audio_url:
            bot.loop.create_task(
                play_audio(guild_id, song_that_just_ended=mp.current_info)
            )
            return

        mp.is_current_live = (
            mp.current_info.get("is_live", False)
            or mp.current_info.get("live_status") == "is_live"
        )

        # Build FFmpeg options
        filter_chain = ",".join(
            AUDIO_FILTERS[f] for f in state.server_filters if f in AUDIO_FILTERS
        )
        ff = {"options": "-vn"}
        if mp.current_info.get("source_type") != "file":
            ff["before_options"] = (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            )
        if seek_time:
            ff["before_options"] = (
                f"-ss {seek_time} {ff.get('before_options', '')}".strip()
            )
        if filter_chain:
            ff["options"] = f"{ff['options']} -af {filter_chain}"

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(audio_url, **ff),
            volume=mp.volume,
        )

        if not (mp.voice_client and mp.voice_client.is_connected()):
            return

        # Ensure nothing is playing before we start
        if mp.voice_client.is_playing():
            mp.voice_client.stop()
            await asyncio.sleep(0.2)

        try:
            mp.voice_client.play(
                source, after=lambda e: bot.loop.create_task(after_playing(e))
            )
        except discord.errors.ClientException as e:
            if "Already playing audio" in str(e):
                logger.warning(f"[{guild_id}] Already playing audio, stopping and retrying...")
                mp.voice_client.stop()
                await asyncio.sleep(0.5)
                try:
                    mp.voice_client.play(
                        source, after=lambda e: bot.loop.create_task(after_playing(e))
                    )
                except Exception as retry_error:
                    logger.error(f"[{guild_id}] Retry failed: {retry_error}")
                    return
            else:
                raise
        mp.start_time = seek_time
        mp.playback_started_at = time.time()

        # Voice channel status (debounced)
        # Cek apakah ini lagu baru (bukan sekadar resume dari loop/seek lagu yg sama)
        is_new_song = not is_a_loop or (
            is_a_loop and seek_time == 0 and not mp.loop_current
        )
        if mp.current_info and is_new_song:
            clean_t, clean_a = get_cleaned_song_info(mp.current_info, guild_id)
            clean_t = clean_t.strip()
            clean_a = clean_a.strip()
            # Hindari duplikat: sembunyikan artis jika sudah terdeteksi di judul
            artist_in_title = clean_a.lower() in clean_t.lower() if clean_a else True
            show_artist = (
                clean_a and not artist_in_title and clean_a.lower() != "unknown artist"
            )
            status = f"🎶 {clean_t}" + (f" - {clean_a}" if show_artist else "")
            bot.loop.create_task(update_voice_channel_status(guild_id, status[:476]))

        # Controller re-anchor check (only on new songs)
        if state.controller_channel_id and not is_a_loop and not seek_time:
            ch_id, msg_id = state.controller_channel_id, state.controller_message_id
            if ch_id and msg_id:
                try:
                    ch = bot.get_channel(ch_id)
                    if ch and ch.last_message_id != msg_id:
                        try:
                            await (await ch.fetch_message(msg_id)).delete()
                        except Exception:
                            pass
                        state.controller_message_id = None
                except Exception:
                    pass

        bot.loop.create_task(update_controller(bot, guild_id))

        if mp.suppress_next_now_playing:
            mp.suppress_next_now_playing = False

    except Exception as e:
        await handle_playback_error(guild_id, e)


async def _handle_empty_queue(state, mp, guild_id, is_kw, song_that_just_ended):
    # Mode 24/7 tanpa autoplay: putar ulang radio playlist
    if state._24_7_mode and not mp.autoplay_enabled and mp.radio_playlist:
        for t in mp.radio_playlist:
            await mp.queue.put(t)
        return

    # Autoplay: cari rekomendasi (berlaku untuk mode normal maupun 24/7+autoplay)
    if mp.autoplay_enabled:
        await _run_autoplay(state, mp, guild_id, is_kw, song_that_just_ended)


async def _run_autoplay(
    state: GuildModel, mp: MusicPlayer, guild_id: int, is_kw: bool, song_that_just_ended
):
    """Find seed URL and fill queue with 10 recommended tracks."""
    seed_url = None
    progress_msg = None

    seed_src = song_that_just_ended or (mp.history[-1] if mp.history else None)
    if seed_src:
        candidate = seed_src.get("webpage_url") or seed_src.get("url", "")
        if any(s in candidate for s in ["youtube.com", "youtu.be", "soundcloud.com"]):
            seed_url = candidate
        else:
            # Walk history to find a YouTube/SC URL
            src_list = (
                mp.radio_playlist
                if (state._24_7_mode and mp.radio_playlist)
                else mp.history
            )
            for track in reversed(src_list):
                fb = track.get("webpage_url") or track.get("url", "")
                if fb and any(
                    s in fb for s in ["youtube.com", "youtu.be", "soundcloud.com"]
                ):
                    seed_url = fb
                    break

    if not seed_url:
        return

    added = 0
    try:
        if mp.text_channel:
            initial = Embed(
                title=get_messages("autoplay_loading_title", guild_id),
                description=get_messages(
                    "autoplay_loading_description", guild_id
                ).format(progress_bar=create_loading_bar(0), processed=0, total="?"),
                color=0xC7CEEA if is_kw else discord.Color.blue(),
            )
            progress_msg = await mp.text_channel.send(
                embed=initial, silent=SILENT_MESSAGES
            )

        recs = []
        if "youtube.com" in seed_url or "youtu.be" in seed_url:
            mix_url = get_mix_playlist_url(seed_url)
            if mix_url:
                info = await run_ydl_with_low_priority(
                    {"extract_flat": True, "quiet": True, "noplaylist": False}, mix_url
                )
                cur_vid = get_video_id(seed_url)
                recs = [
                    e
                    for e in info.get("entries", [])
                    if e and get_video_id(e.get("url", "")) != cur_vid
                ][:10]
        elif "soundcloud.com" in seed_url:
            tid = await get_soundcloud_track_id(seed_url)
            stn_url = get_soundcloud_station_url(tid)
            if stn_url:
                info = await run_ydl_with_low_priority(
                    {"extract_flat": True, "quiet": True, "noplaylist": False}, stn_url
                )
                recs = info.get("entries", [])[1:11]

        if recs:
            orig_req = seed_src.get("requester", bot.user) if seed_src else bot.user
            total = len(recs)
            for i, e in enumerate(recs):
                await mp.queue.put(
                    {
                        "url": e.get("url"),
                        "title": e.get("title", "Unknown Title"),
                        "webpage_url": e.get("webpage_url", e.get("url")),
                        "is_single": True,
                        "requester": orig_req,
                    }
                )
                added += 1
                if progress_msg and ((i + 1) % 5 == 0 or (i + 1) == total):
                    emb = progress_msg.embeds[0]
                    emb.description = get_messages(
                        "autoplay_loading_description", guild_id
                    ).format(
                        progress_bar=create_loading_bar((i + 1) / total),
                        processed=added,
                        total=total,
                    )
                    await progress_msg.edit(embed=emb)
                    await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"Autoplay error: {e}", exc_info=True)
    finally:
        if progress_msg:
            if added:
                emb = progress_msg.embeds[0]
                emb.title = None
                emb.description = get_messages(
                    "autoplay_finished_description", guild_id
                ).format(count=added)
                emb.color = 0xB5EAD7 if is_kw else discord.Color.green()
                await progress_msg.edit(embed=emb)
            else:
                await progress_msg.delete()


async def get_soundcloud_track_id(url):
    if "soundcloud.com" not in url:
        return None
    try:
        loop = asyncio.get_running_loop()

        def _get_id():
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                return ydl.extract_info(url, download=False).get("id")

        return await loop.run_in_executor(None, _get_id)
    except Exception:
        return None


def get_soundcloud_station_url(track_id):
    return (
        f"https://soundcloud.com/discover/sets/track-stations:{track_id}"
        if track_id
        else None
    )


# ════════════════════════════════════════════════════════════════════════════
# ▌ KARAOKE TASK
# ════════════════════════════════════════════════════════════════════════════


async def update_karaoke_task(guild_id: int):
    state = get_guild_state(guild_id)
    mp = state.music_player
    last_i = -1
    footer_removed = False

    while mp.voice_client and mp.voice_client.is_connected():
        try:
            if not mp.voice_client.is_playing():
                await asyncio.sleep(0.5)
                continue
            if not mp.playback_started_at:
                await asyncio.sleep(0.5)
                continue
            elapsed_real = time.time() - mp.playback_started_at
            eff_time = mp.start_time + elapsed_real * mp.playback_speed
            cur_i = -1
            for i, line in enumerate(mp.synced_lyrics):
                if eff_time * 1000 >= line["time"]:
                    cur_i = i
                else:
                    break
            if cur_i != last_i:
                last_i = cur_i
                new_desc = format_lyrics_display(mp.synced_lyrics, cur_i, guild_id)
                if mp.lyrics_message and mp.lyrics_message.embeds:
                    emb = mp.lyrics_message.embeds[0]
                    emb.description = new_desc
                    if not footer_removed:
                        emb.set_footer(text=None)
                        footer_removed = True
                    await mp.lyrics_message.edit(embed=emb)
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Karaoke task error: {e}")
            break

    if mp.lyrics_message:
        try:
            await mp.lyrics_message.edit(
                content=get_messages("karaoke.session_finished", guild_id),
                embed=None,
                view=None,
            )
        except discord.NotFound:
            pass
    mp.lyrics_task = mp.lyrics_message = None


# ════════════════════════════════════════════════════════════════════════════
# ▌ PLATFORM URL PROCESSORS
# ════════════════════════════════════════════════════════════════════════════


async def process_spotify_url(url, interaction):
    guild_id = interaction.guild.id
    state = get_guild_state(guild_id)
    is_kw = state.locale == Locale.EN_X_KAWAII
    clean_url = url.split("?")[0]
    loop = asyncio.get_running_loop()

    if spotify_scraper_client:
        try:
            tracks = []
            if "playlist" in clean_url:
                d = await loop.run_in_executor(
                    None, lambda: spotify_scraper_client.get_playlist_info(clean_url)
                )
                for t in d.get("tracks", []):
                    artist_name = (t.get("artists") or [{}])[0].get(
                        "name", "Unknown Artist"
                    )
                    tracks.append((t.get("name", "Unknown"), artist_name))
            elif "album" in clean_url:
                d = await loop.run_in_executor(
                    None, lambda: spotify_scraper_client.get_album_info(clean_url)
                )
                for t in d.get("tracks", []):
                    artist_name = (t.get("artists") or [{}])[0].get(
                        "name", "Unknown Artist"
                    )
                    tracks.append((t.get("name", "Unknown"), artist_name))
            elif "track" in clean_url:
                d = await loop.run_in_executor(
                    None, lambda: spotify_scraper_client.get_track_info(clean_url)
                )
                artist_name = (d.get("artists") or [{}])[0].get(
                    "name", "Unknown Artist"
                )
                tracks.append((d.get("name", "Unknown"), artist_name))
            if tracks:
                return tracks
        except Exception as e:
            logger.error(f"SpotifyScraper failed: {e}")

    embed = Embed(
        description=get_messages("spotify_error", guild_id),
        color=0xFF9AA2 if is_kw else discord.Color.red(),
    )
    await interaction.followup.send(silent=SILENT_MESSAGES, embed=embed, ephemeral=True)
    return None


async def process_deezer_url(url, interaction):
    guild_id = interaction.guild.id
    try:
        share_re = re.compile(r"^(https?://)?(link\.deezer\.com)/s/.+$")
        if share_re.match(url):
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    url = str(resp.url)

        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) > 1 and len(parts[0]) == 2:
            parts = parts[1:]
        rtype, rid = parts[0], parts[1].split("?")[0]
        base = "https://api.deezer.com"
        tracks = []
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession() as session:
            if rtype == "track":
                async with session.get(f"{base}/track/{rid}", timeout=timeout) as resp:
                    d = await resp.json()
                tracks.append((d["title"], d["artist"]["name"]))

            elif rtype == "playlist":
                nxt = f"{base}/playlist/{rid}/tracks"
                while nxt:
                    async with session.get(nxt, timeout=timeout) as resp:
                        d = await resp.json()
                    for t in d["data"]:
                        tracks.append((t["title"], t["artist"]["name"]))
                    nxt = d.get("next")

            elif rtype == "album":
                async with session.get(
                    f"{base}/album/{rid}/tracks", timeout=timeout
                ) as resp:
                    d = await resp.json()
                for t in d["data"]:
                    tracks.append((t["title"], t["artist"]["name"]))

            elif rtype == "artist":
                async with session.get(
                    f"{base}/artist/{rid}/top?limit=10", timeout=timeout
                ) as resp:
                    d = await resp.json()
                for t in d["data"]:
                    tracks.append((t["title"], t["artist"]["name"]))

        return tracks if tracks else None
    except Exception as e:
        logger.error(f"Deezer error: {e}")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("deezer_error", guild_id),
                color=discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
        return None


async def process_apple_music_url(url, interaction):
    guild_id = interaction.guild.id
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
                )
            )
            page = await ctx.new_page()
            await page.route("**/*.{png,jpg,jpeg,svg,woff,woff2}", lambda r: r.abort())
            await page.goto(
                url.split("?")[0], wait_until="domcontentloaded", timeout=90_000
            )

            parts = urlparse(url).path.strip("/").split("/")
            rtype = parts[1] if len(parts) > 1 else "unknown"
            tracks = []

            if rtype in ("album", "playlist"):
                await page.wait_for_selector("div.songs-list-row", timeout=20_000)
                main_artist = ""
                try:
                    el = await page.query_selector(".headings__subtitles a")
                    if el:
                        main_artist = await el.inner_text()
                except Exception:
                    pass
                for row in await page.query_selector_all("div.songs-list-row"):
                    try:
                        te = await row.query_selector("div.songs-list-row__song-name")
                        ae = await row.query_selector_all(
                            "div.songs-list-row__by-line a"
                        )
                        t = await te.inner_text() if te else ""
                        a = (
                            " & ".join([await e.inner_text() for e in ae])
                            if ae
                            else main_artist
                        )
                        if t:
                            tracks.append((t.strip(), a.strip()))
                    except Exception:
                        pass
            elif rtype == "song":
                try:
                    await page.wait_for_selector(
                        'script[id="schema:song"]', timeout=15_000
                    )
                    d = json.loads(
                        await page.locator('script[id="schema:song"]').inner_text()
                    )
                    tracks.append(
                        (d["audio"]["name"], d["audio"]["byArtist"][0]["name"])
                    )
                except Exception:
                    t = await page.locator(
                        'h1[data-testid="song-title"]'
                    ).first.inner_text()
                    a = await page.locator(
                        'span[data-testid="song-subtitle-artists"] a'
                    ).first.inner_text()
                    if t and a:
                        tracks.append((t.strip(), a.strip()))

            return tracks or None
    except Exception as e:
        logger.error(f"Apple Music error: {e}")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("apple_music_error", guild_id),
                color=discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
        return None
    finally:
        if browser:
            await browser.close()


async def process_tidal_url(url, interaction):
    guild_id = interaction.guild.id
    browser = None
    try:
        clean = url.split("?")[0]
        parts = urlparse(clean).path.strip("/").split("/")
        rtype = next(
            (x for x in ["playlist", "album", "mix", "track", "video"] if x in parts),
            None,
        )
        if not rtype:
            raise ValueError("Unsupported Tidal URL")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            )
            await page.goto(clean, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            tracks = []

            if rtype in ("playlist", "album", "mix"):
                seen_ids = set()
                for _ in range(500):
                    els = await page.query_selector_all("div[data-track-id]")
                    new = 0
                    for el in els:
                        tid = await el.get_attribute("data-track-id")
                        if tid and tid not in seen_ids:
                            seen_ids.add(tid)
                            new += 1
                            te = await el.query_selector(
                                'span._titleText_51cccae, span[data-test="table-cell-title"]'
                            )
                            ae = await el.query_selector("a._item_39605ae")
                            if te and ae:
                                t = (await te.inner_text()).split("<span>")[0].strip()
                                a = await ae.inner_text()
                                if t and a:
                                    tracks.append((t, a))
                    if not new and _:
                        break
                    if els:
                        await els[-1].scroll_into_view_if_needed(timeout=10_000)
                    await asyncio.sleep(0.75)
            elif rtype in ("track", "video"):
                try:
                    t = await page.locator(
                        'span[data-test="now-playing-track-title"]'
                    ).first.inner_text(timeout=5_000)
                    a = await page.locator(
                        'a[data-test="grid-item-detail-text-title-artist"]'
                    ).first.inner_text(timeout=5_000)
                    tracks = [(t.strip(), a.strip())]
                except Exception:
                    pt = await page.title()
                    if " - " in pt:
                        a, t = pt.split(" - ", 1)
                        tracks = [(t.split(" on TIDAL")[0].strip(), a.strip())]

            return list(dict.fromkeys(tracks)) or None
    except Exception as e:
        logger.error(f"Tidal error: {e}")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("tidal_error", guild_id),
                color=discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
        return None
    finally:
        if browser:
            await browser.close()


async def process_amazon_music_url(url, interaction):
    guild_id = interaction.guild.id
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                await page.click(
                    'music-button:has-text("Accepter les cookies")', timeout=7_000
                )
            except Exception:
                pass

            tracks = []
            if "/albums/" in url or "/tracks/" in url:
                await page.wait_for_selector(
                    'script[type="application/ld+json"]',
                    state="attached",
                    timeout=20_000,
                )
                for txt in await page.locator(
                    'script[type="application/ld+json"]'
                ).all_inner_texts():
                    d = json.loads(txt)
                    if d.get("@type") == "MusicAlbum":
                        aa = d.get("byArtist", {}).get("name", "")
                        for item in d.get("itemListElement", []):
                            tracks.append(
                                (item["name"], item.get("byArtist", {}).get("name", aa))
                            )
                        break
                    elif d.get("@type") == "MusicRecording":
                        tracks.append(
                            (d["name"], d.get("byArtist", {}).get("name", ""))
                        )
                        break
            elif "/playlists/" in url or "/user-playlists/" in url:
                await page.wait_for_selector(
                    "music-image-row[primary-text]", timeout=20_000
                )
                await asyncio.sleep(3.5)
                rows = await page.evaluate(
                    """() => {
                    return [...document.querySelectorAll('music-image-row[primary-text]')]
                        .map(r => ({title: r.getAttribute('primary-text'), artist: r.getAttribute('secondary-text-1')}))
                        .filter(r => r.title && r.artist);
                }"""
                )
                tracks = [(r["title"], r["artist"]) for r in rows]

            return tracks or None
    except Exception as e:
        logger.error(f"Amazon Music error: {e}")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("amazon_music_error", guild_id),
                color=discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
        return None
    finally:
        if browser:
            await browser.close()


# ════════════════════════════════════════════════════════════════════════════
# ▌ UI CLASSES - Views & Modals
# ════════════════════════════════════════════════════════════════════════════


class AddSongModal(discord.ui.Modal):
    def __init__(self, bot_ref, guild_id):
        super().__init__(title=get_messages("controller.label.add_song", guild_id))
        self.bot_ref = bot_ref
        self.guild_id = guild_id
        self.query_input = discord.ui.TextInput(
            label=get_messages("add_song_modal.label", guild_id),
            placeholder=get_messages("add_song_modal.placeholder", guild_id),
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction):
        cmd = self.bot_ref.tree.get_command("play")
        if cmd:
            await cmd.callback(interaction, query=self.query_input.value)
        else:
            await interaction.response.send_message(
                "Play command not found.", ephemeral=True
            )


class MusicControllerView(View):
    def __init__(self, bot_ref, guild_id):
        super().__init__(timeout=None)
        self.bot_ref = bot_ref
        self.guild_id = guild_id
        self._emojis = {
            "controller_previous": "⏮️",
            "controller_pause": "⏸️",
            "controller_resume": "▶️",
            "controller_skip": "⏭️",
            "controller_stop": "⏹️",
            "controller_add_song": "➕",
            "controller_shuffle": "🔀",
            "controller_loop": "🔁",
            "controller_autoplay": "➡️",
            "controller_vol_down": "🔉",
            "controller_vol_up": "🔊",
            "controller_lyrics": "📜",
            "controller_karaoke": "🎤",
            "controller_queue": "📜",
            "controller_jump_to_song": "⤵️",
        }
        self.update_buttons()

    def update_buttons(self):
        mp = get_player(self.guild_id)
        vc = mp.voice_client
        active = vc and (vc.is_playing() or vc.is_paused())
        paused = vc and vc.is_paused()
        is_kw = get_mode(self.guild_id)

        for child in self.children:
            if not hasattr(child, "custom_id"):
                continue
            cid = child.custom_id
            if cid == "controller_pause":
                child.label = get_messages(
                    "controller.label.resume" if paused else "controller.label.pause",
                    self.guild_id,
                )
            elif cid == "controller_jump_to_song":
                child.label = get_messages("controller.label.jump_to", self.guild_id)
            elif cid == "controller_vol_down":
                child.label = get_messages("controller.label.vol_down", self.guild_id)
            elif cid == "controller_vol_up":
                child.label = get_messages("controller.label.vol_up", self.guild_id)
            else:
                key = f"controller.label.{cid.replace('controller_', '')}"
                child.label = get_messages(key, self.guild_id)
            child.emoji = (
                None
                if is_kw
                else (
                    self._emojis.get(
                        "controller_resume"
                        if (cid == "controller_pause" and paused)
                        else cid
                    )
                )
            )

        # Toggle styles
        for cid, attr in [
            ("controller_pause", None),
            ("controller_loop", "loop_current"),
            ("controller_autoplay", "autoplay_enabled"),
        ]:
            btn = discord.utils.get(self.children, custom_id=cid)
            if btn:
                if cid == "controller_pause":
                    btn.style = ButtonStyle.success if paused else ButtonStyle.secondary
                else:
                    btn.style = (
                        ButtonStyle.success
                        if getattr(mp, attr)
                        else ButtonStyle.secondary
                    )

        for child in self.children:
            if hasattr(child, "custom_id") and child.custom_id not in (
                "controller_stop",
                "controller_add_song",
            ):
                child.disabled = not active
        for cid in ("controller_stop", "controller_add_song"):
            btn = discord.utils.get(self.children, custom_id=cid)
            if btn:
                btn.disabled = False

    # ---- Row 0 buttons ----
    @discord.ui.button(
        style=ButtonStyle.primary, custom_id="controller_previous", row=0
    )
    async def previous_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.defer()

        THRESHOLD = 5
        cur_pos = 0
        if vc.is_playing() and mp.playback_started_at:
            cur_pos = (
                mp.start_time
                + (time.time() - mp.playback_started_at) * mp.playback_speed
            )
        elif vc.is_paused():
            cur_pos = mp.start_time

        if mp.loop_current or cur_pos > THRESHOLD:
            mp.is_seeking, mp.seek_info = True, 0
            await safe_stop(vc)
            return await interaction.response.defer()

        async with mp.queue_lock:
            if len(mp.history) < 2:
                return await interaction.response.send_message(
                    get_messages("player.history.empty", self.guild_id),
                    ephemeral=True,
                    silent=True,
                )
            rest = list(mp.queue._queue)
            cur_pop = mp.history.pop()
            prev_pop = mp.history.pop()
            new_q = asyncio.Queue(maxsize=5000)
            for item in [prev_pop, cur_pop] + rest:
                await new_q.put(item)
            mp.queue = new_q

        mp.manual_stop = True
        await safe_stop(vc)
        await interaction.response.defer()

    @discord.ui.button(style=ButtonStyle.secondary, custom_id="controller_pause", row=0)
    async def pause_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        vc = mp.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.defer()
        if vc.is_paused():
            vc.resume()
            if mp.playback_started_at is None:
                mp.playback_started_at = time.time()
        else:
            vc.pause()
            if mp.playback_started_at:
                mp.start_time += (
                    time.time() - mp.playback_started_at
                ) * mp.playback_speed
                mp.playback_started_at = None
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    @discord.ui.button(style=ButtonStyle.primary, custom_id="controller_skip", row=0)
    async def skip_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        vc = mp.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.defer()
        if mp.lyrics_task and not mp.lyrics_task.done():
            mp.lyrics_task.cancel()
        if not mp.loop_current:
            mp.manual_stop = True
        await safe_stop(vc)
        await interaction.response.defer()

    @discord.ui.button(style=ButtonStyle.danger, custom_id="controller_stop", row=0)
    async def stop_button(self, interaction, button):
        gid = interaction.guild_id
        mp = get_player(gid)
        await interaction.response.defer()
        vc = mp.voice_client
        if vc and vc.is_connected():
            await safe_stop(vc)
            if mp.current_task and not mp.current_task.done():
                mp.current_task.cancel()
            await vc.disconnect()
            clear_audio_cache(gid)
            get_guild_state(gid).music_player = MusicPlayer()
            await update_controller(self.bot_ref, gid)

    @discord.ui.button(
        style=ButtonStyle.success, custom_id="controller_add_song", row=0
    )
    async def add_song_button(self, interaction, button):
        await interaction.response.send_modal(
            AddSongModal(self.bot_ref, interaction.guild_id)
        )

    # ---- Row 1 buttons ----
    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_shuffle", row=1
    )
    async def shuffle_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        async with mp.queue_lock:
            if mp.queue.empty():
                return await interaction.response.send_message(
                    get_messages("queue_empty", self.guild_id),
                    ephemeral=True,
                    silent=True,
                )
            items = list(mp.queue._queue)
            random.shuffle(items)
            q = asyncio.Queue(maxsize=5000)
            for i in items:
                await q.put(i)
            mp.queue = q
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    @discord.ui.button(style=ButtonStyle.secondary, custom_id="controller_loop", row=1)
    async def loop_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        mp.loop_current = not mp.loop_current
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_autoplay", row=1
    )
    async def autoplay_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        mp.autoplay_enabled = not mp.autoplay_enabled
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_vol_down", row=1
    )
    async def vol_down_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        mp.volume = max(0.0, mp.volume - 0.1)
        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = mp.volume
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_vol_up", row=1
    )
    async def vol_up_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        mp.volume = min(2.0, mp.volume + 0.1)
        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = mp.volume
        await update_controller(self.bot_ref, interaction.guild_id)
        await interaction.response.defer()

    # ---- Row 2 buttons ----
    async def _run_command(self, interaction: discord.Interaction, name: str):
        cmd = self.bot_ref.tree.get_command(name)
        if cmd:
            try:
                await cmd.callback(interaction)
            except Exception as e:
                logger.error(f"_run_command '{name}' error: {e}", exc_info=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"/{name} not found.", ephemeral=True, silent=True
                )

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_lyrics", row=2
    )
    async def lyrics_button(self, interaction, button):
        await self._run_command(interaction, "lyrics")

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_karaoke", row=2
    )
    async def karaoke_button(self, interaction, button):
        await self._run_command(interaction, "karaoke")

    @discord.ui.button(style=ButtonStyle.primary, custom_id="controller_queue", row=2)
    async def queue_button(self, interaction, button):
        await self._run_command(interaction, "queue")

    @discord.ui.button(
        style=ButtonStyle.secondary, custom_id="controller_jump_to_song", row=2
    )
    async def jump_button(self, interaction, button):
        mp = get_player(interaction.guild_id)
        if mp.queue.empty():
            return await interaction.response.send_message(
                get_messages("queue_empty", interaction.guild_id),
                ephemeral=True,
                silent=True,
            )
        await self._run_command(interaction, "jumpto")


# ════════════════════════════════════════════════════════════════════════════
# ▌ QUEUE / REMOVE / JUMPTO VIEWS
# ════════════════════════════════════════════════════════════════════════════


class QueueView(View):
    def __init__(self, interaction, tracks, items_per_page=5):
        super().__init__(timeout=300.0)
        self.interaction = interaction
        self.guild_id = interaction.guild_id
        self.mp = get_player(self.guild_id)
        self.tracks = tracks
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = math.ceil(len(tracks) / items_per_page) if tracks else 1
        self.message = None
        self.is_kw = get_mode(self.guild_id)

        self.prev_btn = Button(
            style=ButtonStyle.secondary,
            label=get_messages("queue_button.previous", self.guild_id),
        )
        self.next_btn = Button(
            style=ButtonStyle.secondary,
            label=get_messages("queue_button.next", self.guild_id),
        )
        self.prev_btn.callback = self._prev
        self.next_btn.callback = self._next
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        self._update_states()

    def _update_states(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= self.total_pages - 1

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass

    async def _prev(self, interaction):
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
        self._update_states()
        await interaction.edit_original_response(
            embed=await self._build_embed(), view=self
        )

    async def _next(self, interaction):
        await interaction.response.defer()
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self._update_states()
        await interaction.edit_original_response(
            embed=await self._build_embed(), view=self
        )

    async def _build_embed(self) -> Embed:
        gid = self.guild_id
        mp = self.mp
        sl = []
        if mp.loop_current:
            sl.append(get_messages("queue_status_loop", gid))
        state = get_guild_state(gid)
        if state._24_7_mode:
            sl.append(
                get_messages("queue_status_24_7", gid).format(
                    mode="Auto" if mp.autoplay_enabled else "Normal"
                )
            )
        elif mp.autoplay_enabled:
            sl.append(get_messages("queue_status_autoplay", gid))
        vol = int(mp.volume * 100)
        if vol != 100:
            sl.append(get_messages("queue_status_volume", gid).format(level=vol))

        embed = Embed(
            title=get_messages("queue_title", gid),
            description=get_messages(
                "queue_last_song" if not self.tracks else "queue_description",
                gid,
                count=len(self.tracks),
            ),
            color=0xB5EAD7 if self.is_kw else discord.Color.blue(),
        )
        embed.add_field(
            name=get_messages("queue_status_title", gid),
            value="\n".join(sl) or get_messages("queue_status_none", gid),
            inline=False,
        )

        if mp.current_info:
            t = mp.current_info.get("title", "Unknown")
            url = mp.current_info.get("webpage_url", mp.current_url)
            disp = (
                get_messages("queue.now_playing_format.file", gid, title=t)
                if mp.current_info.get("source_type") == "file"
                else f"[{t}]({url})"
            )
            embed.add_field(
                name=get_messages("now_playing_in_queue", gid), value=disp, inline=False
            )

        si, ei = (
            self.current_page * self.items_per_page,
            (self.current_page + 1) * self.items_per_page,
        )
        page_tracks = self.tracks[si:ei]

        # Hydrate only stale items
        need = [
            t
            for t in page_tracks
            if isinstance(t, dict)
            and not t.get("duration", 0)
            and t.get("source_type") != "file"
            and t.get("url") not in url_cache
        ]
        if need:
            results = await asyncio.gather(*[fetch_meta(t["url"], None) for t in need])
            for r in results:
                if r:
                    url_cache[r["url"]] = r
            for t in page_tracks:
                if isinstance(t, dict) and t.get("url") in url_cache:
                    t.update(url_cache[t["url"]])

        lines = []
        for i, item in enumerate(page_tracks, start=si):
            di = get_track_display_info(item)
            title = di.get("title", "")
            if di.get("source_type") in ("lazy", "file"):
                line = f"`{title}`"
            else:
                line = f"[{title}]({di.get('webpage_url','#')})"
            lines.append(
                get_messages(
                    "queue.track_line.full_format", gid, i=i + 1, display_line=line
                )
            )

        if lines:
            embed.add_field(
                name=get_messages("queue_next", gid),
                value="\n".join(lines),
                inline=False,
            )
        embed.set_footer(
            text=get_messages(
                "queue_page_footer",
                gid,
                current_page=self.current_page + 1,
                total_pages=self.total_pages,
            )
        )
        return embed


class RemoveSelect(discord.ui.Select):
    def __init__(self, tracks_on_page, page_offset, guild_id):
        options = [
            discord.SelectOption(
                label=f"{i+page_offset+1}. {get_track_display_info(t).get('title','?')}"[
                    :100
                ],
                value=str(i + page_offset),
            )
            for i, t in enumerate(tracks_on_page)
        ]
        super().__init__(
            placeholder=get_messages("remove_placeholder", guild_id),
            min_values=1,
            max_values=len(options) or 1,
            options=options,
        )

    async def callback(self, interaction):
        gid = interaction.guild_id
        mp = get_player(gid)
        ids = sorted([int(v) for v in self.values], reverse=True)
        q = list(mp.queue._queue)
        removed = []
        for idx in ids:
            if 0 <= idx < len(q):
                removed.append(get_track_display_info(q.pop(idx)).get("title", "?"))
        nq = asyncio.Queue(maxsize=5000)
        for item in q:
            await nq.put(item)
        mp.queue = nq
        bot.loop.create_task(update_controller(bot, gid))
        self.view.clear_items()
        await interaction.response.edit_message(
            content=get_messages("remove_processed", gid), embed=None, view=self.view
        )
        state = get_guild_state(gid)
        is_kw = state.locale == Locale.EN_X_KAWAII
        embed = Embed(
            title=get_messages("remove_success_title", gid, count=len(removed)),
            description="\n".join(f"• `{t}`" for t in removed),
            color=0xB5EAD7 if is_kw else discord.Color.green(),
        )
        await interaction.channel.send(embed=embed, silent=SILENT_MESSAGES)


class RemoveView(View):
    def __init__(self, interaction, all_tracks):
        super().__init__(timeout=300.0)
        self.interaction = interaction
        self.guild_id = interaction.guild_id
        self.all_tracks = all_tracks
        self.current_page = 0
        self.items_per_page = 25
        self.total_pages = math.ceil(len(all_tracks) / 25) if all_tracks else 1

    async def update_view(self):
        self.clear_items()
        si, ei = self.current_page * 25, (self.current_page + 1) * 25
        page = self.all_tracks[si:ei]
        need = [
            t
            for t in page
            if isinstance(t, dict)
            and not t.get("title")
            and t.get("source_type") != "file"
        ]
        if need:
            results = await asyncio.gather(*[fetch_meta(t["url"], None) for t in need])
            for r in results:
                if r:
                    for t in page:
                        if isinstance(t, dict) and t.get("url") == r["url"]:
                            t["title"] = r["title"]
        self.add_item(RemoveSelect(page, si, self.guild_id))
        if self.total_pages > 1:
            prev = Button(
                label=get_messages("remove_button.previous", self.guild_id),
                style=ButtonStyle.secondary,
                disabled=self.current_page == 0,
            )
            nxt = Button(
                label=get_messages("remove_button.next", self.guild_id),
                style=ButtonStyle.secondary,
                disabled=self.current_page >= self.total_pages - 1,
            )
            prev.callback = self._prev
            nxt.callback = self._next
            self.add_item(prev)
            self.add_item(nxt)

    async def _prev(self, interaction):
        await interaction.response.defer()
        self.current_page = max(0, self.current_page - 1)
        await self.update_view()
        await interaction.edit_original_response(view=self)

    async def _next(self, interaction):
        await interaction.response.defer()
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view()
        await interaction.edit_original_response(view=self)


class JumpToSelect(discord.ui.Select):
    def __init__(self, tracks_on_page, page_offset, guild_id):
        options = [
            discord.SelectOption(
                label=f"{i+page_offset+1}. {get_track_display_info(t).get('title','?')}"[
                    :100
                ],
                value=str(i + page_offset),
            )
            for i, t in enumerate(tracks_on_page)
        ]
        super().__init__(
            placeholder=get_messages("jumpto.placeholder", guild_id),
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction):
        gid = interaction.guild_id
        mp = get_player(gid)
        vc = mp.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.defer()
        idx = int(self.values[0])
        async with mp.queue_lock:
            q = list(mp.queue._queue)
            if not 0 <= idx < len(q):
                return await interaction.response.defer()
            mp.history.extend(q[:idx])
            nq = asyncio.Queue(maxsize=5000)
            for item in q[idx:]:
                await nq.put(item)
            mp.queue = nq
        await interaction.response.defer()
        await interaction.delete_original_response()
        mp.manual_stop = True
        await safe_stop(vc)


class JumpToView(View):
    def __init__(self, interaction, all_tracks):
        super().__init__(timeout=300.0)
        self.interaction = interaction
        self.guild_id = interaction.guild_id
        self.all_tracks = all_tracks
        self.current_page = 0
        self.items_per_page = 25
        self.total_pages = math.ceil(len(all_tracks) / 25) if all_tracks else 1

    async def update_view(self):
        self.clear_items()
        si = self.current_page * 25
        self.add_item(JumpToSelect(self.all_tracks[si : si + 25], si, self.guild_id))
        if self.total_pages > 1:
            prev = Button(
                label=get_messages("queue.button.previous", self.guild_id),
                style=ButtonStyle.secondary,
                disabled=self.current_page == 0,
            )
            nxt = Button(
                label=get_messages("queue.button.next", self.guild_id),
                style=ButtonStyle.secondary,
                disabled=self.current_page >= self.total_pages - 1,
            )
            prev.callback = self._prev
            nxt.callback = self._next
            self.add_item(prev)
            self.add_item(nxt)

    async def _prev(self, interaction):
        await interaction.response.defer()
        self.current_page = max(0, self.current_page - 1)
        await self.update_view()
        await interaction.edit_original_response(view=self)

    async def _next(self, interaction):
        await interaction.response.defer()
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view()
        await interaction.edit_original_response(view=self)


# Seek views (unchanged, kept for compatibility)
class SeekModal(discord.ui.Modal):
    def __init__(self, view, guild_id):
        super().__init__(title=get_messages("seek_modal_title", guild_id))
        self.seek_view = view
        self.guild_id = guild_id
        self.mp = get_player(guild_id)
        self.ts_input = discord.ui.TextInput(
            label=get_messages("seek_modal_label", guild_id),
            placeholder=get_messages("seek_modal.placeholder", guild_id),
            required=True,
        )
        self.add_item(self.ts_input)

    async def on_submit(self, interaction):
        secs = parse_time(self.ts_input.value)
        if secs is None:
            return await interaction.response.send_message(
                get_messages("seek.fail_invalid_time", self.guild_id),
                ephemeral=True,
                silent=True,
            )
        self.mp.is_seeking, self.mp.seek_info = True, secs
        if self.mp.voice_client:
            await safe_stop(self.mp.voice_client)
        await self.seek_view.update_embed(interaction, jumped=True)


class SeekView(View):
    REWIND = FORWARD = 15

    def __init__(self, interaction):
        super().__init__(timeout=300.0)
        self.interaction = interaction
        self.guild_id = interaction.guild.id
        self.mp = get_player(self.guild_id)
        self.is_kw = get_mode(self.guild_id)
        self.message = None
        self.update_task = None
        self.rewind_btn.label = get_messages("seek.button.rewind", self.guild_id)
        self.jump_btn.label = get_messages("seek.button.jump_to", self.guild_id)
        self.forward_btn.label = get_messages("seek.button.forward", self.guild_id)

    def _current_pos(self) -> int:
        vc = self.mp.voice_client
        if not vc or not vc.is_playing():
            return int(self.mp.start_time)
        if self.mp.playback_started_at:
            return int(
                self.mp.start_time
                + (time.time() - self.mp.playback_started_at) * self.mp.playback_speed
            )
        return int(self.mp.start_time)

    async def start_update_task(self):
        if self.update_task is None or self.update_task.done():
            self.update_task = asyncio.create_task(self._loop())

    async def _loop(self):
        while not self.is_finished():
            await asyncio.sleep(2)
            if (
                self.mp.voice_client
                and self.mp.voice_client.is_playing()
                and self.message
            ):
                try:
                    await self.update_embed()
                except discord.NotFound:
                    break

    async def update_embed(self, interaction=None, jumped=False):
        if not self.mp.current_info:
            return
        pos = self._current_pos()
        total = self.mp.current_info.get("duration", 0)
        title = self.mp.current_info.get("title", "")
        desc = f"**{title}**\n\n{create_progress_bar(pos, total, self.guild_id)} **{format_duration(pos)} / {format_duration(total)}**"
        embed = Embed(
            title=get_messages("seek_interface_title", self.guild_id),
            description=desc,
            color=0xB5EAD7 if self.is_kw else discord.Color.blue(),
        )
        embed.set_footer(text=get_messages("seek_interface_footer", self.guild_id))
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(style=ButtonStyle.primary, emoji="⏪")
    async def rewind_btn(self, interaction, button):
        t = max(0, self._current_pos() - self.REWIND)
        self.mp.is_seeking, self.mp.seek_info = True, t
        if self.mp.voice_client:
            await safe_stop(self.mp.voice_client)
        await self.update_embed(interaction, jumped=True)

    @discord.ui.button(style=ButtonStyle.secondary, emoji="✏️")
    async def jump_btn(self, interaction, button):
        await interaction.response.send_modal(SeekModal(self, self.guild_id))

    @discord.ui.button(style=ButtonStyle.primary, emoji="⏩")
    async def forward_btn(self, interaction, button):
        t = self._current_pos() + self.FORWARD
        self.mp.is_seeking, self.mp.seek_info = True, t
        if self.mp.voice_client:
            await safe_stop(self.mp.voice_client)
        await self.update_embed(interaction, jumped=True)

    async def on_timeout(self):
        if self.update_task:
            self.update_task.cancel()
        if self.message:
            for c in self.children:
                c.disabled = True
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# Search, Lyrics, Karaoke views — kept as-is (no logic changes, just re-used original code structure)
class SearchSelect(discord.ui.Select):
    def __init__(self, results, guild_id):
        options = [
            discord.SelectOption(
                label=v.get("title", "?")[:100],
                description=get_messages(
                    "search.result_description", guild_id, artist=v.get("uploader", "?")
                )[:100],
                value=v.get("webpage_url", v.get("url")),
                emoji="🎵",
            )
            for v in results
        ]
        super().__init__(
            placeholder=get_messages("search_placeholder", guild_id),
            min_values=1,
            max_values=1,
            options=options,
        )
        self.guild_id = guild_id

    async def callback(self, interaction):
        gid = interaction.guild_id
        state = get_guild_state(gid)
        mp = state.music_player
        is_kw = state.locale == Locale.EN_X_KAWAII
        url = self.values[0]
        self.disabled = True
        self.placeholder = get_messages("search_selection_made", gid)
        await interaction.response.edit_message(view=self.view)
        try:
            info = await fetch_video_info_with_retry(
                url, {"format": "bestaudio/best", "quiet": True, "noplaylist": True}
            )
            if not info:
                raise ValueError("No info")
            item = {
                "url": info.get("webpage_url", info.get("url")),
                "title": info.get("title", "Unknown"),
                "webpage_url": info.get("webpage_url", info.get("url")),
                "thumbnail": info.get("thumbnail"),
                "is_single": True,
                "requester": interaction.user,
            }
            await mp.queue.put(item)
            vc = mp.voice_client  # cache ref — could be None
            if not vc or not (vc.is_playing() or vc.is_paused()):
                mp.suppress_next_now_playing = True
                mp.current_task = asyncio.create_task(play_audio(gid))
        except Exception as e:
            logger.error(f"Search select callback error: {e}")
            await interaction.followup.send(
                embed=Embed(
                    description=get_messages("player.error.add_failed", gid),
                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                ),
                silent=True,
                ephemeral=True,
            )


class SearchView(View):
    def __init__(self, results, guild_id):
        super().__init__(timeout=300.0)
        self.add_item(SearchSelect(results, guild_id))


class FilterView(View):
    """Audio filter toggle view with per-section organization."""

    def __init__(self, interaction: discord.Interaction) -> None:
        super().__init__(timeout=None)
        self.guild_id = interaction.guild.id
        self.state = get_guild_state(self.guild_id)
        for i, effect in enumerate(AUDIO_FILTERS):
            label = get_messages(f"filter.name.{effect}", self.guild_id)
            is_on = effect in self.state.server_filters
            btn = Button(
                label=label,
                custom_id=f"filter_{effect}",
                style=ButtonStyle.success if is_on else ButtonStyle.secondary,
                row=i // 5,  # 9 effects → row 0 (idx 0-4), row 1 (idx 5-8)
            )
            btn.callback = self._cb
            self.add_item(btn)

    async def _cb(self, interaction: discord.Interaction) -> None:
        """Handle filter toggle with optimized style updates."""
        effect = interaction.data["custom_id"].removeprefix("filter_")
        af = self.state.server_filters
        if effect in af:
            af.remove(effect)
        else:
            af.add(effect)

        # Update button styles efficiently
        for child in self.children:
            if isinstance(child, Button):
                effect_name = (
                    child.custom_id.removeprefix("filter_") if child.custom_id else ""
                )
                child.style = (
                    ButtonStyle.success if effect_name in af else ButtonStyle.secondary
                )

        await interaction.response.edit_message(view=self)

        # Apply filter if music is playing
        mp = get_player(self.guild_id)
        if mp.voice_client and (
            mp.voice_client.is_playing() or mp.voice_client.is_paused()
        ):
            old_speed = mp.playback_speed
            elapsed = 0
            if mp.playback_started_at:
                elapsed = (
                    time.time() - mp.playback_started_at
                ) * old_speed + mp.start_time
            mp.playback_speed = get_speed_multiplier_from_filters(af)
            mp.is_seeking, mp.seek_info = True, elapsed
            await safe_stop(mp.voice_client)


class LyricsView(View):
    """Paginated lyrics display with refinement support."""

    def __init__(self, pages: List[str], original_embed: Embed, guild_id: int) -> None:
        super().__init__(timeout=300.0)
        self.pages = pages
        self.original_embed = original_embed
        self.current_page = 0
        self.guild_id = guild_id
        self.prev_btn.label = get_messages("lyrics.button.previous", guild_id)
        self.next_btn.label = get_messages("lyrics.button.next", guild_id)
        self.refine_btn.label = get_messages("lyrics.button.refine", guild_id)

    def _update(self) -> Embed:
        """Update embed with current page."""
        self.original_embed.description = self.pages[self.current_page]
        self.original_embed.set_footer(
            text=get_messages(
                "lyrics.embed.footer",
                self.guild_id,
                current_page=self.current_page + 1,
                total_pages=len(self.pages),
            )
        )
        return self.original_embed

    @discord.ui.button(style=discord.ButtonStyle.grey)
    async def prev_btn(self, interaction: discord.Interaction, button: Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = False
        await interaction.response.edit_message(embed=self._update(), view=self)

    @discord.ui.button(style=discord.ButtonStyle.grey)
    async def next_btn(self, interaction: discord.Interaction, button: Button) -> None:
        if self.current_page < max(0, len(self.pages) - 1):
            self.current_page += 1
        self.next_btn.disabled = self.current_page >= max(0, len(self.pages) - 1)
        self.prev_btn.disabled = False
        await interaction.response.edit_message(embed=self._update(), view=self)

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.secondary)
    async def refine_btn(
        self, interaction: discord.Interaction, button: Button
    ) -> None:
        await interaction.response.send_modal(RefineLyricsModal(interaction.message))


class RefineLyricsModal(discord.ui.Modal):
    """Modal for refining lyrics search query."""

    def __init__(self, message: discord.Message) -> None:
        self.msg_to_edit = message
        self.guild_id = message.guild.id
        self.is_kw = get_mode(self.guild_id)
        super().__init__(title=get_messages("lyrics.refine_modal.title", self.guild_id))
        self.query = discord.ui.TextInput(
            label=get_messages("lyrics.refine_modal.label", self.guild_id),
            placeholder=get_messages("lyrics.refine_modal.placeholder", self.guild_id),
            style=discord.TextStyle.short,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle lyrics refinement submission."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not genius:
            return await interaction.followup.send(
                get_messages("api.genius.not_configured", self.guild_id),
                ephemeral=True,
                silent=True,
            )
        loop = asyncio.get_running_loop()
        song = await loop.run_in_executor(
            None, lambda: genius.search_song(self.query.value)
        )
        if not song:
            return await interaction.followup.send(
                get_messages(
                    "lyrics.error.refine_failed", self.guild_id, query=self.query.value
                ),
                ephemeral=True,
                silent=True,
            )
        await _display_genius_lyrics(
            song, self.msg_to_edit, interaction, self.guild_id, self.is_kw
        )


class KaraokeWarningView(View):
    def __init__(self, interaction, karaoke_coro):
        super().__init__(timeout=180.0)
        self.interaction = interaction
        self.karaoke_coro = karaoke_coro
        self.cont_btn.label = get_messages(
            "karaoke.warning.button", interaction.guild.id
        )

    @discord.ui.button(style=ButtonStyle.success)
    async def cont_btn(self, interaction, button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message(
                get_messages("command.error.user_only", interaction.guild_id),
                ephemeral=True,
                silent=True,
            )
        get_guild_state(interaction.guild_id).karaoke_disclaimer_shown = True
        button.disabled = True
        button.label = get_messages(
            "karaoke.warning.acknowledged_button", interaction.guild_id
        )
        await interaction.response.edit_message(view=self)
        await self.karaoke_coro()


class KaraokeRetryView(View):
    def __init__(self, original_interaction, suggested_query, guild_id):
        super().__init__(timeout=180.0)
        self.orig_int = original_interaction
        self.suggested = suggested_query
        self.guild_id = guild_id
        self.retry_btn.label = get_messages("karaoke.retry_button", guild_id)
        self.genius_btn.label = get_messages("karaoke.genius_fallback_button", guild_id)

    @discord.ui.button(style=ButtonStyle.primary)
    async def retry_btn(self, interaction, button):
        await interaction.response.send_modal(
            KaraokeRetryModal(self.orig_int, self.suggested)
        )

    @discord.ui.button(style=ButtonStyle.secondary)
    async def genius_btn(self, interaction, button):
        for c in self.children:
            c.disabled = True
        await self.orig_int.edit_original_response(view=self)
        await interaction.response.defer()
        msg = get_messages("lyrics.fallback_warning", self.guild_id)
        await fetch_and_display_genius_lyrics(self.orig_int, fallback_message=msg)


class KaraokeRetryModal(discord.ui.Modal):
    def __init__(self, orig_interaction, suggested):
        self.orig_int = orig_interaction
        self.guild_id = orig_interaction.guild_id
        self.mp = get_player(self.guild_id)
        self.is_kw = get_mode(self.guild_id)
        super().__init__(
            title=get_messages("karaoke.refine_modal.title", self.guild_id)
        )
        self.query = discord.ui.TextInput(
            label=get_messages("karaoke.refine_modal.label", self.guild_id),
            placeholder=get_messages("karaoke.refine_modal.placeholder", self.guild_id),
            default=suggested,
            style=discord.TextStyle.short,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop = asyncio.get_running_loop()
        lrc = None
        try:
            lrc = await asyncio.wait_for(
                loop.run_in_executor(None, syncedlyrics.search, self.query.value),
                timeout=10.0,
            )
        except Exception:
            pass

        lines = _parse_lrc(lrc)
        if not lines:
            return await interaction.followup.send(
                get_messages("karaoke.not_found_description", self.guild_id).format(
                    query=self.query.value
                ),
                ephemeral=True,
                silent=True,
            )

        self.mp.synced_lyrics = lines
        t, _ = get_cleaned_song_info(self.mp.current_info, self.guild_id)
        embed = Embed(
            title=get_messages("karaoke.embed.title", self.guild_id, title=t),
            description=get_messages("karaoke.embed.description", self.guild_id),
            color=0xC7CEEA if self.is_kw else discord.Color.blue(),
        )
        self.mp.lyrics_message = await self.orig_int.followup.send(
            embed=embed, wait=True, silent=True
        )
        self.mp.lyrics_task = asyncio.create_task(update_karaoke_task(self.guild_id))
        await interaction.followup.send(
            get_messages("karaoke.retry.success", self.guild_id),
            ephemeral=True,
            silent=True,
        )


class LyricsRetryView(View):
    def __init__(self, orig_interaction, suggested_query, guild_id):
        super().__init__(timeout=180.0)
        self.orig_int = orig_interaction
        self.suggested = suggested_query
        self.guild_id = guild_id
        self.retry_btn.label = get_messages("lyrics.refine_button", guild_id)

    @discord.ui.button(style=ButtonStyle.primary)
    async def retry_btn(self, interaction, button):
        await interaction.response.send_modal(
            _LyricsRetryModal(self.orig_int, self.suggested, self.guild_id)
        )


class _LyricsRetryModal(discord.ui.Modal):
    def __init__(self, orig_int, suggested, guild_id):
        self.orig_int = orig_int
        self.guild_id = guild_id
        self.is_kw = get_mode(guild_id)
        super().__init__(title=get_messages("lyrics.refine_modal.title", guild_id))
        self.query = discord.ui.TextInput(
            label=get_messages("lyrics.refine_modal.label", guild_id),
            placeholder=get_messages("lyrics.refine_modal.placeholder", guild_id),
            default=suggested,
            style=discord.TextStyle.short,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not genius:
            return await interaction.followup.send(
                get_messages("api.genius.not_configured", self.guild_id),
                ephemeral=True,
                silent=True,
            )
        loop = asyncio.get_running_loop()
        song = await loop.run_in_executor(
            None, lambda: genius.search_song(self.query.value)
        )
        if not song:
            return await interaction.followup.send(
                get_messages(
                    "lyrics.error.refine_failed", self.guild_id, query=self.query.value
                ),
                ephemeral=True,
                silent=True,
            )
        msg = await self.orig_int.original_response()
        await _display_genius_lyrics(song, msg, interaction, self.guild_id, self.is_kw)


def _lrc_ms(mm, ss, cs):
    ms = int(cs) * 10 if len(cs) == 2 else int(cs) if len(cs) == 3 else int(cs[:3])
    return int(mm) * 60_000 + int(ss) * 1_000 + ms


def _parse_lrc(lrc_text: Optional[str]) -> list:
    if not lrc_text:
        return []
    return [
        {
            "time": _lrc_ms(m.group(1), m.group(2), m.group(3)),
            "text": m.group(4).strip(),
        }
        for m in TIME_TAG_RE.finditer(lrc_text)
    ]


async def _display_genius_lyrics(
    song, message_or_none, interaction, guild_id, is_kw, fallback_message=None
):
    lyrics = song.lyrics
    lines = [
        l
        for l in lyrics.split("\n")
        if not any(w in l.lower() for w in ("contributor", "lyrics", "embed"))
    ]
    clean = "\n".join(lines).strip()
    pages = []
    buf = ""
    for line in clean.split("\n"):
        if len(buf) + len(line) + 1 > 1_500:
            pages.append(f"```{buf.strip()}```")
            buf = ""
        buf += line + "\n"
    if buf.strip():
        pages.append(f"```{buf.strip()}```")

    # FIX 2: Embed diisi dengan benar, bukan Embed(...)
    base_embed = Embed(
        title=get_messages("lyrics.embed.title", guild_id, title=song.title),
        url=song.url,
        color=0xB5EAD7 if is_kw else discord.Color.green(),
    )
    if fallback_message:
        base_embed.set_author(name=fallback_message)

    view = LyricsView(pages, base_embed, guild_id)
    fe = view._update()
    view.children[0].disabled = True
    if len(pages) <= 1:
        view.children[1].disabled = True

    if message_or_none and hasattr(message_or_none, "edit"):
        await message_or_none.edit(embed=fe, view=view)
    else:
        msg = await interaction.followup.send(
            embed=fe, view=view, wait=True, silent=SILENT_MESSAGES
        )
        view.message = msg
    if interaction and not interaction.response.is_done():
        await interaction.followup.send(
            get_messages("lyrics.success.updated", guild_id),
            ephemeral=True,
            silent=True,
        )


async def fetch_and_display_genius_lyrics(interaction, fallback_message=None):
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    loop = asyncio.get_running_loop()

    if not genius:
        return await interaction.followup.send(
            get_messages("api.genius.not_configured", gid), ephemeral=True, silent=True
        )

    clean_title, artist = get_cleaned_song_info(mp.current_info, gid)
    query = f"{clean_title} {artist}"

    try:
        res = await loop.run_in_executor(
            None, lambda: genius.search_songs(query, per_page=5)
        )
        hits = res.get("hits", []) if res else []
        if not hits:
            embed = Embed(
                title=get_messages("lyrics.error.not_found.title", gid),
                description=get_messages(
                    "lyrics.error.not_found.description", gid, query=query
                ),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            )
            view = LyricsRetryView(interaction, clean_title, gid)
            return await interaction.followup.send(
                embed=embed, view=view, silent=SILENT_MESSAGES
            )

        info = hits[0]["result"]
        song = await loop.run_in_executor(
            None, lambda: genius.search_song(song_id=info["id"])
        )
        if not song or not song.lyrics:
            raise ValueError("No lyrics")

        # FIX 4: Langsung panggil _display_genius_lyrics dengan fallback_message,
        # tidak perlu buat embed terpisah yang tidak dipakai
        await _display_genius_lyrics(
            song, None, interaction, gid, is_kw, fallback_message=fallback_message
        )

    except Exception as e:
        logger.error(f"Genius fetch error '{query}': {e}", exc_info=True)
        await interaction.followup.send(
            get_messages("api.lyrics.generic_fetch_error", gid),
            ephemeral=True,
            silent=True,
        )


# ==============================================================================
# 17. SLASH COMMANDS
# ==============================================================================


async def play_autocomplete(
    interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current or len(current) < 3 or re.match(r"https?://", current):
        return []
    try:
        prefix = "ytsearch10:"
        info = await asyncio.wait_for(
            fetch_video_info_with_retry(
                f"{prefix}{sanitize_query(current)}",
                {"extract_flat": True, "noplaylist": True, "socket_timeout": 5},
            ),
            timeout=2.5,  # Discord autocomplete deadline is 3 s — bail early
        )
        choices = []
        for e in info.get("entries", []):
            title = e.get("title", "")
            url = e.get("webpage_url", e.get("url", ""))
            if not title or not url:
                continue
            dur = e.get("duration")
            name = f"{title} - {format_duration(dur)}" if dur else title
            val = url if len(url) <= 100 else title[:100]
            choices.append(app_commands.Choice(name=name[:100], value=val))
        return choices
    except (asyncio.TimeoutError, discord.NotFound):
        return []  # interaction already expired — silently drop
    except Exception:
        return []


@bot.tree.command(name="play", description="Play a link or search for a song")
@app_commands.describe(query="Link or title of the song/video to play")
@app_commands.autocomplete(query=play_autocomplete)
async def play(interaction: discord.Interaction, query: str):
    if not interaction.guild:
        return await interaction.response.send_message(
            get_messages("command.error.guild_only", 0), ephemeral=True
        )

    gid = interaction.guild.id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player

    if not interaction.response.is_done():
        await interaction.response.defer()

    vc = await ensure_voice_connection(interaction)
    if not vc:
        return

    async def add_single(info: dict):
        item = {
            "url": info.get("webpage_url", info.get("url", "#")),
            "title": info.get("title", "Unknown Title"),
            "webpage_url": info.get("webpage_url", info.get("url", "#")),
            "thumbnail": info.get("thumbnail"),
            "is_single": True,
            "requester": interaction.user,
        }
        await mp.queue.put(item)
        await update_controller(bot, gid, interaction=interaction)
        if not (vc.is_playing() or vc.is_paused()):
            mp.current_task = asyncio.create_task(play_audio(gid))

    async def add_platform_playlist(tracks, platform):
        for name, artist in tracks:
            await mp.queue.put(
                LazySearchItem(
                    {"name": name, "artist": artist}, interaction.user, platform
                )
            )
        key_map = {
            "Spotify": ("spotify_playlist_added", "spotify_playlist_description"),
            "Deezer": ("deezer_playlist_added", "deezer_playlist_description"),
            "Apple Music": (
                "apple_music_playlist_added",
                "apple_music_playlist_description",
            ),
            "Tidal": ("tidal_playlist_added", "tidal_playlist_description"),
            "Amazon Music": (
                "amazon_music_playlist_added",
                "amazon_music_playlist_description",
            ),
        }
        tk, dk = key_map[platform]
        embed = Embed(
            title=get_messages(tk, gid),
            description=get_messages(
                dk, gid, count=len(tracks), failed=0, failed_tracks=""
            ),
            color=0xB5EAD7 if is_kw else discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, silent=SILENT_MESSAGES)
        if not (vc.is_playing() or vc.is_paused()):
            mp.current_task = asyncio.create_task(play_audio(gid))
        bot.loop.create_task(update_controller(bot, gid))

    try:
        # Platform detection
        processors = [
            (SPOTIFY_REGEX, process_spotify_url, "Spotify"),
            (DEEZER_REGEX, process_deezer_url, "Deezer"),
            (APPLE_MUSIC_REGEX, process_apple_music_url, "Apple Music"),
            (TIDAL_REGEX, process_tidal_url, "Tidal"),
            (AMAZON_MUSIC_REGEX, process_amazon_music_url, "Amazon Music"),
        ]
        for regex, processor, platform in processors:
            if regex.match(query):
                tracks = await processor(query, interaction)
                if not tracks:
                    return
                if len(tracks) == 1:
                    name, artist = tracks[0]
                    # Selalu cari di YouTube Music
                    prefix = "scsearch:" if IS_PUBLIC_VERSION else "ytsearch:"
                    info = await fetch_video_info_with_retry(
                        f"{prefix}{sanitize_query(f'{name} {artist} official')}",
                        {"noplaylist": True},
                    )
                    await add_single(info["entries"][0] if "entries" in info else info)
                else:
                    await add_platform_playlist(tracks, platform)
                return

        # Direct URL (YouTube, SoundCloud, direct file link)
        if (
            YOUTUBE_REGEX.match(query)
            or SOUNDCLOUD_REGEX.match(query)
            or DIRECT_LINK_REGEX.match(query)
        ):
            info = await fetch_video_info_with_retry(
                query, {"extract_flat": True, "noplaylist": False}
            )
            if "entries" in info and len(info["entries"]) > 1:
                # Limit playlist additions to prevent unbounded queue growth (max 5000 items)
                entries_to_add = info["entries"]

                for e in entries_to_add:
                    await mp.queue.put(
                        {
                            "url": e.get("url"),
                            "title": e.get("title", "Unknown"),
                            "webpage_url": e.get("webpage_url", e.get("url")),
                            "thumbnail": e.get("thumbnail"),
                            "duration": e.get("duration", 0),
                            "requester": interaction.user,
                            "is_single": False,
                        }
                    )
                embed = Embed(
                    title=get_messages("playlist_added", gid),
                    description=get_messages(
                        "playlist_description", gid, count=len(info["entries"])
                    ),
                    color=0xB5EAD7 if is_kw else discord.Color.green(),
                )
                await interaction.followup.send(embed=embed, silent=SILENT_MESSAGES)
                if not (vc.is_playing() or vc.is_paused()):
                    mp.current_task = asyncio.create_task(play_audio(gid))
            else:
                video = (info.get("entries") or [info])[0]
                await add_single(video)
            return

        # Keyword search
        prefix = "scsearch:" if IS_PUBLIC_VERSION else "ytsearch:"
        info = await fetch_video_info_with_retry(
            f"{prefix}{sanitize_query(query)}", {"noplaylist": True}
        )
        if not info.get("entries"):
            raise ValueError("No results")
        await add_single(info["entries"][0])

    except Exception as e:
        logger.error(f"/play error for '{query}': {e}", exc_info=True)
        try:
            await interaction.edit_original_response(
                content=get_messages("error.command.fallback", gid, error=str(e)),
                embed=None,
                view=None,
            )
        except Exception:
            await interaction.followup.send(
                embed=Embed(
                    description=get_messages("search_error", gid),
                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                ),
                ephemeral=True,
                silent=True,
            )


@bot.tree.command(name="play-files", description="Plays uploaded audio/video files.")
@app_commands.describe(
    file1="First file",
    file2="Optional",
    file3="Optional",
    file4="Optional",
    file5="Optional",
    file6="Optional",
    file7="Optional",
    file8="Optional",
    file9="Optional",
    file10="Optional",
)
async def play_files(
    interaction: discord.Interaction,
    file1: discord.Attachment,
    file2: discord.Attachment = None,
    file3: discord.Attachment = None,
    file4: discord.Attachment = None,
    file5: discord.Attachment = None,
    file6: discord.Attachment = None,
    file7: discord.Attachment = None,
    file8: discord.Attachment = None,
    file9: discord.Attachment = None,
    file10: discord.Attachment = None,
):
    if not interaction.guild:
        return await interaction.response.send_message(
            get_messages("command.error.guild_only", 0), ephemeral=True
        )

    gid = interaction.guild_id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player

    await interaction.response.defer()
    vc = await ensure_voice_connection(interaction)
    if not vc:
        return

    cache_dir = os.path.join("audio_cache", str(gid))
    os.makedirs(cache_dir, exist_ok=True)

    attachments = [
        f
        for f in [file1, file2, file3, file4, file5, file6, file7, file8, file9, file10]
        if f
    ]
    added, failed = [], []

    for att in attachments:
        if not att.content_type or not (
            att.content_type.startswith("audio/")
            or att.content_type.startswith("video/")
        ):
            failed.append(att.filename)
            continue
        fp = os.path.join(cache_dir, att.filename)
        try:
            await att.save(fp)
            dur = get_file_duration(fp)
            item = {
                "url": fp,
                "title": att.filename,
                "webpage_url": None,
                "thumbnail": None,
                "is_single": True,
                "source_type": "file",
                "duration": dur,
                "requester": interaction.user,
            }
            await mp.queue.put(item)
            if state._24_7_mode:
                mp.radio_playlist.append(item)
            added.append(att.filename)
        except Exception as e:
            logger.error(f"File save error {att.filename}: {e}")
            failed.append(att.filename)

    if not added:
        return await interaction.followup.send(
            embed=Embed(
                description=get_messages("player.play_files.error.no_valid_files", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )

    desc = get_messages(
        "player.play_files.success.description",
        gid,
        count=len(added),
        file_list="\n".join(f"• {n}" for n in added[:10]),
    )
    if len(added) > 10:
        desc += f"\n... and {len(added)-10} more."
    if failed:
        desc += get_messages(
            "player.play_files.success.footer_failed", gid, count=len(failed)
        )
    await interaction.followup.send(
        embed=Embed(
            title=get_messages("player.play_files.success.title", gid),
            description=desc,
            color=0xB5EAD7 if is_kw else discord.Color.blue(),
        ),
        silent=SILENT_MESSAGES,
    )
    if not (vc.is_playing() or vc.is_paused()):
        mp.current_task = asyncio.create_task(play_audio(gid))


@bot.tree.command(name="queue", description="Show the current song queue.")
async def queue_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            get_messages("command.error.guild_only", 0), ephemeral=True
        )
    await interaction.response.defer()
    gid = interaction.guild.id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    is_247n = state._24_7_mode and not mp.autoplay_enabled
    if is_247n and mp.radio_playlist:
        cur_url = mp.current_info.get("url") if mp.current_info else None
        try:
            ci = [t.get("url") for t in mp.radio_playlist].index(cur_url)
            tracks = mp.radio_playlist[ci + 1 :] + mp.radio_playlist[: ci + 1]
        except (ValueError, IndexError):
            tracks = mp.radio_playlist
    else:
        tracks = list(mp.queue._queue)

    if not tracks and not mp.current_info:
        return await interaction.followup.send(
            embed=Embed(
                description=get_messages("queue_empty", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )

    view = QueueView(interaction, tracks)
    msg = await interaction.followup.send(
        embed=await view._build_embed(), view=view, silent=SILENT_MESSAGES
    )
    view.message = msg


@bot.tree.command(name="clearqueue", description="Clear the current queue")
async def clear_queue(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            get_messages("command.error.guild_only", 0), ephemeral=True
        )
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp.queue = asyncio.Queue(maxsize=5000)
    mp.history.clear()
    mp.radio_playlist.clear()
    bot.loop.create_task(update_controller(bot, gid))
    await interaction.response.send_message(
        embed=Embed(
            description=get_messages("clear_queue_success", gid),
            color=0xB5EAD7 if is_kw else discord.Color.green(),
        ),
        silent=SILENT_MESSAGES,
    )


@bot.tree.command(
    name="skip", description="Skip current song or jump to a specific track number."
)
@app_commands.describe(number="[Optional] Track number to jump to.")
async def skip(
    interaction: discord.Interaction,
    number: Optional[app_commands.Range[int, 1]] = None,
):
    if not interaction.guild:
        return await interaction.response.send_message(
            get_messages("command.error.guild_only", 0), ephemeral=True
        )
    gid = interaction.guild_id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player
    vc = interaction.guild.voice_client

    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("no_song", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )

    await interaction.response.defer()

    if mp.lyrics_task and not mp.lyrics_task.done():
        mp.lyrics_task.cancel()

    if number is not None:
        async with mp.queue_lock:
            qs = mp.queue.qsize()
            if not 1 <= number <= qs:
                return await interaction.followup.send(
                    get_messages(
                        "player.skip.error.invalid_number", gid, queue_size=qs
                    ),
                    ephemeral=True,
                    silent=True,
                )
            q = list(mp.queue._queue)
            idx = number - 1
            mp.history.extend(q[:idx])
            nq = asyncio.Queue(maxsize=5000)  # ← Maintain maxsize limit
            for item in q[idx:]:
                await nq.put(item)
            mp.queue = nq
        title = get_track_display_info(q[idx]).get("title", "?")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages(
                    "player.skip.success.jumped", gid, number=number, title=title
                ),
                color=0xB5EAD7 if is_kw else discord.Color.green(),
            ),
            silent=SILENT_MESSAGES,
        )
        mp.manual_stop = True
        await safe_stop(vc)
        return

    mp.manual_stop = True
    await safe_stop(vc)
    embed = Embed(
        title=get_messages("skip_confirmation", gid),
        color=0xE2F0CB if is_kw else discord.Color.blue(),
    )
    q_snap = list(mp.queue._queue)
    if q_snap:
        ni = get_track_display_info(q_snap[0])
        nt = ni.get("title", "?")
        embed.description = f"▶️ [{nt}]({ni.get('webpage_url','#')})"
    await interaction.followup.send(embed=embed, silent=SILENT_MESSAGES)


@bot.tree.command(name="loop", description="Enable/disable looping")
async def loop_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    await interaction.response.defer()
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp.loop_current = not mp.loop_current
    st = get_messages(
        "loop_state_enabled" if mp.loop_current else "loop_state_disabled", gid
    )
    await interaction.followup.send(
        embed=Embed(
            description=get_messages("loop", gid, state=st),
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        ),
        silent=SILENT_MESSAGES,
    )
    bot.loop.create_task(update_controller(bot, gid))


@bot.tree.command(name="stop", description="Stop playback and disconnect")
async def stop_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    if mp.lyrics_task and not mp.lyrics_task.done():
        mp.lyrics_task.cancel()

    if mp.voice_client and mp.voice_client.is_connected():
        await safe_stop(mp.voice_client)
        if mp.current_task and not mp.current_task.done():
            mp.current_task.cancel()
        await mp.voice_client.disconnect()
        clear_audio_cache(gid)
        get_guild_state(gid).music_player = MusicPlayer()
        bot.loop.create_task(update_controller(bot, gid))
        await interaction.response.send_message(
            embed=Embed(
                description=get_messages("stop", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            silent=SILENT_MESSAGES,
        )
    else:
        await interaction.response.send_message(
            embed=Embed(
                description=get_messages("not_connected", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )


@bot.tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    if not interaction.guild:
        return
    await interaction.response.defer()
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    vc = await ensure_voice_connection(interaction)
    if vc and vc.is_playing():
        if mp.playback_started_at:
            mp.start_time += (time.time() - mp.playback_started_at) * mp.playback_speed
            mp.playback_started_at = None
        vc.pause()
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("pause", gid),
                color=0xFFB7B2 if is_kw else discord.Color.orange(),
            ),
            silent=SILENT_MESSAGES,
        )
        bot.loop.create_task(update_controller(bot, gid))
    else:
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("no_playback", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )


@bot.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    if not interaction.guild:
        return
    await interaction.response.defer()
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    vc = await ensure_voice_connection(interaction)
    if vc and vc.is_paused():
        if mp.playback_started_at is None:
            mp.playback_started_at = time.time()
        vc.resume()
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("resume", gid),
                color=0xB5EAD7 if is_kw else discord.Color.green(),
            ),
            silent=SILENT_MESSAGES,
        )
        bot.loop.create_task(update_controller(bot, gid))
    else:
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("no_paused", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )


@bot.tree.command(name="shuffle", description="Shuffle the queue")
async def shuffle_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    if mp.queue.empty():
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("queue_empty", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
    items = list(mp.queue._queue)
    random.shuffle(items)
    q = asyncio.Queue(maxsize=5000)
    for i in items:
        await q.put(i)
    mp.queue = q
    await interaction.response.send_message(
        embed=Embed(
            description=get_messages("shuffle_success", gid),
            color=0xB5EAD7 if is_kw else discord.Color.green(),
        ),
        silent=SILENT_MESSAGES,
    )
    bot.loop.create_task(update_controller(bot, gid))


@bot.tree.command(name="nowplaying", description="Show currently playing song")
async def now_playing(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    if not mp.current_info:
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("no_song_playing", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
    t = mp.current_info.get("title", "Unknown")
    url = mp.current_info.get("webpage_url", mp.current_url)
    desc = (
        get_messages("queue.now_playing_format.file", gid, title=t)
        if mp.current_info.get("source_type") == "file"
        else get_messages("now_playing_description", gid, title=t, url=url)
    )
    embed = Embed(
        title=get_messages("now_playing_title", gid),
        description=desc,
        color=0xC7CEEA if is_kw else discord.Color.green(),
    )
    if mp.current_info.get("thumbnail"):
        embed.set_thumbnail(url=mp.current_info["thumbnail"])
    await interaction.response.send_message(embed=embed, silent=SILENT_MESSAGES)


@bot.tree.command(name="autoplay", description="Enable/disable autoplay")
async def toggle_autoplay(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp.autoplay_enabled = not mp.autoplay_enabled
    st = get_messages(
        "autoplay_state_enabled" if mp.autoplay_enabled else "autoplay_state_disabled",
        gid,
    )
    await interaction.response.send_message(
        embed=Embed(
            description=get_messages("autoplay_toggle", gid, state=st),
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        ),
        silent=SILENT_MESSAGES,
    )
    bot.loop.create_task(update_controller(bot, gid))


@bot.tree.command(name="volume", description="Set music volume (0-200%)")
@app_commands.describe(level="Volume percentage")
@app_commands.default_permissions(manage_channels=True)
async def volume(
    interaction: discord.Interaction, level: app_commands.Range[int, 0, 200]
):
    if not interaction.guild:
        return
    gid = interaction.guild.id
    mp = get_player(gid)
    vc = interaction.guild.voice_client
    mp.volume = level / 100.0
    if vc and vc.is_playing() and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = mp.volume
    await interaction.response.send_message(
        embed=Embed(
            description=get_messages("volume_success", gid, level=level),
            color=0xB5EAD7 if get_mode(gid) else discord.Color.blue(),
        ),
        silent=SILENT_MESSAGES,
    )
    bot.loop.create_task(update_controller(bot, gid))


@bot.tree.command(name="filter", description="Apply/remove audio filters in real time.")
async def filter_command(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild.id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    if not mp.voice_client or not (
        mp.voice_client.is_playing() or mp.voice_client.is_paused()
    ):
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("filter.no_playback", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
    view = FilterView(interaction)
    embed = Embed(
        title=get_messages("filter.title", gid),
        description=get_messages("filter.description", gid),
        color=0xB5EAD7 if is_kw else discord.Color.blue(),
    )
    await interaction.response.send_message(
        embed=embed, view=view, silent=SILENT_MESSAGES
    )


@bot.tree.command(name="seek", description="Seek/rewind/fast-forward the current song.")
async def seek_cmd(interaction: discord.Interaction):
    gid = interaction.guild.id
    mp = get_player(gid)
    if not mp.voice_client or not (
        mp.voice_client.is_playing() or mp.voice_client.is_paused()
    ):
        return await interaction.response.send_message(
            get_messages("no_playback", gid), ephemeral=True, silent=True
        )
    if mp.is_current_live:
        return await interaction.response.send_message(
            get_messages("seek.fail_live", gid), ephemeral=True, silent=True
        )
    view = SeekView(interaction)
    await interaction.response.send_message(
        embed=Embed(
            title=get_messages("seek_interface_title", gid),
            description=get_messages("seek.interface.loading_description", gid),
            color=0xB5EAD7 if get_mode(gid) else discord.Color.blue(),
        ),
        view=view,
        silent=SILENT_MESSAGES,
    )
    view.message = await interaction.original_response()
    await view.update_embed()
    await view.start_update_task()


@bot.tree.command(
    name="remove", description="Remove songs from the queue interactively."
)
async def remove_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    if mp.queue.empty():
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("queue_empty", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
    await interaction.response.defer()
    view = RemoveView(interaction, list(mp.queue._queue))
    await view.update_view()
    await interaction.followup.send(
        embed=Embed(
            title=get_messages("remove_title", gid),
            description=get_messages("remove_description", gid),
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        ),
        view=view,
        silent=SILENT_MESSAGES,
    )


@bot.tree.command(
    name="search", description="Search for a song and choose from results."
)
@app_commands.describe(query="Song name to search for")
async def search_cmd(interaction: discord.Interaction, query: str):
    if not interaction.guild:
        return
    await interaction.response.defer()
    gid = interaction.guild_id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    vc = await ensure_voice_connection(interaction)
    if not vc:
        return
    try:
        prefix = "scsearch5:" if IS_PUBLIC_VERSION else "ytsearch5:"
        info = await fetch_video_info_with_retry(
            f"ytsearch5:{sanitize_query(query)}",
            {"extract_flat": True, "noplaylist": True},
        )
        results = info.get("entries", [])
        if not results:
            return await interaction.followup.send(
                embed=Embed(
                    description=get_messages("search_no_results", gid).format(
                        query=query
                    ),
                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                ),
                ephemeral=True,
                silent=True,
            )
        view = SearchView(results, gid)
        await interaction.followup.send(
            embed=Embed(
                title=get_messages("search_results_title", gid),
                description=get_messages("search_results_description", gid),
                color=0xC7CEEA if is_kw else discord.Color.blue(),
            ),
            view=view,
            silent=SILENT_MESSAGES,
        )
    except Exception as e:
        logger.error(f"/search error: {e}")
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("search_error", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )


@bot.tree.command(name="jumpto", description="Jump to a specific song in the queue.")
async def jumpto(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII
    if mp.queue.empty():
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("queue_empty", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )
    await interaction.response.defer()
    view = JumpToView(interaction, list(mp.queue._queue))
    await view.update_view()
    await interaction.followup.send(
        embed=Embed(
            title=get_messages("jumpto.title", gid),
            description=get_messages("jumpto.description", gid),
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        ),
        view=view,
        silent=SILENT_MESSAGES,
    )


@bot.tree.command(name="previous", description="Play the previous song.")
async def previous(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild.id
    mp = get_player(gid)
    vc = interaction.guild.voice_client
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(
            get_messages("player.no_playback.title", gid), ephemeral=True, silent=True
        )
    if len(mp.history) < 2:
        return await interaction.response.send_message(
            get_messages("player.history.empty", gid), ephemeral=True, silent=True
        )
    await interaction.response.defer(ephemeral=True)

    async with mp.queue_lock:
        cur, prev_item = mp.history.pop(), mp.history.pop()
        nq = asyncio.Queue(maxsize=5000)
        for item in [prev_item, cur] + list(mp.queue._queue):
            await nq.put(item)
        mp.queue = nq

    mp.manual_stop = True
    await safe_stop(vc)
    await interaction.followup.send(
        get_messages("player.previous.success", gid), silent=True
    )


@bot.tree.command(name="lyrics", description="Get song lyrics from Genius.")
async def lyrics_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    mp = get_player(gid)
    if not mp.voice_client or not mp.voice_client.is_playing() or not mp.current_info:
        return await interaction.response.send_message(
            get_messages("player.no_song.title", gid), ephemeral=True, silent=True
        )
    await interaction.response.defer()
    await fetch_and_display_genius_lyrics(interaction)


@bot.tree.command(name="karaoke", description="Start synced karaoke lyrics.")
async def karaoke_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    mp = state.music_player
    is_kw = state.locale == Locale.EN_X_KAWAII

    if not mp.voice_client or not mp.voice_client.is_playing() or not mp.current_info:
        return await interaction.response.send_message(
            get_messages("player.no_playback.title", gid), ephemeral=True, silent=True
        )
    if mp.lyrics_task and not mp.lyrics_task.done():
        return await interaction.response.send_message(
            get_messages("karaoke.error.already_running", gid),
            ephemeral=True,
            silent=True,
        )

    async def proceed():
        if not interaction.response.is_done():
            await interaction.response.defer()
        clean, artist = get_cleaned_song_info(mp.current_info, gid)
        loop = asyncio.get_running_loop()
        lrc = None
        for q in [f"{clean} {artist}", clean]:
            try:
                lrc = await asyncio.wait_for(
                    loop.run_in_executor(None, syncedlyrics.search, q), timeout=7.0
                )
                if lrc:
                    break
            except Exception:
                pass

        lines = _parse_lrc(lrc)
        if not lines:
            embed = Embed(
                title=get_messages("karaoke.not_found_title", gid),
                description=get_messages(
                    "karaoke.not_found_description", gid, query=f"{clean} {artist}"
                ),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            )
            view = KaraokeRetryView(interaction, clean, gid)
            return await interaction.followup.send(
                embed=embed, view=view, silent=SILENT_MESSAGES
            )

        mp.synced_lyrics = lines
        embed = Embed(
            title=get_messages("karaoke.embed.title", gid, title=clean),
            description=get_messages("karaoke.embed.description", gid),
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        )
        mp.lyrics_message = await interaction.followup.send(
            embed=embed, wait=True, silent=SILENT_MESSAGES
        )
        mp.lyrics_task = asyncio.create_task(update_karaoke_task(gid))

    if state.karaoke_disclaimer_shown:
        await proceed()
    else:
        warn = Embed(
            title=get_messages("karaoke.warning.title", gid),
            description=get_messages("karaoke.warning.description", gid),
            color=0xFFB6C1 if is_kw else discord.Color.orange(),
        )
        view = KaraokeWarningView(interaction, karaoke_coro=proceed)
        await interaction.response.send_message(
            embed=warn, view=view, silent=SILENT_MESSAGES
        )


@bot.tree.command(name="playnext", description="Add a song to play next")
@app_commands.describe(query="Link or title", file="Audio/video file")
async def play_next(
    interaction: discord.Interaction, query: str = None, file: discord.Attachment = None
):
    if not interaction.guild:
        return
    gid = interaction.guild.id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player

    if (query and file) or (not query and not file):
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("player.play_next.error.invalid_args", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )

    await interaction.response.defer()

    vc = await ensure_voice_connection(interaction)
    if not vc:
        return

    item = None
    if query:
        try:
            sq = (
                query
                if (
                    YOUTUBE_REGEX.match(query)
                    or SOUNDCLOUD_REGEX.match(query)
                    or DIRECT_LINK_REGEX.match(query)
                )
                else f"ytsearch:{sanitize_query(query)}"
            )
            info = await fetch_video_info_with_retry(sq, {"noplaylist": True})
            if "entries" in info:
                info = info["entries"][0]
            item = {
                "url": info.get("webpage_url", info.get("url")),
                "title": info.get("title", "Unknown"),
                "webpage_url": info.get("webpage_url", info.get("url")),
                "thumbnail": info.get("thumbnail"),
                "is_single": True,
                "requester": interaction.user,
            }
        except Exception as e:
            logger.error(f"/playnext error: {e}")
            return await interaction.followup.send(
                embed=Embed(
                    description=get_messages("search_error", gid),
                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                ),
                ephemeral=True,
                silent=True,
            )
    elif file:
        if not file.content_type or not (
            file.content_type.startswith("audio/")
            or file.content_type.startswith("video/")
        ):
            return await interaction.followup.send(
                embed=Embed(
                    description=get_messages(
                        "player.play_files.error.invalid_type", gid
                    ),
                    color=0xFF9AA2 if is_kw else discord.Color.red(),
                ),
                ephemeral=True,
                silent=True,
            )
        fp = os.path.join("audio_cache", str(gid), file.filename)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        await file.save(fp)
        item = {
            "url": fp,
            "title": file.filename,
            "webpage_url": None,
            "thumbnail": None,
            "is_single": True,
            "source_type": "file",
            "duration": get_file_duration(fp),
            "requester": interaction.user,
        }

    if item:
        async with mp.queue_lock:
            nq = asyncio.Queue(maxsize=5000)
            await nq.put(item)
            while not mp.queue.empty():
                await nq.put(await mp.queue.get())
            mp.queue = nq
        desc = (
            get_messages("queue.now_playing_format.file", gid, title=item["title"])
            if item.get("source_type") == "file"
            else f"[{item['title']}]({item['webpage_url']})"
        )
        embed = Embed(
            title=get_messages("play_next_added", gid),
            description=desc,
            color=0xC7CEEA if is_kw else discord.Color.blue(),
        )
        if item.get("thumbnail"):
            embed.set_thumbnail(url=item["thumbnail"])
        await interaction.followup.send(embed=embed, silent=SILENT_MESSAGES)
        bot.loop.create_task(update_controller(bot, gid))
        if not (vc.is_playing() or vc.is_paused()):
            mp.current_task = asyncio.create_task(play_audio(gid))


@bot.tree.command(
    name="reconnect", description="Refresh voice connection without losing the queue."
)
async def reconnect_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player

    vc = await ensure_voice_connection(interaction)
    if not vc:
        return
    if not mp.current_info:
        return await interaction.response.send_message(
            embed=Embed(
                description=get_messages("reconnect_not_playing", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            ephemeral=True,
            silent=True,
        )

    if not interaction.response.is_done():
        await interaction.response.defer()

    ts = mp.start_time
    if mp.playback_started_at:
        ts += (time.time() - mp.playback_started_at) * mp.playback_speed

    ch = vc.channel
    try:
        mp.is_reconnecting = True
        await safe_stop(vc)
        await vc.disconnect(force=True)
        await asyncio.sleep(0.75)
        new_vc = await ch.connect()
        mp.voice_client = new_vc
        mp.current_task = bot.loop.create_task(
            play_audio(gid, seek_time=ts, is_a_loop=True)
        )
        await interaction.followup.send(
            embed=Embed(
                description=get_messages("reconnect_success", gid),
                color=0xB5EAD7 if is_kw else discord.Color.green(),
            ),
            silent=SILENT_MESSAGES,
        )
    except Exception as e:
        logger.error(f"Reconnect error: {e}")
        await interaction.followup.send(
            get_messages("player.reconnect.error.generic", gid),
            ephemeral=True,
            silent=True,
        )
    finally:
        mp.is_reconnecting = False


@bot.tree.command(name="kaomoji", description="Enable/disable kawaii mode")
@app_commands.default_permissions(administrator=True)
async def toggle_kawaii(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    state.locale = (
        Locale.EN_US if state.locale == Locale.EN_X_KAWAII else Locale.EN_X_KAWAII
    )
    is_kw = state.locale == Locale.EN_X_KAWAII
    st = get_messages("kawaii_state_enabled" if is_kw else "kawaii_state_disabled", gid)
    await interaction.response.send_message(
        embed=Embed(
            description=get_messages("kawaii_toggle", gid).format(state=st),
            color=0xFFB6C1 if is_kw else discord.Color.blue(),
        ),
        ephemeral=True,
        silent=True,
    )


@bot.tree.command(name="24_7", description="Enable/disable 24/7 mode.")
@app_commands.choices(
    mode=[
        Choice(name="Normal (Loops the current queue)", value="normal"),
        Choice(name="Auto (Adds similar songs when queue is empty)", value="auto"),
        Choice(name="Off (Disable 24/7 mode)", value="off"),
    ]
)
async def radio_24_7(interaction: discord.Interaction, mode: str):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    state = get_guild_state(gid)
    is_kw = state.locale == Locale.EN_X_KAWAII
    mp = state.music_player
    await interaction.response.defer(thinking=True)

    if mode == "off":
        if not state._24_7_mode:
            return await interaction.followup.send(
                get_messages("24_7.not_active", gid), ephemeral=True, silent=True
            )
        state._24_7_mode = False
        mp.autoplay_enabled = False
        mp.loop_current = False
        mp.radio_playlist.clear()
        return await interaction.followup.send(
            embed=Embed(
                title=get_messages("24_7.off_title", gid),
                description=get_messages("24_7.off_desc", gid),
                color=0xFF9AA2 if is_kw else discord.Color.red(),
            ),
            silent=SILENT_MESSAGES,
        )

    vc = await ensure_voice_connection(interaction)
    if not vc:
        return

    if not mp.radio_playlist:
        if mp.current_info:
            mp.radio_playlist.append(
                {
                    "url": mp.current_url,
                    "title": mp.current_info.get("title", ""),
                    "webpage_url": mp.current_info.get("webpage_url", mp.current_url),
                    "is_single": False,
                    "source_type": mp.current_info.get("source_type"),
                }
            )
        mp.radio_playlist.extend(list(mp.queue._queue))

    if not mp.radio_playlist and mode == "normal":
        return await interaction.followup.send(
            get_messages("24_7.error.empty_queue_normal", gid),
            ephemeral=True,
            silent=True,
        )

    state._24_7_mode = True
    mp.loop_current = False
    mp.autoplay_enabled = mode == "auto"

    key = "auto" if mode == "auto" else "normal"
    await interaction.followup.send(
        embed=Embed(
            title=get_messages(f"24_7.{key}_title", gid),
            description=get_messages(f"24_7.{key}_desc", gid),
            color=0xB5EAD7 if is_kw else discord.Color.green(),
        ),
        silent=SILENT_MESSAGES,
    )
    if not (vc.is_playing() or vc.is_paused()):
        mp.current_task = asyncio.create_task(play_audio(gid))


@bot.tree.command(name="status", description="Display bot performance stats.")
async def status_cmd(interaction: discord.Interaction):
    def fmt_bytes(size):
        if not size:
            return "0B"
        names = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size, 1024)))
        return f"{round(size/math.pow(1024,i),2)} {names[min(i,4)]}"

    await interaction.response.defer(ephemeral=True)
    gid = interaction.guild_id
    proc = psutil.Process()
    lat = round(bot.latency * 1000)
    up = str(datetime.timedelta(seconds=int(time.time() - bot.start_time)))
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    embed = discord.Embed(
        title=get_messages("status.title", gid),
        description=get_messages("status.description", gid),
        color=0x2ECC71 if lat < 200 else (0xE67E22 if lat < 500 else 0xE74C3C),
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.add_field(
        name=get_messages("status.bot.title", gid),
        value=get_messages(
            "status.bot.value",
            gid,
            latency=lat,
            server_count=len(bot.guilds),
            user_count=sum(g.member_count for g in bot.guilds),
            uptime_string=up,
        ),
        inline=True,
    )
    embed.add_field(
        name=get_messages("status.music_player.title", gid),
        value=get_messages(
            "status.music_player.value",
            gid,
            active_players=len(guild_states),
            total_queued_songs=sum(
                s.music_player.queue.qsize() for s in guild_states.values()
            ),
            ffmpeg_processes=len(
                [
                    c
                    for c in proc.children(recursive=True)
                    if "ffmpeg" in c.name().lower()
                ]
            ),
            url_cache_size=url_cache.currsize,
            url_cache_max=url_cache.maxsize,
        ),
        inline=True,
    )
    embed.add_field(
        name=get_messages("status.host.title", gid),
        value=get_messages(
            "status.host.value",
            gid,
            os_info=f"{platform.system()} {platform.release()}",
            cpu_load=cpu,
            cpu_freq_current=psutil.cpu_freq().current,
            ram_used=fmt_bytes(ram.used),
            ram_total=fmt_bytes(ram.total),
            ram_percent=ram.percent,
            disk_used=fmt_bytes(disk.used),
            disk_total=fmt_bytes(disk.total),
            disk_percent=disk.percent,
        ),
        inline=True,
    )
    embed.add_field(
        name=get_messages("status.environment.title", gid),
        value=get_messages(
            "status.environment.value",
            gid,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            discord_py_version=discord.__version__,
            yt_dlp_version=yt_dlp.version.__version__,
            bot_ram_usage=fmt_bytes(proc.memory_info().rss),
        ),
        inline=True,
    )
    embed.set_footer(
        text=get_messages(
            "status.footer", gid, user_display_name=interaction.user.display_name
        )
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    await interaction.followup.send(embed=embed, silent=True)


@bot.tree.command(name="discord", description="Get an invite to the support server.")
async def discord_cmd(interaction: discord.Interaction):
    gid = interaction.guild_id
    is_kw = get_mode(gid)
    view = View()
    view.add_item(
        Button(
            label=get_messages("discord_command_button", gid),
            style=discord.ButtonStyle.link,
            url="https://discord.gg/JeH8g6g3cG",
        )
    )
    await interaction.response.send_message(
        embed=Embed(
            title=get_messages("discord_command_title", gid),
            description=get_messages("discord_command_description", gid),
            color=0xFFB6C1 if is_kw else discord.Color.blue(),
        ),
        view=view,
        silent=SILENT_MESSAGES,
    )


@bot.tree.command(name="support", description="Show ways to support Playify.")
async def support_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    gid = interaction.guild_id
    is_kw = get_mode(gid)
    embed = Embed(
        title=get_messages("support_title", gid),
        description=get_messages("support_description", gid),
        color=0xFFC300 if not is_kw else 0xFFB6C1,
    )
    embed.add_field(
        name=get_messages("support_patreon_title", gid),
        value=get_messages(
            "support.patreon_value", gid, link="https://patreon.com/Playify"
        ),
        inline=True,
    )
    embed.add_field(
        name=get_messages("support_paypal_title", gid),
        value=get_messages(
            "support.paypal_value",
            gid,
            link="https://www.paypal.com/paypalme/alanmussot1",
        ),
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name=get_messages("support_discord_title", gid),
        value=get_messages(
            "support.discord_value", gid, link="https://discord.gg/JeH8g6g3cG"
        ),
        inline=True,
    )
    embed.add_field(
        name=get_messages("support_contact_title", gid),
        value=get_messages("support.contact_value", gid, username="@alananasssss"),
        inline=True,
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text=get_messages("support.footer", gid))
    await interaction.response.send_message(embed=embed, silent=SILENT_MESSAGES)


# Setup commands group
@app_commands.default_permissions(administrator=True)
class SetupCommands(app_commands.Group):
    def __init__(self, bot_ref):
        super().__init__(
            name="setup",
            description="Set up bot features.",
            default_permissions=discord.Permissions(administrator=True),
        )
        self.bot_ref = bot_ref

    @app_commands.command(
        name="controller",
        description="Set a channel for the persistent music controller.",
    )
    @app_commands.describe(channel="Text channel (defaults to current)")
    async def controller(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            return
        target = channel or interaction.channel
        gid = interaction.guild.id
        state = get_guild_state(gid)

        # Delete old controller message
        if state.controller_message_id:
            try:
                old_ch = self.bot_ref.get_channel(state.controller_channel_id)
                if old_ch:
                    await (
                        await old_ch.fetch_message(state.controller_message_id)
                    ).delete()
            except Exception:
                pass

        state.controller_channel_id = target.id
        state.controller_message_id = None
        await interaction.response.send_message(
            get_messages(
                "setup.controller.success", gid, channel_mention=target.mention
            ),
            ephemeral=True,
            silent=True,
        )
        await update_controller(self.bot_ref, gid)

    @app_commands.command(
        name="allowlist", description="Restrict bot commands to specific channels."
    )
    @app_commands.describe(
        reset="Type 'default' to allow all channels",
        channel1="First allowed channel",
        channel2="Optional",
        channel3="Optional",
        channel4="Optional",
        channel5="Optional",
    )
    async def allowlist(
        self,
        interaction: discord.Interaction,
        reset: Optional[str] = None,
        channel1: Optional[discord.TextChannel] = None,
        channel2: Optional[discord.TextChannel] = None,
        channel3: Optional[discord.TextChannel] = None,
        channel4: Optional[discord.TextChannel] = None,
        channel5: Optional[discord.TextChannel] = None,
    ):
        gid = interaction.guild.id
        state = get_guild_state(gid)
        is_kw = state.locale == Locale.EN_X_KAWAII

        if reset and reset.lower() == "default":
            state.allowed_channels.clear()
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=get_messages("allowlist_reset_success", gid),
                    color=0xB5EAD7 if is_kw else discord.Color.green(),
                ),
                ephemeral=True,
                silent=True,
            )

        channels = [c for c in [channel1, channel2, channel3, channel4, channel5] if c]
        if channels:
            state.allowed_channels = {c.id for c in channels}
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=get_messages("allowlist_set_success", gid).format(
                        channels=", ".join(c.mention for c in channels)
                    ),
                    color=0xB5EAD7 if is_kw else discord.Color.green(),
                ),
                ephemeral=True,
                silent=True,
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                description=get_messages("allowlist_invalid_args", gid),
                color=0xFF9AA2 if is_kw else discord.Color.orange(),
            ),
            ephemeral=True,
            silent=True,
        )


@bot.tree.command(
    name="clear-database", description="[ADMIN] Clear all saved bot data."
)
@app_commands.default_permissions(administrator=True)
async def clear_database(interaction: discord.Interaction):
    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30.0)
            self.value = None

        @discord.ui.button(label="Confirm Clear", style=discord.ButtonStyle.danger)
        async def confirm(self, i: discord.Interaction, b):
            self.value = True
            await i.response.defer()  # ← WAJIB agar tidak "Interaction Failed"
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, i: discord.Interaction, b):
            self.value = False
            await i.response.defer()  # ← WAJIB
            self.stop()

    embed = discord.Embed(
        title="⚠️ Database Clear Confirmation",
        description="This will **permanently delete** all saved data.\n**This cannot be undone!**",
        color=discord.Color.red(),
    )
    view = ConfirmView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    await view.wait()

    if view.value:
        try:
            with db_connection() as conn:
                conn.execute("DELETE FROM guild_settings")
                conn.execute("DELETE FROM allowlist")
                conn.execute("DELETE FROM playback_state")
            result_embed = discord.Embed(
                title="✅ Database Cleared", color=discord.Color.green()
            )
        except Exception as e:
            result_embed = discord.Embed(
                title="❌ Error", description=str(e), color=discord.Color.red()
            )
    else:
        result_embed = discord.Embed(title="Cancelled", color=discord.Color.orange())
    await interaction.edit_original_response(embed=result_embed, view=None)


@bot.tree.command(
    name="profile", description="Tampilkan statistik musik kamu atau member lain."
)
@app_commands.describe(member="Member yang ingin dilihat profilnya (default: kamu)")
async def profile_cmd(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
):
    # Defer immediately to prevent timeout
    await interaction.response.defer()

    if not interaction.guild:
        return await interaction.followup.send(
            "Command ini hanya bisa digunakan di server.", ephemeral=True
        )

    target = member or interaction.guild.get_member(interaction.user.id)
    if not target:
        return await interaction.followup.send(
            "Member tidak ditemukan.", ephemeral=True
        )

    try:
        await build_and_send_profile(interaction, target)
    except Exception as e:
        import traceback

        traceback.print_exc()
        await interaction.followup.send(
            f"Gagal generate profile card: {e}", ephemeral=True
        )


# ==============================================================================
# 18. EVENTS
# ==============================================================================


async def global_interaction_check(interaction: discord.Interaction) -> bool:
    if interaction.type in (
        discord.InteractionType.autocomplete,
        discord.InteractionType.component,  # Tombol & select menu
    ):
        return True
    if not interaction.guild:
        return True
    gid = interaction.guild.id
    state = get_guild_state(gid)
    if not state.allowed_channels:
        return True
    if interaction.user.guild_permissions.manage_guild:
        return True
    if interaction.channel_id in state.allowed_channels:
        return True

    is_kw = state.locale == Locale.EN_X_KAWAII
    mentions = ", ".join(f"<#{i}>" for i in state.allowed_channels)
    embed = discord.Embed(
        title=get_messages("command_restricted_title", gid),
        description=get_messages("command_restricted_description", gid).format(
            bot_name=interaction.client.user.name
        ),
        color=0xFF9AA2 if is_kw else discord.Color.red(),
    )
    embed.add_field(
        name=get_messages("command_allowed_channels_field", gid), value=mentions
    )
    await interaction.response.send_message(embed=embed, ephemeral=True, silent=True)
    return False


@bot.event
async def on_ready():
    if not hasattr(bot, "start_time"):
        bot.start_time = time.time()
    logger.info(f"{bot.user.name} is online.")
    bot.tree.interaction_check = global_interaction_check

    for guild in bot.guilds:
        bot.add_view(MusicControllerView(bot, guild.id))

    synced = await bot.tree.sync()
    logger.info(f"Synced {len(synced)} slash commands.")

    async def rotate_presence():
        await bot.wait_until_ready()
        while not bot.is_closed():
            if bot.guilds:
                gid = bot.guilds[0].id
                statuses = [
                    (
                        get_messages("presence.listening_volume", gid),
                        discord.ActivityType.listening,
                    ),
                    (
                        get_messages("presence.listening_play", gid),
                        discord.ActivityType.listening,
                    ),
                    (
                        get_messages(
                            "presence.playing_servers", gid, count=len(bot.guilds)
                        ),
                        discord.ActivityType.playing,
                    ),
                ]
                for txt, atype in statuses:
                    try:
                        await bot.change_presence(
                            activity=discord.Activity(name=txt, type=atype)
                        )
                    except Exception as e:
                        logger.error(f"Presence error: {e}")
                    await asyncio.sleep(10)
            else:
                await asyncio.sleep(30)

    bot.loop.create_task(rotate_presence())
    await setup_profile(bot)
    await load_states_on_startup()


@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    vc = guild.voice_client
    if not vc or not vc.channel:
        return

    gid = guild.id
    state = get_guild_state(gid)
    mp = state.music_player

    # Bot disconnected
    if member.id == bot.user.id and after.channel is None:
        if mp.is_reconnecting or mp.is_cleaning:
            return
        if mp.silence_task and not mp.silence_task.done():
            mp.silence_task.cancel()

        if state._24_7_mode:
            last_ch = before.channel
            if not last_ch:
                return
            ts = mp.start_time
            if mp.playback_started_at:
                ts += (time.time() - mp.playback_started_at) * mp.playback_speed
            if mp.current_task and not mp.current_task.done():
                mp.current_task.cancel()

            async def reconnect_247():
                try:
                    await asyncio.sleep(2)
                    new_vc = await last_ch.connect()
                    mp.voice_client = new_vc
                    if mp.current_info:
                        mp.current_task = bot.loop.create_task(
                            play_audio(gid, seek_time=ts, is_a_loop=True)
                        )
                except Exception as e:
                    logger.error(f"24/7 auto-reconnect failed: {e}")
                    mp.voice_client = None

            bot.loop.create_task(reconnect_247())
            return

        clear_audio_cache(gid)
        if mp.current_task and not mp.current_task.done():
            mp.current_task.cancel()
        state.music_player = MusicPlayer()
        state.server_filters = set()
        state._24_7_mode = False
        return

    bot_ch = vc.channel
    humans_in_channel = [m for m in bot_ch.members if not m.bot]

    # User left — bot now alone
    if not member.bot and before.channel == bot_ch and after.channel != bot_ch:
        if not humans_in_channel:
            if state._24_7_mode:
                # In 24/7 mode, keep music playing even when alone
                # Make sure silence loop is ready if music stops for any reason
                if not mp.silence_task or mp.silence_task.done():
                    mp.silence_task = bot.loop.create_task(play_silence_loop(gid))
            else:
                if vc.is_playing() and not mp.is_playing_silence:
                    mp.is_paused_by_leave = True
                    if mp.playback_started_at:
                        mp.start_time += (
                            time.time() - mp.playback_started_at
                        ) * mp.playback_speed
                        mp.playback_started_at = None
                    await safe_stop(vc)

                async def _leave_if_still_alone():
                    await asyncio.sleep(60)
                    if vc.is_connected() and not [
                        m for m in vc.channel.members if not m.bot
                    ]:
                        await vc.disconnect()

                bot.loop.create_task(_leave_if_still_alone())

    # First human rejoins
    if not member.bot and after.channel == bot_ch and before.channel != bot_ch:
        if len(humans_in_channel) == 1:
            if state._24_7_mode and vc.is_playing():
                # Music is already playing in 24/7 mode, no need to resume
                pass
            else:
                mp.is_paused_by_leave = False
                was_silence = mp.silence_task and not mp.silence_task.done()
                if mp.current_info:
                    if was_silence:
                        mp.silence_task.cancel()
                        # Give silence loop time to gracefully stop
                        await asyncio.sleep(0.3)
                        if vc.is_playing():
                            vc.stop()
                        await asyncio.sleep(0.2)
                    ts = mp.start_time
                    if mp.is_current_live:
                        mp.is_resuming_live = True
                        bot.loop.create_task(play_audio(gid, is_a_loop=True))
                    else:
                        bot.loop.create_task(play_audio(gid, seek_time=ts, is_a_loop=True))


# ==============================================================================
# 19. BOT RUN
# ==============================================================================
bot.tree.add_command(SetupCommands(bot))

if __name__ == "__main__":
    init_db()
    bot.start_time = time.time()
    bot.run(os.getenv("DISCORD_TOKEN"))
