<h1 align="center">🎵 Cleo Musik ♪(｡◕‿◕｡)</h1>

<p align="center">
  <img src="https://image2url.com/images/1764519755428-cad6bced-fa34-4c61-9d01-4fb741893f6e.png" alt="Cleo Musik Banner" width="900">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/version-v2026.04-brightgreen.svg" alt="Version" />
  <img src="https://img.shields.io/badge/license-MIT-orange.svg" alt="License" />
  <img src="https://img.shields.io/badge/FFmpeg-required-red.svg" alt="FFmpeg" />
  <a href="https://discord.com/oauth2/authorize?client_id=1416435130402082909&permissions=36785216&integration_type=0&scope=bot+applications.commands">
    <img src="https://img.shields.io/discord/1395755097350213632?label=Discord%20Server&logo=discord" alt="Discord Server" />
  </a>
</p>

---

## Table of Contents

- [What is Cleo Musik?](#what-is-cleo-musik)
- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Performance Tuning](#performance-tuning)
- [Command Reference](#command-reference)
- [Troubleshooting](#troubleshooting)
- [Privacy & Data](#privacy--data)
- [Contributing & Support](#contributing--support)
- [License](#license)

---

<a id="what-is-cleo-musik"></a>

## ＼(＾O＾)／ What is Cleo Musik?

Cleo Musik is the ultimate minimalist Discord music bot — no ads, no premium tiers, no limits, just music and kawaii vibes!

- **No web UI**: Only simple slash commands.
- **100% free**: All features unlocked for everyone.
- **Unlimited playback**: Giant playlists, endless queues, eternal tunes!

**Supports YouTube, SoundCloud, Spotify, Deezer, Apple Music, Tidal, Amazon Music, direct audio links, and local files.**  
Type `/play <url or query>` and let the music flow~

---

<a id="quick-start"></a>

## ⚡ Quick Start

Just want to get it running fast? Here you go:

```bash
git clone https://github.com/ihsanaminul/MusicBot.git
cd MusicBot
cp .env.example .env
# Edit .env with your tokens, then:
docker compose up -d --build
```

That's it! Invite the bot to your server and use `/play` to start jamming. 🎶  
For a full setup guide, see [Installation](#installation).

---

<a id="key-features"></a>

## (≧◡≦) Key Features

- 🎵 Play from **8+ sources**: YouTube • SoundCloud • Spotify • Deezer • Apple Music • Tidal • Amazon Music • **Direct Audio Links** • **Local Files**
- ⌨️ Slash commands: `/play`, `/search`, `/pause`, `/skip`, `/queue`, `/remove`, and more!
- 📁 **Play Local Files**: Directly upload and play your own audio/video files.
- 🔗 **Direct Audio Links**: Stream music from any audio URL (MP3, FLAC, WAV, etc.)
- 🔁 **Autoplay** of similar tracks (YouTube Mix, SoundCloud Stations)
- 🔀 **Loop** & **shuffle** controls
- 🌸 **Kawaii Mode** toggles cute kaomoji responses (`/kaomoji`)
- 🎛️ Audio **filters**: slowed, reverb, bass boost, nightcore, and more
- Powered by `yt-dlp`, `FFmpeg`, `asyncio`, and a dash of chaos

---

<a id="system-requirements"></a>

## ⚙️ System Requirements

| Requirement    | Minimum               | Recommended                           |
| :------------- | :-------------------- | :------------------------------------ |
| **Python**     | 3.10                  | 3.11+                                 |
| **RAM**        | 512 MB                | 2 GB                                  |
| **Disk Space** | 500 MB                | 2 GB                                  |
| **CPU Cores**  | 1                     | 2+                                    |
| **FFmpeg**     | Required              | Latest stable                         |
| **OS**         | Linux, Windows, macOS | Windows 10+, Ubuntu 20.04+, macOS 11+ |

**Docker Setup** (Recommended):

- Docker 20.10+
- Docker Compose 1.29+
- No additional dependencies needed — everything is containerized!

---

<a id="installation"></a>

## (＾∀＾) Installation

You can run Cleo Musik in two ways. Docker is recommended for most users as it's simpler and manages all dependencies automatically.

### 🐳 Method 1: Docker Setup (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ihsanaminul/MusicBot.git
   cd MusicBot
   ```

2. **Create your config file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your tokens:
   ```ini
   DISCORD_TOKEN=your_discord_bot_token
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   GENIUS_TOKEN=your_genius_api_token
   ```

3. **Start the bot:**
   ```bash
   docker compose up -d --build
   ```
   View live logs with `docker compose logs -f`.

---

### 🛠️ Method 2: Manual Setup

**Requirements:** Python 3.10+, FFmpeg in PATH, Git

1. **Clone the repo:**
   ```bash
   git clone https://github.com/ihsanaminul/MusicBot.git
   cd MusicBot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your tokens (same as Docker method)
   ```

4. **Run the bot:**
   ```bash
   python playify.py
   ```

---

### 🔗 Inviting the Bot to Your Server

1. Go to your [Discord Developer Portal](https://discord.com/developers/applications).
2. Enable the **Guilds**, **Voice States**, and **Message Content** intents.
3. Generate an invite link with `Connect`, `Speak`, and `Send Messages` permissions.
4. Add the bot to your server and enjoy `/play`!

---

<a id="performance-tuning"></a>

## 🚀 Performance Tuning

Configure these in your `.env` file for optimal performance based on your server size and hardware.

### Essential Environment Variables

```ini
# Cache Configuration
CACHE_METADATA_TTL=7200       # Cache metadata for 2 hours (speeds up repeat searches)
CACHE_STREAM_TTL=300          # Cache stream URLs for 5 minutes (reduces API calls)
QUEUE_MAX_SIZE=5000           # Maximum songs in queue

# Performance Optimization
PROCESS_POOL_WORKERS=0        # Auto-detect CPU count (0 = auto, 1+ = fixed)
SILENCE_CHECK_INTERVAL=15     # Check for silence every 15 seconds
DB_QUERY_TIMEOUT=15           # Database query timeout in seconds

# Docker Resource Limits (docker-compose.yml)
CPU_LIMIT=2.0                 # Maximum CPU cores
MEMORY_LIMIT=2G               # Maximum RAM
```

### Performance Impact (v2026.04)

| Optimization                | Improvement            | Implementation                    |
| :-------------------------- | :--------------------- | :-------------------------------- |
| **Dependency Optimization** | 20–30% faster build    | Updated packages to latest stable |
| **Container Size**          | 15–20% smaller image   | Optimized Docker layers & caching |
| **Cache System**            | 15–20% faster searches | Metadata & stream URL caching     |
| **Type Hints**              | Easier debugging       | 40%+ code coverage                |
| **Health Monitoring**       | Auto-recovery          | Integrated health checks          |
| **Resource Limits**         | Stable performance     | CPU & memory caps                 |

### Recommended Settings by Scale

**Small Server (< 500 members):**
```ini
PROCESS_POOL_WORKERS=1
CACHE_METADATA_TTL=3600
SILENCE_CHECK_INTERVAL=20
```

**Medium Server (500–5,000 members):**
```ini
PROCESS_POOL_WORKERS=2
CACHE_METADATA_TTL=7200
SILENCE_CHECK_INTERVAL=15
MEMORY_LIMIT=2G
```

**Large Server (5,000+ members):**
```ini
PROCESS_POOL_WORKERS=4
CACHE_METADATA_TTL=14400
SILENCE_CHECK_INTERVAL=10
MEMORY_LIMIT=4G
CPU_LIMIT=4.0
```

---

<a id="command-reference"></a>

## (⊙‿⊙) Command Reference

| Command                  | Description                                                             |
| :----------------------- | :---------------------------------------------------------------------- |
| `/play <url/query>`      | Add a song or playlist from a link/search. Supports direct audio links! |
| `/search <query>`        | Search for a song and choose from the top results.                      |
| `/play-files <file1...>` | Play one or more uploaded audio/video files.                            |
| `/playnext <query/file>` | Add a song or local file to the front of the queue.                     |
| `/pause`                 | Pause playback.                                                         |
| `/resume`                | Resume playback.                                                        |
| `/skip`                  | Skip the current track. Replays if loop is enabled.                     |
| `/stop`                  | Stop playback, clear queue, and disconnect.                             |
| `/nowplaying`            | Display the current track's information.                                |
| `/seek`                  | Open an interactive menu to seek, fast-forward, or rewind.              |
| `/queue`                 | Show the current song queue with interactive pages.                     |
| `/remove`                | Open a menu to remove specific songs from the queue.                    |
| `/shuffle`               | Shuffle the queue.                                                      |
| `/clearqueue`            | Clear all songs from the queue.                                         |
| `/loop`                  | Toggle looping for the current track.                                   |
| `/autoplay`              | Toggle autoplay of similar songs when the queue ends.                   |
| `/24_7 <mode>`           | Keep the bot in channel (`normal`, `auto`, or `off`).                   |
| `/filter`                | Apply real-time audio filters (nightcore, bassboost, etc.).             |
| `/lyrics`                | Fetch and display lyrics for the current song.                          |
| `/karaoke`               | Start a karaoke session with synced lyrics.                             |
| `/reconnect`             | Refresh the voice connection without losing your place.                 |
| `/status`                | Show the bot's detailed performance and resource usage.                 |
| `/kaomoji`               | Toggle cute kaomoji responses. `(ADMIN)`                                |

---

<a id="troubleshooting"></a>

## (｀・ω・´) Troubleshooting

### General Issues

| Problem | Solution |
| :------ | :------- |
| **FFmpeg not found** | Ensure FFmpeg is installed & in PATH. Docker handles this automatically. |
| **Spotify errors** | Verify `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`. |
| **Bot offline / unresponsive** | Check `DISCORD_TOKEN` and bot permissions in the Developer Portal. |
| **Direct link not playing** | Ensure the URL points directly to an audio file and is publicly accessible. |

### Performance Issues

| Problem | Solution |
| :------ | :------- |
| **High CPU usage** | Set `PROCESS_POOL_WORKERS=0` for auto-detection, or increase the count. |
| **Memory leaks** | Keep `CACHE_STREAM_TTL` at 300s or lower. Reduce `QUEUE_MAX_SIZE` if needed. |
| **Slow search results** | Increase `CACHE_METADATA_TTL` (default: 7200s). |
| **Frequent disconnects** | Lower `SILENCE_CHECK_INTERVAL` to detect dead connections faster. |

### Docker-Specific Issues

| Problem | Solution |
| :------ | :------- |
| **Container keeps restarting** | Check logs: `docker compose logs`. Health check may need adjustment. |
| **Out of memory** | Increase `MEMORY_LIMIT` in `.env`, then restart: `docker compose down && docker compose up -d`. |
| **Permission denied (Linux)** | Run: `sudo usermod -aG docker $USER`, then log out and back in. |
| **Port already in use** | Change the port mapping in `docker-compose.yml`. |

---

<a id="privacy--data"></a>

## (ﾉ◕ヮ◕)ﾉ Privacy & Data

- **Self-hosted**: All logs are stored locally on your machine. Zero telemetry is sent anywhere.
- **Public instances**: Only minimal error logs are kept for debugging. No user data or analytics are ever collected.

---

<a id="contributing--support"></a>

## (ง＾◡＾)ง Contributing & Support

Contributions are always welcome! Here's how you can help:

- 🐛 **Found a bug?** Open an [issue](https://github.com/ihsanaminul/MusicBot/issues).
- 💡 **Have an idea?** Start a [discussion](https://github.com/ihsanaminul/MusicBot/discussions).
- 🔧 **Want to contribute?** Fork the repo and open a pull request!
- ⭐ **Enjoying the bot?** Star the repository — it means a lot!
- 💬 **Need help?** Join our [Discord Server](https://discord.com/oauth2/authorize?client_id=1416435130402082909&permissions=36785216&integration_type=0&scope=bot+applications.commands) and ask away.

---

<a id="license"></a>

## 📄 License

This project is licensed under the [MIT License](LICENSE).  
You are free to use, modify, and distribute this project with proper attribution.

---

<p align="center">
  Built with ☕ and love by <a href="https://github.com/ihsanaminul">ihsanaminul</a> (｡♥‿♥｡)<br/>
  <sub>Cleo Musik v2026.04 — Keep the music playing~</sub>
</p>