import discord
from discord.ext import commands
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import aiohttp
import async_timeout
from collections import deque
import os
import sys
import logging
import time
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import discord.opus

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix='!', 
    intents=intents, 
    help_command=None,
    reconnect=True,
    max_messages=None
)

# Opus library loading
opus_path = os.path.join(os.path.dirname(__file__), "libopus.dll")
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus(opus_path)
        logger.info("Opus loaded successfully")
    except OSError as e:
        logger.error(f"Failed to load Opus: {e}")
        exit(1)

# Spotify API setup
try:
    spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    if spotify_client_id and spotify_client_secret:
        from spotipy.cache_handler import CacheHandler
        
        class NullCacheHandler(CacheHandler):
            def get_cached_token(self): return None
            def save_token_to_cache(self, token_info): pass
        
        spotify = spotipy.Spotify(
            client_credentials_manager=SpotifyClientCredentials(
                client_id=spotify_client_id,
                client_secret=spotify_client_secret,
                cache_handler=NullCacheHandler()
            )
        )
        logger.info("Spotify API initialized")
    else:
        spotify = None
        logger.warning("Spotify credentials not found")
except Exception as e:
    spotify = None
    logger.error(f"Failed to initialize Spotify: {e}")

# YouTube-DL configuration
ytdl_format_options = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'extractaudio': True,
    'audioformat': 'webm',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'socket_timeout': 30,
    'retries': 5,
    'fragment_retries': 5,
    'http_chunk_size': 10485760,
    'buffersize': 10485760,
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 '
        '-reconnect_at_eof 1 -timeout 30000000 -fflags +discardcorrupt '
        '-analyzeduration 2147483647 -probesize 2147483647'
    ),
    'options': '-vn -bufsize 2M -maxrate 128k -avoid_negative_ts make_zero'
}

try:
    ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
    logger.info("YouTube-DL initialized")
except Exception as e:
    logger.error(f"Failed to initialize YouTube-DL: {e}")
    ytdl = None

# Utility classes
class RetryConfig:
    def __init__(self, max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff

async def retry_async(func, config: RetryConfig = RetryConfig(), *args, **kwargs):
    last_exception = None
    delay = config.delay
    
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}/{config.max_attempts} failed: {str(e)}")
            
            if attempt < config.max_attempts - 1:
                await asyncio.sleep(delay)
                delay *= config.backoff
    
    logger.error(f"All retry attempts failed. Last error: {last_exception}")
    if last_exception:
        raise last_exception
    else:
        raise Exception("All retry attempts failed")

class EnhancedYTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.webpage_url = data.get('webpage_url')

    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream=True, retry_config=RetryConfig()):
        loop = loop or asyncio.get_event_loop()
        
        async def _extract_info():
            if not ytdl:
                raise Exception("YouTube-DL not initialized")
            
            try:
                async with async_timeout.timeout(60):
                    data = await loop.run_in_executor(
                        None, 
                        lambda: ytdl.extract_info(url, download=not stream)
                    )
            except asyncio.TimeoutError:
                raise Exception("Extraction timeout")
                
            if 'entries' in data:
                data = data['entries'][0]
            
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            
            return cls(
                discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                data=data
            )
        
        return await retry_async(_extract_info, retry_config)

class Song:
    def __init__(self, title: str, artist: str, duration: int, thumbnail: str, 
                 youtube_url: str, spotify_data: Optional[Dict] = None):
        self.title = title or "Unknown Title"
        self.artist = artist or "Unknown Artist"
        self.duration = duration
        self.thumbnail = thumbnail
        self.youtube_url = youtube_url
        self.spotify_data = spotify_data
        self.source = None
        self.retry_count = 0
        self.max_retries = 2

class EnhancedMusicQueue:
    def __init__(self):
        self.queue = deque()
        self.current: Optional[Song] = None
        self.is_playing = False
        self.voice_client = None
        self.last_activity = time.time()
        self.connection_failures = 0
        self.max_connection_failures = 3
        self.autoplay_enabled = False
        self.last_played_songs = deque(maxlen=5)
        self.autoplay_history = deque(maxlen=20)
        self.autoplay_failures = 0
        self.last_autoplay_attempt = 0
        self.max_autoplay_duration = 300

    def add_song(self, song: Song):
        self.queue.append(song)
        self.last_activity = time.time()

    def get_next_song(self) -> Optional[Song]:
        if self.queue:
            return self.queue.popleft()
        return None

    def clear_queue(self):
        self.queue.clear()
        self.last_activity = time.time()

    def is_inactive(self, timeout_minutes: int = 10) -> bool:
        return time.time() - self.last_activity > (timeout_minutes * 60)

    def reset_connection_failures(self):
        self.connection_failures = 0

    def increment_connection_failures(self):
        self.connection_failures += 1

    def should_give_up_connection(self) -> bool:
        return self.connection_failures >= self.max_connection_failures

# Global music queues
music_queues: Dict[int, EnhancedMusicQueue] = {}

def get_music_queue(guild_id: int) -> EnhancedMusicQueue:
    if guild_id not in music_queues:
        music_queues[guild_id] = EnhancedMusicQueue()
    return music_queues[guild_id]

# Utility functions
def format_duration(seconds: Optional[int]) -> str:
    if not seconds or seconds <= 0:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

def is_spotify_url(url: str) -> bool:
    return 'open.spotify.com' in url

def is_youtube_url(url: str) -> bool:
    return any(domain in url for domain in ['youtube.com', 'youtu.be', 'youtube-nocookie.com'])

# Search functions
async def search_spotify_track(query: str) -> Optional[Dict]:
    if not spotify:
        return None
        
    async def _spotify_search():
        try:
            async with async_timeout.timeout(15):
                if not spotify:
                    return None
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(
                    None, 
                    lambda: spotify.search(q=query, type='track', limit=1)
                )
                
                if results and 'tracks' in results and results['tracks']['items']:
                    track = results['tracks']['items'][0]
                    return {
                        'title': track['name'],
                        'artist': ', '.join([artist['name'] for artist in track['artists']]),
                        'duration': track['duration_ms'] // 1000,
                        'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else None,
                        'spotify_url': track['external_urls']['spotify']
                    }
        except Exception as e:
            logger.warning(f"Spotify search error: {e}")
        return None
    
    return await retry_async(_spotify_search, RetryConfig(max_attempts=2))

async def get_spotify_track_info(spotify_url: str) -> Optional[Dict]:
    if not spotify:
        return None
        
    async def _get_track_info():
        try:
            track_id = spotify_url.split('/')[-1].split('?')[0]
            async with async_timeout.timeout(15):
                if not spotify:
                    return None
                loop = asyncio.get_event_loop()
                track = await loop.run_in_executor(
                    None,
                    lambda: spotify.track(track_id)
                )
                
                return {
                    'title': track['name'],
                    'artist': ', '.join([artist['name'] for artist in track['artists']]),
                    'duration': track['duration_ms'] // 1000,
                    'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_url': track['external_urls']['spotify']
                }
        except Exception as e:
            logger.warning(f"Spotify track info error: {e}")
        return None
    
    return await retry_async(_get_track_info, RetryConfig(max_attempts=2))

async def search_youtube_for_song(title: str, artist: str) -> Optional[str]:
    if not ytdl:
        return None
    
    search_queries = [
        f"{title} {artist}",
        f"{title} {artist} official",
        f"{title} {artist} audio",
        title.split('(')[0].strip()
    ]
    
    for query in search_queries:
        try:
            clean_query = re.sub(r'[^\w\s-]', '', query).strip()
            if not clean_query:
                continue
                
            async with async_timeout.timeout(30):
                if not ytdl:
                    return None
                loop = asyncio.get_event_loop()
                search_results = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(f"ytsearch1:{clean_query}", download=False)
                )
                
                if search_results and 'entries' in search_results and search_results['entries']:
                    return search_results['entries'][0]['webpage_url']
                    
        except Exception as e:
            logger.warning(f"YouTube search failed for '{query}': {e}")
            continue
    
    return None

async def get_youtube_info(url: str) -> Optional[Dict]:
    if not ytdl:
        return None
        
    async def _get_info():
        try:
            async with async_timeout.timeout(45):
                if not ytdl:
                    return None
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(url, download=False)
                )
                
                if 'entries' in data:
                    data = data['entries'][0]
                    
                return {
                    'title': data.get('title'),
                    'duration': data.get('duration'),
                    'thumbnail': data.get('thumbnail'),
                    'url': data.get('webpage_url')
                }
        except Exception as e:
            logger.warning(f"YouTube info error: {e}")
        return None
    
    return await retry_async(_get_info, RetryConfig(max_attempts=2))

async def enhanced_youtube_search(query: str) -> Optional[str]:
    if not ytdl:
        return None
    
    try:
        async with async_timeout.timeout(15):
            loop = asyncio.get_event_loop()
            clean_query = re.sub(r'[^\w\s-]', '', query).strip()
            
            search_results = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch1:{clean_query}", download=False)
            )
            
            if search_results and 'entries' in search_results and search_results['entries']:
                return search_results['entries'][0]['webpage_url']
                
    except Exception as e:
        logger.warning(f"YouTube search failed: {e}")
    
    return None

async def enhanced_youtube_search_multiple(query: str, limit: int = 3) -> List[Dict]:
    if not ytdl:
        return []
    
    try:
        async with async_timeout.timeout(20):
            loop = asyncio.get_event_loop()
            clean_query = re.sub(r'[^\w\s-]', '', query).strip()
            
            search_results = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch{limit}:{clean_query}", download=False)
            )
            
            if search_results and 'entries' in search_results:
                return search_results['entries']
                
    except Exception as e:
        logger.warning(f"YouTube multiple search failed: {e}")
    
    return []

async def get_autoplay_recommendations(last_song: Song, music_queue: EnhancedMusicQueue, max_songs: int = 3, max_duration: int = 300) -> List[Song]:
    recommendations = []
    MAX_DURATION = max_duration
    
    try:
        # Spotify recommendations
        if spotify and last_song.spotify_data and len(recommendations) < max_songs:
            try:
                async with async_timeout.timeout(20):
                    loop = asyncio.get_event_loop()
                    spotify_url = last_song.spotify_data.get('spotify_url', '')
                    if spotify_url:
                        track_id = spotify_url.split('/')[-1].split('?')[0]
                        
                        if track_id and len(track_id) == 22:
                            try:
                                rec_data = await loop.run_in_executor(
                                    None,
                                    lambda: spotify.recommendations(seed_tracks=[track_id], limit=max_songs, market='ID')
                                )
                                
                                for track in rec_data.get('tracks', []):
                                    if len(recommendations) >= max_songs:
                                        break
                                    
                                    track_duration = track['duration_ms'] // 1000
                                    if track_duration > MAX_DURATION:
                                        continue
                                        
                                    track_title = track['name'].lower()
                                    track_artist = track['artists'][0]['name'].lower()
                                    is_duplicate = any(
                                        (track_title in h.title.lower() and track_artist in h.artist.lower())
                                        for h in music_queue.autoplay_history
                                    )
                                    
                                    if not is_duplicate:
                                        search_query = f"{track['name']} {track['artists'][0]['name']}"
                                        youtube_url = await enhanced_youtube_search(search_query)
                                        
                                        if youtube_url:
                                            song = Song(
                                                title=track['name'],
                                                artist=', '.join([artist['name'] for artist in track['artists']]),
                                                duration=track_duration,
                                                thumbnail=track['album']['images'][0]['url'] if track['album']['images'] else None,
                                                youtube_url=youtube_url,
                                                spotify_data={'spotify_url': track['external_urls']['spotify']}
                                            )
                                            recommendations.append(song)
                                            
                            except Exception as spotify_rec_error:
                                logger.warning(f"Spotify recommendations failed: {spotify_rec_error}")
                                    
            except Exception as e:
                logger.warning(f"Spotify autoplay failed: {e}")
        
        # YouTube-only autoplay
        if len(recommendations) < max_songs and ytdl:
            artist_name = last_song.artist.split(',')[0].strip()
            
            search_queries = [
                f"{artist_name} lagu terbaru",
                f"{artist_name} lagu populer",
                f"{last_song.title} remix",
                f"musik {artist_name}",
            ]
            
            for query in search_queries:
                if len(recommendations) >= max_songs:
                    break
                    
                try:
                    async with async_timeout.timeout(20):
                        search_results = await enhanced_youtube_search_multiple(query, max_songs - len(recommendations))
                        
                        for result in search_results:
                            if len(recommendations) >= max_songs:
                                break
                                
                            title = result.get('title', 'Unknown Title')
                            artist = result.get('uploader', 'Unknown Artist')
                            webpage_url = result.get('webpage_url', '')
                            duration = result.get('duration', 0)
                            
                            if duration and duration > MAX_DURATION:
                                continue
                            
                            is_duplicate = any(
                                (title.lower() in h.title.lower() or h.title.lower() in title.lower()) or
                                h.youtube_url == webpage_url or
                                title.lower() == last_song.title.lower()
                                for h in music_queue.autoplay_history
                            )
                            
                            if not is_duplicate and webpage_url:
                                song = Song(
                                    title=title,
                                    artist=artist,
                                    duration=duration,
                                    thumbnail=result.get('thumbnail'),
                                    youtube_url=webpage_url
                                )
                                recommendations.append(song)
                                
                except Exception as e:
                    logger.warning(f"YouTube autoplay search failed: {e}")
                    continue
        
        # Add to history
        for song in recommendations:
            music_queue.autoplay_history.append(song)
            
        logger.info(f"Generated {len(recommendations)} autoplay recommendations")
        return recommendations
        
    except Exception as e:
        logger.error(f"Failed to generate autoplay recommendations: {e}")
        return []

# Connection and playback functions
async def connect_to_voice_channel(ctx, music_queue: EnhancedMusicQueue, voice_channel):
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            if music_queue.voice_client and music_queue.voice_client.is_connected():
                if music_queue.voice_client.channel == voice_channel:
                    music_queue.reset_connection_failures()
                    return True
                else:
                    await music_queue.voice_client.move_to(voice_channel)
                    music_queue.reset_connection_failures()
                    return True
            
            if music_queue.voice_client and not music_queue.voice_client.is_connected():
                try:
                    await music_queue.voice_client.disconnect()
                except:
                    pass
                music_queue.voice_client = None
            
            if not music_queue.voice_client:
                music_queue.voice_client = await voice_channel.connect(timeout=15.0)
                music_queue.reset_connection_failures()
                return True
            
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Voice connection timeout (attempt {attempt + 1}/{max_attempts})")
            music_queue.increment_connection_failures()
            
            if music_queue.voice_client:
                try:
                    await music_queue.voice_client.disconnect()
                except:
                    pass
                music_queue.voice_client = None
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)
                
        except Exception as e:
            logger.error(f"Voice connection error: {e}")
            music_queue.increment_connection_failures()
            
            if music_queue.voice_client:
                try:
                    await music_queue.voice_client.disconnect()
                except:
                    pass
                music_queue.voice_client = None
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)
    
    return False

async def play_next_song(ctx, music_queue: EnhancedMusicQueue, status_msg=None):
    if music_queue.current is None:
        music_queue.current = music_queue.get_next_song()

    if not music_queue.current:
        music_queue.is_playing = False
        embed = discord.Embed(
            title="🏁 Queue Selesai",
            description="Semua lagu telah diputar!",
            color=0x808080
        )
        if status_msg:
            await status_msg.edit(embed=embed)
        else:
            await ctx.send(embed=embed)
        return

    try:
        music_queue.is_playing = True
        
        retry_config = RetryConfig(max_attempts=3, delay=2.0)
        
        try:
            if status_msg:
                loading_embed = discord.Embed(
                    title="⏳ Memuat Audio...",
                    description=f"Sedang mempersiapkan: **{music_queue.current.title}**",
                    color=0xFFFF00
                )
                await status_msg.edit(embed=loading_embed)
            
            source = await EnhancedYTDLSource.from_url(
                music_queue.current.youtube_url, 
                stream=True,
                retry_config=retry_config
            )
            music_queue.current.source = source
            
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
            
            if music_queue.current.retry_count < music_queue.current.max_retries:
                music_queue.current.retry_count += 1
                await asyncio.sleep(2)
                return await play_next_song(ctx, music_queue, status_msg)
            else:
                error_embed = discord.Embed(
                    title="❌ Gagal Memutar",
                    description=f"Tidak bisa memuat audio: **{music_queue.current.title}**",
                    color=0xFF0000
                )
                if status_msg:
                    await status_msg.edit(embed=error_embed)
                else:
                    await ctx.send(embed=error_embed)
                
                music_queue.current = None
                if music_queue.queue:
                    await asyncio.sleep(2)
                    await play_next_song(ctx, music_queue)
                else:
                    music_queue.is_playing = False
                return

        def after_playing(error):
            song_title = "Unknown"
            if music_queue.current and hasattr(music_queue.current, 'title'):
                song_title = music_queue.current.title
                music_queue.last_played_songs.append(music_queue.current)

            if error:
                logger.error(f'Player error for "{song_title}": {error}')
            
            music_queue.current = None
            
            coro = play_next_in_queue(ctx, music_queue)
            asyncio.run_coroutine_threadsafe(coro, bot.loop)

        if not music_queue.voice_client or not music_queue.voice_client.is_connected():
            music_queue.is_playing = False
            return

        music_queue.voice_client.play(source, after=after_playing)

        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{music_queue.current.title}**\nBy: {music_queue.current.artist}\nDurasi: {format_duration(music_queue.current.duration)}",
            color=0x9932CC
        )
        
        if music_queue.current.thumbnail:
            embed.set_thumbnail(url=music_queue.current.thumbnail)
        
        footer_text = "🎥 Dari YouTube"
        if music_queue.current.spotify_data:
            footer_text = "🎧 Metadata dari Spotify • 🎥 Audio dari YouTube"
        
        if len(music_queue.queue) > 0:
            footer_text += f" • {len(music_queue.queue)} lagu dalam queue"
            
        embed.set_footer(text=footer_text)
        
        if status_msg:
            await status_msg.edit(embed=embed)
        else:
            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error playing song: {e}")
        music_queue.is_playing = False
        music_queue.current = None

async def play_next_in_queue(ctx, music_queue: EnhancedMusicQueue):
    music_queue.current = music_queue.get_next_song()
    
    if music_queue.current:
        await play_next_song(ctx, music_queue)
    else:
        if (music_queue.autoplay_enabled and music_queue.last_played_songs and 
            music_queue.autoplay_failures < 3 and  
            time.time() - music_queue.last_autoplay_attempt > 30):
            
            try:
                music_queue.last_autoplay_attempt = time.time()
                last_song = music_queue.last_played_songs[-1]
                
                recommendations = await get_autoplay_recommendations(
                    last_song, 
                    music_queue, 
                    max_songs=3, 
                    max_duration=300
                )
                
                if recommendations:
                    music_queue.autoplay_failures = 0
                    
                    for song in recommendations:
                        music_queue.add_song(song)
                    
                    embed = discord.Embed(
                        title="🔄 Autoplay Aktif",
                        description=f"Menambahkan {len(recommendations)} lagu rekomendasi berdasarkan: **{last_song.title}**\n\n" + 
                                  "\n".join([
                                      f"• **{song.title}** - {song.artist} `[{format_duration(song.duration)}]`" 
                                      for song in recommendations[:3]
                                  ]),
                        color=0x9932CC
                    )
                    embed.set_footer(text="Gunakan !autoplay off untuk menonaktifkan")
                    await ctx.send(embed=embed)
                    
                    music_queue.current = music_queue.get_next_song()
                    if music_queue.current:
                        await play_next_song(ctx, music_queue)
                        return
                else:
                    music_queue.autoplay_failures += 1
                    
            except Exception as e:
                music_queue.autoplay_failures += 1
                logger.error(f"Autoplay error: {e}")
        
        music_queue.is_playing = False
        if not music_queue.autoplay_enabled:
            embed = discord.Embed(
                title="🏁 Queue Selesai",
                description="Semua lagu telah diputar!\n\n💡 *Aktifkan autoplay dengan `!autoplay on`*",
                color=0x808080
            )
            await ctx.send(embed=embed)

# Event handlers
@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot ready in {len(bot.guilds)} servers!')
    
    # Check prerequisites
    import shutil
    if not shutil.which('ffmpeg'):
        logger.error("FFmpeg not found in PATH!")
    else:
        logger.info("FFmpeg ready")
    
    try:
        if not discord.opus.is_loaded():
            opus_libs = ['libopus.so.0', 'libopus.so', 'opus', 'libopus']
            for lib_name in opus_libs:
                try:
                    discord.opus.load_opus(lib_name)
                    if discord.opus.is_loaded():
                        break
                except:
                    continue
        
        if discord.opus.is_loaded():
            logger.info("✅ Opus library loaded")
        else:
            logger.error("❌ Opus library not loaded")
    except Exception as e:
        logger.error(f"Opus initialization failed: {e}")
    
    bot.loop.create_task(enhanced_cleanup_task())

@bot.event
async def on_disconnect():
    logger.info("Bot disconnecting, cleaning up voice connections...")
    for guild_id, music_queue in music_queues.items():
        if music_queue.voice_client:
            try:
                if music_queue.voice_client.is_connected():
                    await music_queue.voice_client.disconnect()
            except Exception as e:
                logger.error(f"Error cleaning up voice client: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user:
        return
    
    for guild_id, music_queue in music_queues.items():
        try:
            if music_queue.voice_client and music_queue.voice_client.channel:
                if not music_queue.voice_client.is_connected():
                    continue
                    
                channel = music_queue.voice_client.channel
                try:
                    human_members = [m for m in channel.members if not m.bot]
                except (AttributeError, IndexError):
                    continue
                
                if len(human_members) == 0:
                    bot.loop.create_task(delayed_disconnect_if_alone(guild_id, 120))
        except Exception as e:
            logger.error(f"Error in voice state update: {e}")

async def delayed_disconnect_if_alone(guild_id: int, delay: int):
    await asyncio.sleep(delay)
    
    music_queue = music_queues.get(guild_id)
    if not music_queue or not music_queue.voice_client:
        return
    
    try:
        if not music_queue.voice_client.is_connected():
            return
            
        channel = music_queue.voice_client.channel
        if not channel:
            return
            
        try:
            human_members = [m for m in channel.members if not m.bot]
        except (AttributeError, IndexError):
            return
        
        if len(human_members) == 0:
            try:
                music_queue.clear_queue()
                music_queue.current = None
                music_queue.is_playing = False
                await music_queue.voice_client.disconnect()
                music_queue.voice_client = None
                logger.info(f"Auto-disconnected from empty channel in guild {guild_id}")
            except Exception as e:
                logger.error(f"Error during auto-disconnect: {e}")
    except Exception as e:
        logger.error(f"Error in delayed disconnect: {e}")

async def enhanced_cleanup_task():
    while not bot.is_closed():
        try:
            current_time = time.time()
            
            for guild_id, music_queue in list(music_queues.items()):
                # Clean up disconnected clients
                if music_queue.voice_client and not music_queue.voice_client.is_connected():
                    music_queue.voice_client = None
                    music_queue.is_playing = False
                    music_queue.current = None
                    music_queue.clear_queue()
                
                # Auto-disconnect inactive bots
                elif music_queue.voice_client and music_queue.is_inactive(timeout_minutes=15):
                    try:
                        await music_queue.voice_client.disconnect()
                        music_queue.voice_client = None
                        music_queue.is_playing = False
                        music_queue.current = None
                        music_queue.clear_queue()
                    except Exception as e:
                        logger.error(f"Error during inactive disconnect: {e}")
            
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
            await asyncio.sleep(30)

# Commands
@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query: str):
    """
    Play music from various sources
    Examples:
    - !play Shape of You
    - !play https://open.spotify.com/track/...
    - !play https://www.youtube.com/watch?v=...
    """
    if not ctx.author.voice:
        embed = discord.Embed(
            title="❌ Error",
            description="Anda harus berada di voice channel untuk menggunakan bot ini!",
            color=0xFF0000
        )
        return await ctx.send(embed=embed)

    voice_channel = ctx.author.voice.channel
    music_queue = get_music_queue(ctx.guild.id)

    if not await connect_to_voice_channel(ctx, music_queue, voice_channel):
        if music_queue.should_give_up_connection():
            embed = discord.Embed(
                title="❌ Connection Failed",
                description="Tidak dapat terhubung ke voice channel setelah beberapa percobaan.",
                color=0xFF0000
            )
            return await ctx.send(embed=embed)

    processing_embed = discord.Embed(
        title="🔍 Mencari musik...",
        description=f"Sedang memproses: `{query}`",
        color=0xFFFF00
    )
    processing_msg = await ctx.send(embed=processing_embed)

    song = None
    search_method = "Unknown"

    try:
        if is_spotify_url(query):
            search_method = "Spotify URL"
            spotify_data = await get_spotify_track_info(query)
            if spotify_data:
                youtube_url = await search_youtube_for_song(spotify_data['title'], spotify_data['artist'])
                if youtube_url:
                    song = Song(
                        title=spotify_data['title'],
                        artist=spotify_data['artist'],
                        duration=spotify_data['duration'],
                        thumbnail=spotify_data['thumbnail'],
                        youtube_url=youtube_url,
                        spotify_data=spotify_data
                    )

        elif is_youtube_url(query):
            search_method = "YouTube URL"
            youtube_data = await get_youtube_info(query)
            if youtube_data:
                song = Song(
                    title=youtube_data['title'],
                    artist="Unknown Artist",
                    duration=youtube_data['duration'],
                    thumbnail=youtube_data['thumbnail'],
                    youtube_url=youtube_data['url']
                )

        else:
            search_method = "Smart Search"
            
            if spotify:
                spotify_data = await search_spotify_track(query)
                if spotify_data:
                    youtube_url = await search_youtube_for_song(spotify_data['title'], spotify_data['artist'])
                    if youtube_url:
                        song = Song(
                            title=spotify_data['title'],
                            artist=spotify_data['artist'],
                            duration=spotify_data['duration'],
                            thumbnail=spotify_data['thumbnail'],
                            youtube_url=youtube_url,
                            spotify_data=spotify_data
                        )
                        search_method = "Spotify + YouTube"
            
            if not song and ytdl:
                try:
                    async with async_timeout.timeout(45):
                        loop = asyncio.get_event_loop()
                        search_results = await loop.run_in_executor(
                            None,
                            lambda: ytdl.extract_info(f"ytsearch1:{query}", download=False)
                        )
                        
                        if search_results and 'entries' in search_results and search_results['entries']:
                            first_result = search_results['entries'][0]
                            song = Song(
                                title=first_result.get('title', 'Unknown Title'),
                                artist=first_result.get('uploader', 'Unknown Artist'),
                                duration=first_result.get('duration'),
                                thumbnail=first_result.get('thumbnail'),
                                youtube_url=first_result.get('webpage_url')
                            )
                            search_method = "YouTube Direct"
                            
                except Exception as e:
                    logger.error(f"Direct YouTube search failed: {e}")

        if not song:
            error_embed = discord.Embed(
                title="❌ Pencarian Gagal",
                description=f"Tidak dapat menemukan lagu: `{query}`",
                color=0xFF0000
            )
            return await processing_msg.edit(embed=error_embed)

        music_queue.add_song(song)

        if not music_queue.is_playing:
            await play_next_song(ctx, music_queue, processing_msg)
        else:
            embed = discord.Embed(
                title="✅ Ditambahkan ke Queue",
                description=f"**{song.title}**\nBy: {song.artist}\nDurasi: {format_duration(song.duration)}",
                color=0x00FF00
            )
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            embed.set_footer(text=f"Posisi dalam queue: {len(music_queue.queue)} • Metode: {search_method}")
            await processing_msg.edit(embed=embed)

    except Exception as e:
        logger.error(f"Play command error: {e}")
        error_embed = discord.Embed(
            title="❌ Error",
            description="Terjadi kesalahan sistem. Silakan coba lagi.",
            color=0xFF0000
        )
        await processing_msg.edit(embed=error_embed)

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """
    Skip the current song
    Example: !skip
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if music_queue.voice_client and music_queue.voice_client.is_playing():
        skipped_title = "Unknown"
        if music_queue.current and music_queue.current.title:
            skipped_title = music_queue.current.title
            
        music_queue.voice_client.stop()
        
        embed = discord.Embed(
            title="⏭️ Skipped",
            description=f"Dilewati: **{skipped_title}**",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="Tidak ada lagu yang sedang diputar!",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop(ctx):
    """
    Stop playback and clear queue
    Example: !stop
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if music_queue.voice_client:
        queue_count = len(music_queue.queue)
        current_song = music_queue.current.title if music_queue.current else None
        
        music_queue.clear_queue()
        music_queue.current = None
        music_queue.is_playing = False
        music_queue.voice_client.stop()
        
        embed = discord.Embed(
            title="⏹️ Stopped",
            description=f"Musik dihentikan dan queue dibersihkan!\n\n**Dihentikan:** {current_song or 'None'}\n**Dibersihkan:** {queue_count} lagu",
            color=0xFF6B6B
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error", 
            description="Bot tidak sedang memutar musik!",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    """
    Display the current music queue
    Example: !queue
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if not music_queue.current and not music_queue.queue:
        embed = discord.Embed(
            title="📝 Queue Kosong",
            description="Tidak ada lagu dalam queue!\n\nGunakan `!play <lagu>` untuk menambahkan lagu.",
            color=0x808080
        )
        return await ctx.send(embed=embed)

    embed = discord.Embed(
        title="📝 Music Queue",
        color=0x9932CC
    )

    if music_queue.current:
        status = "🎵 Playing" if music_queue.voice_client and music_queue.voice_client.is_playing() else "⏸️ Paused"
        embed.add_field(
            name=f"{status}",
            value=f"**{music_queue.current.title}**\nBy: {music_queue.current.artist}\nDurasi: {format_duration(music_queue.current.duration)}",
            inline=False
        )

    if music_queue.queue:
        queue_list = []
        total_duration = 0
        
        for i, song in enumerate(list(music_queue.queue)[:15], 1):
            duration_str = format_duration(song.duration)
            queue_list.append(f"`{i}.` **{song.title}** - {song.artist} `[{duration_str}]`")
            if song.duration:
                total_duration += song.duration
        
        embed.add_field(
            name=f"📋 Up Next ({len(music_queue.queue)} lagu)",
            value="\n".join(queue_list),
            inline=False
        )
        
        if len(music_queue.queue) > 15:
            embed.add_field(
                name="➕ Additional",
                value=f"Dan {len(music_queue.queue) - 15} lagu lainnya...",
                inline=False
            )
        
        if total_duration > 0:
            embed.set_footer(text=f"Total durasi queue: {format_duration(total_duration)}")

    await ctx.send(embed=embed)

@bot.command(name='disconnect', aliases=['dc', 'leave'])
async def disconnect(ctx):
    """
    Disconnect bot from voice channel
    Example: !disconnect
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if music_queue.voice_client:
        queue_count = len(music_queue.queue)
        music_queue.clear_queue()
        music_queue.current = None
        music_queue.is_playing = False
        
        await music_queue.voice_client.disconnect()
        music_queue.voice_client = None
        
        embed = discord.Embed(
            title="👋 Disconnected",
            description=f"Bot keluar dari voice channel!\n\n**Dibersihkan:** {queue_count} lagu dari queue",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="Bot tidak terhubung ke voice channel!",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

@bot.command(name='pause')
async def pause(ctx):
    """
    Pause current playback
    Example: !pause
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if music_queue.voice_client and music_queue.voice_client.is_playing():
        music_queue.voice_client.pause()
        
        song_title = music_queue.current.title if music_queue.current else "Unknown"
        embed = discord.Embed(
            title="⏸️ Paused",
            description=f"**{song_title}** dijeda!\n\nGunakan `!resume` untuk melanjutkan.",
            color=0xFFFF00
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="Tidak ada musik yang sedang diputar!",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

@bot.command(name='resume')
async def resume(ctx):
    """
    Resume paused playback
    Example: !resume
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if music_queue.voice_client and music_queue.voice_client.is_paused():
        music_queue.voice_client.resume()
        
        song_title = music_queue.current.title if music_queue.current else "Unknown"
        embed = discord.Embed(
            title="▶️ Resumed",
            description=f"**{song_title}** dilanjutkan!",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="Musik tidak sedang dijeda!",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    """
    Show currently playing song
    Example: !nowplaying
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if not music_queue.current:
        embed = discord.Embed(
            title="❌ Error",
            description="Tidak ada musik yang sedang diputar!",
            color=0xFF0000
        )
        return await ctx.send(embed=embed)

    if music_queue.voice_client:
        if music_queue.voice_client.is_playing():
            status = "🎵 Playing"
            color = 0x9932CC
        elif music_queue.voice_client.is_paused():
            status = "⏸️ Paused"
            color = 0xFFFF00
        else:
            status = "⏹️ Stopped"
            color = 0xFF6B6B
    else:
        status = "❓ Unknown"
        color = 0x808080

    embed = discord.Embed(
        title=status,
        description=f"**{music_queue.current.title}**\nBy: {music_queue.current.artist}\nDurasi: {format_duration(music_queue.current.duration)}",
        color=color
    )
    
    if music_queue.current.thumbnail:
        embed.set_thumbnail(url=music_queue.current.thumbnail)
    
    footer_text = "🎥 Dari YouTube"
    if music_queue.current.spotify_data:
        footer_text = "🎧 Metadata dari Spotify • 🎥 Audio dari YouTube"
    
    if len(music_queue.queue) > 0:
        footer_text += f" • {len(music_queue.queue)} lagu dalam queue"
        
    embed.set_footer(text=footer_text)
    
    await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear_queue(ctx):
    """
    Clear the music queue
    Example: !clear
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if not music_queue.queue:
        embed = discord.Embed(
            title="❌ Queue Kosong",
            description="Queue sudah kosong!",
            color=0xFF0000
        )
        return await ctx.send(embed=embed)
    
    queue_count = len(music_queue.queue)
    music_queue.clear_queue()
    
    embed = discord.Embed(
        title="🗑️ Queue Dibersihkan",
        description=f"Berhasil menghapus **{queue_count} lagu** dari queue!",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command(name='autoplay', aliases=['ap'])
async def autoplay(ctx, action: str = None):
    """
    Toggle autoplay functionality
    Examples:
    - !autoplay - Check status
    - !autoplay on - Enable autoplay
    - !autoplay off - Disable autoplay
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if action is None:
        status_text = "**Aktif**" if music_queue.autoplay_enabled else "**Nonaktif**"
        embed = discord.Embed(
            title="🔄 Status Autoplay",
            description=f"Autoplay saat ini: {status_text}",
            color=0x00FF00 if music_queue.autoplay_enabled else 0xFF0000
        )
        
        if music_queue.last_played_songs:
            last_song = music_queue.last_played_songs[-1]
            embed.add_field(
                name="🎵 Lagu Referensi Terakhir",
                value=f"**{last_song.title}** - {last_song.artist}",
                inline=False
            )
        
        return await ctx.send(embed=embed)
    
    action = action.lower()
    if action in ['on', 'enable', 'aktif', '1', 'true']:
        if music_queue.autoplay_enabled:
            embed = discord.Embed(
                title="ℹ️ Autoplay Sudah Aktif",
                description="Autoplay sudah dalam keadaan aktif!",
                color=0xFFFF00
            )
        else:
            music_queue.autoplay_enabled = True
            embed = discord.Embed(
                title="✅ Autoplay Diaktifkan",
                description="Autoplay berhasil diaktifkan! Bot akan otomatis memutar lagu rekomendasi ketika queue kosong.",
                color=0x00FF00
            )
            
    elif action in ['off', 'disable', 'nonaktif', '0', 'false']:
        if not music_queue.autoplay_enabled:
            embed = discord.Embed(
                title="ℹ️ Autoplay Sudah Nonaktif",
                description="Autoplay sudah dalam keadaan nonaktif!",
                color=0xFFFF00
            )
        else:
            music_queue.autoplay_enabled = False
            embed = discord.Embed(
                title="🔴 Autoplay Dinonaktifkan",
                description="Autoplay berhasil dinonaktifkan.",
                color=0xFF0000
            )
    else:
        embed = discord.Embed(
            title="❌ Parameter Tidak Valid",
            description="Gunakan `!autoplay on` atau `!autoplay off`",
            color=0xFF0000
        )
    
    await ctx.send(embed=embed)

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, volume: int = None):
    """
    Adjust playback volume
    Examples:
    - !volume - Check current volume
    - !volume 50 - Set volume to 50%
    - !volume 100 - Set volume to 100%
    """
    music_queue = get_music_queue(ctx.guild.id)
    
    if not music_queue.voice_client or not music_queue.current or not music_queue.current.source:
        embed = discord.Embed(
            title="❌ Error",
            description="Tidak ada musik yang sedang diputar!",
            color=0xFF0000
        )
        return await ctx.send(embed=embed)

    if volume is None:
        current_vol = int(music_queue.current.source.volume * 100)
        embed = discord.Embed(
            title="🔊 Volume Info",
            description=f"Volume saat ini: **{current_vol}%**",
            color=0x00FF00
        )
        return await ctx.send(embed=embed)

    if volume < 0 or volume > 200:
        embed = discord.Embed(
            title="❌ Volume Invalid",
            description="Volume harus antara **0-200**!",
            color=0xFF0000
        )
        return await ctx.send(embed=embed)

    music_queue.current.source.volume = volume / 100.0
    
    if volume == 0:
        volume_emoji = "🔇"
        status = "Muted"
    elif volume <= 50:
        volume_emoji = "🔉"
        status = "Low"
    elif volume <= 100:
        volume_emoji = "🔊"
        status = "Normal"
    else:
        volume_emoji = "📢"
        status = "High"

    embed = discord.Embed(
        title=f"{volume_emoji} Volume Changed",
        description=f"Volume diatur ke **{volume}%** ({status})",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['commands'])
async def show_help(ctx):
    """
    Show help information
    Example: !help
    """
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="Bot musik Discord yang dioptimalkan untuk koneksi jaringan yang tidak stabil",
        color=0x9932CC
    )
    
    embed.add_field(
        name="🎵 Playback Commands",
        value=(
            "`!play <lagu/url>` - Putar lagu dari pencarian, YouTube, atau Spotify\n"
            "`!pause` - Jeda musik\n"
            "`!resume` - Lanjutkan musik\n"
            "`!skip` - Lewati lagu saat ini\n"
            "`!stop` - Hentikan musik dan bersihkan queue\n"
            "`!volume <0-200>` - Atur volume\n"
            "`!autoplay on/off` - Toggle autoplay rekomendasi"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📋 Queue Commands", 
        value=(
            "`!queue` - Lihat daftar lagu dalam queue\n"
            "`!nowplaying` - Info lagu yang sedang diputar\n"
            "`!clear` - Bersihkan queue"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔄 Autoplay Feature",
        value=(
            "`!autoplay` - Cek status autoplay\n"
            "`!autoplay on` - Aktifkan autoplay\n"
            "`!autoplay off` - Nonaktifkan autoplay"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔧 Connection Commands",
        value=(
            "`!disconnect` - Keluar dari voice channel\n"
            "`!help` - Tampilkan bantuan ini"
        ),
        inline=False
    )

    embed.set_footer(text="Bot ini dioptimalkan untuk koneksi jaringan yang lambat atau tidak stabil")
    
    await ctx.send(embed=embed)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ Command Not Found",
            description=f"Command tidak ditemukan. Gunakan `!help` untuk melihat daftar command.",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Argument",
            description=f"Parameter yang dibutuhkan tidak ada.\n\nGunakan: `!{ctx.command} {ctx.command.signature}`",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Argument",
            description="Parameter yang diberikan tidak valid. Periksa format dan coba lagi.",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        
    else:
        logger.error(f"Unhandled command error: {error}")
        embed = discord.Embed(
            title="❌ Unexpected Error",
            description="Terjadi kesalahan yang tidak terduga. Silakan coba lagi.",
            color=0xFF0000
        )
        await ctx.send(embed=embed)

# Main execution
if __name__ == "__main__":
    discord_token = os.getenv('DISCORD_TOKEN')
    
    if not discord_token:
        logger.error("DISCORD_TOKEN not found in environment variables!")
        print("\n❌ DISCORD_TOKEN tidak ditemukan!")
        print("Pastikan file .env sudah dibuat dan berisi:")
        print("DISCORD_TOKEN=your_discord_bot_token_here")
        sys.exit(1)
    
    try:
        logger.info("Starting Discord Music Bot...")
        bot.run(discord_token, log_handler=None)
    except discord.LoginFailure:
        logger.error("Invalid Discord token!")
        print("\n❌ Token Discord tidak valid!")
        print("Periksa kembali DISCORD_TOKEN di file .env")
    except Exception as e:
        logger.error(f"Bot startup failed: {e}")
        print(f"\n❌ Bot gagal start: {e}")