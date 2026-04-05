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
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Command Reference](#command-reference)
- [Troubleshooting](#troubleshooting)
- [Privacy & Data](#privacy--data)
- [Contributing & Support](#contributing--support)
- [License](#license)

---

<a id="what-is-cleo-musik"></a>

## ＼(＾O＾)／ What is Cleo Musik?

Cleo Musik is a minimalist Discord music bot — no ads, no premium tiers, no limits, just music and kawaii vibes!

- **No web UI**: Only simple slash commands.
- **100% free**: All features unlocked for everyone.
- **Unlimited playback**: Giant playlists, endless queues, eternal tunes!

**Supports YouTube, SoundCloud, Spotify, Deezer, Apple Music, Tidal, Amazon Music, direct audio links, and local files.**  
Type `/play <url or query>` and let the music flow~

---

<a id="key-features"></a>

## (≧◡≦) Key Features

- 🎵 Play from **8+ sources**: YouTube • SoundCloud • Spotify • Deezer • Apple Music • Tidal • Amazon Music • **Direct Audio Links** • **Local Files**
- ⌨️ Slash commands: `/play`, `/search`, `/pause`, `/skip`, `/queue`, `/remove`, and more!
- 📁 **Play Local Files**: Upload and play your own audio/video files directly.
- 🔗 **Direct Audio Links**: Stream from any audio URL (MP3, FLAC, WAV, etc.)
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
| **FFmpeg**     | Required              | Latest stable                         |
| **OS**         | Linux, Windows, macOS | Windows 10+, Ubuntu 20.04+, macOS 11+ |

---

<a id="installation"></a>

## (＾∀＾) Installation

### 🐳 Method 1: Docker (Recommended for VPS/Server)

```bash
git clone https://github.com/ihsanaminul/MusicBot.git
cd MusicBot
cp .env.example .env
# Edit .env with your tokens, then:
docker compose up -d --build
```

### 🛠️ Method 2: Manual (Recommended for Local/PC)

```bash
git clone https://github.com/ihsanaminul/MusicBot.git
cd MusicBot
pip install -r requirements.txt
playwright install
cp .env.example .env
# Edit .env with your tokens, then:
python playify.py
```

### 🔑 Required Tokens (`.env`)

```ini
DISCORD_TOKEN=your_discord_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
GENIUS_TOKEN=your_genius_api_token
```

### 🔗 Inviting the Bot to Your Server

1. Go to your [Discord Developer Portal](https://discord.com/developers/applications).
2. Enable **Guilds**, **Voice States**, and **Message Content** intents.
3. Generate an invite link with `Connect`, `Speak`, and `Send Messages` permissions.
4. Add the bot to your server and enjoy `/play`!

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
| `/status`                | Show the bot's performance and resource usage.                          |
| `/kaomoji`               | Toggle cute kaomoji responses. `(ADMIN)`                                |

---

<a id="troubleshooting"></a>

## (｀・ω・´) Troubleshooting

| Problem | Solution |
| :------ | :------- |
| **FFmpeg not found** | Ensure FFmpeg is installed & added to PATH. |
| **Spotify errors** | Check `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`. |
| **Bot offline / unresponsive** | Check `DISCORD_TOKEN` and bot permissions in the Developer Portal. |
| **Direct link not playing** | Ensure the URL points directly to an audio file and is publicly accessible. |
| **High CPU / memory usage** | Reduce `QUEUE_MAX_SIZE` or lower `CACHE_METADATA_TTL` in `.env`. |
| **Frequent disconnects** | Lower `SILENCE_CHECK_INTERVAL` in `.env` (default: 15s). |

---

<a id="privacy--data"></a>

## (ﾉ◕ヮ◕)ﾉ Privacy & Data

- **Self-hosted**: All logs are stored locally. Zero telemetry is sent anywhere.
- **Public instances**: Only minimal error logs are kept for debugging. No user data or analytics collected.

---

<a id="contributing--support"></a>

## (ง＾◡＾)ง Contributing & Support

- 🐛 **Found a bug?** Open an [issue](https://github.com/ihsanaminul/MusicBot/issues).
- 💡 **Have an idea?** Start a [discussion](https://github.com/ihsanaminul/MusicBot/discussions).
- 🔧 **Want to contribute?** Fork the repo and open a pull request!
- ⭐ **Enjoying the bot?** Star the repository — it means a lot!
- 💬 **Need help?** Join our [Discord Server](https://discord.com/oauth2/authorize?client_id=1416435130402082909&permissions=36785216&integration_type=0&scope=bot+applications.commands).

---

<a id="license"></a>

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built with ☕ and love by <a href="https://github.com/ihsanaminul">ihsanaminul</a> (｡♥‿♥｡)<br/>
  <sub>Cleo Musik v2026.04 — Keep the music playing~</sub>
</p>