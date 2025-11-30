<h1 align="center">🎵 Cleo Musik ♪(｡◕‿◕｡)</h1>

<p align="center">
  <img src="https://i.pinimg.com/736x/c8/10/99/c81099a28532cbde421b62cf95a124b2.jpg" alt="Playify Banner" weight="300">
</p>

---

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+" />
  <a href="https://discord.com/oauth2/authorize?client_id=1416435130402082909&permissions=36785216&integration_type=0&scope=bot+applications.commands"><img src="https://img.shields.io/discord/1395755097350213632?label=Discord%20Server&logo=discord" alt="Discord Server" /></a>
</p>

---

## Table of Contents

- [What is Cleo Musik?](#what-is-cleo-musik)
- [Key Features](#key-features)
- [Installation](#installation)
- [Command Reference](#command-reference)
- [Troubleshooting](#troubleshooting)
- [Privacy & Data](#privacy--data)
- [Contributing & Support](#contributing--support)

---

<a id="what-is-cleo-musik"></a>

## ＼(＾ O ＾)／ What is Cleo Musik?

Cleo Musik is the ultimate minimalist Discord music bot—no ads, no premium tiers, no limits, just music and kawaii vibes!

- **No web UI**: Only simple slash commands.
- **100% free**: All features unlocked for everyone.
- **Unlimited playback**: Giant playlists, endless queues, eternal tunes!

**Supports YouTube, SoundCloud, Spotify, Deezer, Apple Music, Tidal, Amazon Music, direct audio links, and local files.**
Type `/play <url or query>` and let the music flow~

<a id="key-features"></a>

## (≧◡≦) Key Features

- Play from **8+ sources**: YouTube • SoundCloud • Spotify • Deezer • Apple Music • Tidal • Amazon Music • **Direct Audio Links** • **Local Files**
- Slash commands: `/play`, `/search`, `/pause`, `/skip`, `/queue`, `/remove`, + more!
- **Play Local Files**: Directly upload and play your own audio/video files.
- **Direct Audio Links**: Stream music directly from any audio URL (MP3, FLAC, WAV, etc.)
- **Autoplay** of similar tracks (YouTube Mix, SoundCloud Stations)
- **Loop** & **shuffle** controls
- **Kawaii Mode** toggles cute kaomoji responses (`/kaomoji`)
- Audio **filters**: slowed, reverb, bass boost, nightcore, and more
- Powered by `yt-dlp`, `FFmpeg`, `asyncio`, and a dash of chaos

<a id="installation"></a>

## (＾ ∀ ＾) Installation

You can run Cleo Musik in two ways. The Docker method is recommended for most users as it's simpler and manages all dependencies for you.

### (🐳) Method 1: Docker Setup (Recommended)

This is the easiest way to get the bot running.

1.  **Clone the repository and enter it:**
    ```bash
    git clone https://github.com/ihsanaminul/MusicBot.git
    cd MusicBot
    ```
2.  **Create your secret file:**
    Copy the example file to create your own configuration.
    ```bash
    cp .env.example .env
    ```
    Now, **edit the `.env` file** and fill in your tokens.
    ```ini
    DISCORD_TOKEN=your_discord_bot_token
    SPOTIFY_CLIENT_ID=your_spotify_client_id
    SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
    GENIUS_TOKEN=your_genius_api_token
    ```
3.  **Fire it up!**
    This command will build the container and run the bot in the background.
    ```bash
    docker compose up -d --build
    ```
    To view the bot's logs, use `docker compose logs -f`.

### (🛠️) Method 2: Manual Setup

**Requirements:**

- Python 3.9+
- FFmpeg installed & in your system's PATH
- Git

**Steps:**

1.  Clone the repo:
    ```bash
    git clone https://github.com/ihsanaminul/MusicBot.git
    cd MusicBot
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    playwright install
    ```
3.  Copy & configure environment:
    ```bash
    cp .env.example .env
    ```
    **Edit the `.env` file** with your tokens as shown in the Docker method.
4.  Run the bot:
    ```bash
    python playify.py
    ```

### Inviting the Bot to Discord (for both methods)

- Go to your Discord Developer Portal.
- Enable the **Guilds**, **Voice States**, and **Message Content** intents for your bot.
- Generate an invite link with the `Connect`, `Speak`, and `Send Messages` permissions.
- Add the bot to your server and enjoy `/play`!

---

<a id="command-reference"></a>

## (⊙‿⊙) Command Reference

| Command                  | Description                                                             |
| :----------------------- | :---------------------------------------------------------------------- |
| `/play <url/query>`      | Add a song or playlist from a link/search. Supports direct audio links! |
| `/search <query>`        | Searches for a song and lets you choose from the top results.           |
| `/play-files <file1...>` | Play one or more uploaded audio/video files.                            |
| `/playnext <query/file>` | Add a song or local file to the front of the queue.                     |
| `/pause`                 | Pause playback.                                                         |
| `/resume`                | Resume playback.                                                        |
| `/skip`                  | Skip the current track. Replays the song if loop is enabled.            |
| `/stop`                  | Stop playback, clear queue, and disconnect.                             |
| `/nowplaying`            | Display the current track's information.                                |
| `/seek`                  | Opens an interactive menu to seek, fast-forward, or rewind.             |
| `/queue`                 | Show the current song queue with interactive pages.                     |
| `/remove`                | Open a menu to remove specific songs from the queue.                    |
| `/shuffle`               | Shuffle the queue.                                                      |
| `/clearqueue`            | Clear all songs from the queue.                                         |
| `/loop`                  | Toggle looping for the current track.                                   |
| `/autoplay`              | Toggle autoplay of similar songs when the queue ends.                   |
| `/24_7 <mode>`           | Keep the bot in the channel (`normal`, `auto`, or `off`).               |
| `/filter`                | Apply real-time audio filters (nightcore, bassboost...).                |
| `/lyrics`                | Fetch and display lyrics for the current song.                          |
| `/karaoke`               | Start a karaoke session with synced lyrics.                             |
| `/reconnect`             | Refresh the voice connection to fix lag without losing your place.      |
| `/status`                | Show the bot's detailed performance and resource usage.                 |
| `/kaomoji`               | Toggle cute kaomoji responses. `(ADMIN)`                                |

<a id="troubleshooting"></a>

## (｀・ω・´) Troubleshooting

- **FFmpeg not found**: Ensure it's installed & in your system's PATH. (Docker setup handles this for you!)
- **Spotify errors**: Verify your API credentials in the `.env` file.
- **Bot offline/unresponsive**: Check your `DISCORD_TOKEN` and bot permissions in the Developer Portal.
- **Direct link issues**: Ensure the URL points directly to an audio file and is publicly accessible.

<a id="privacy--data"></a>

## (ﾉ ◕ ヮ ◕)ﾉ Privacy & Data

- **Self-hosted**: All logs are local to your machine. No telemetry is sent.
- Public instances: Minimal error logs are stored for debugging purposes only. No user data or analytics are collected.

<a id="contributing--support"></a>

## (ง ＾ ◡ ＾)ง Contributing & Support

- Fork the repo, open an issue or pull request—all contributions are welcome!
- Star the repository if you enjoy using Cleo Musik!
- For help and community discussions, please open an issue or start a discussion on GitHub.

<p align="center">
  Built with ☕ and love by <a href="https://github.com/ihsanaminul">ihsanaminul</a> (｡♥‿♥｡)
</p>
