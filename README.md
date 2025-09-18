# 🎵 Enhanced Discord Music Bot

A robust, feature-rich Discord music bot optimized for unstable network connections with intelligent autoplay and multi-platform support.

## ✨ Features

### 🚀 Core Features
- **Multi-Platform Search**: Seamlessly integrates Spotify metadata with YouTube audio
- **Smart Autoplay**: AI-powered recommendations based on listening history
- **Network Resilience**: Built-in retry mechanisms and connection recovery
- **Queue Management**: Full queue control with persistent state
- **Voice Channel Intelligence**: Auto-disconnect and connection monitoring

### 🎯 Advanced Features
- **Dual-Source Integration**: Spotify track info + YouTube audio streaming
- **Enhanced Error Recovery**: Handles network timeouts and API failures gracefully
- **Automatic Cleanup**: Resource management and memory optimization
- **Volume Control**: Per-session volume adjustment
- **Connection Monitoring**: Smart voice channel management

## 🛠️ Tech Stack

- **Discord.py** - Discord API interaction
- **yt-dlp** - YouTube audio extraction
- **Spotipy** - Spotify Web API integration
- **FFmpeg** - Audio processing and streaming
- **asyncio** - Asynchronous operation handling

## 📋 Prerequisites (Windows)

### System Requirements
```powershell
# Install Python 3.8+ from https://python.org
# Make sure to check "Add Python to PATH" during installation

# Install FFmpeg (using chocolatey - recommended)
# First install chocolatey from https://chocolatey.org/install
choco install ffmpeg

# Alternative: Download FFmpeg manually
# 1. Download from https://ffmpeg.org/download.html#build-windows
# 2. Extract to C:\ffmpeg\
# 3. Add C:\ffmpeg\bin to your PATH environment variable
```

### Python Dependencies
```powershell
pip install discord.py yt-dlp spotipy python-dotenv aiohttp async-timeout PyNaCl
```

## ⚙️ Installation (Windows)

### 1. Clone Repository
```powershell
git clone https://github.com/yourusername/discord-music-bot.git
cd discord-music-bot
```

### 2. Create Virtual Environment
```powershell
# Create virtual environment
python -m venv musicbot-env

# Activate virtual environment
musicbot-env\Scripts\activate

# Your command prompt should now show (musicbot-env)
```

### 3. Install Dependencies
```powershell
# Make sure virtual environment is activated
pip install discord.py yt-dlp spotipy python-dotenv aiohttp async-timeout PyNaCl

# Or install from requirements file
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the root directory:
```env
# Discord Bot Token (Required)
DISCORD_TOKEN=your_discord_bot_token_here

# Spotify API Credentials (Optional but recommended)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

### 5. Discord Bot Setup
1. Visit the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application and bot
3. Copy the bot token to your `.env` file
4. Enable the following bot permissions:
   - Connect
   - Speak
   - Use Voice Activity
   - Send Messages
   - Embed Links
   - Read Message History

### 6. Spotify API Setup (Optional)
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy Client ID and Client Secret to your `.env` file

## 🚀 Usage

### Starting the Bot (Windows)
```powershell
# Make sure virtual environment is activated
musicbot-env\Scripts\activate

# Run the bot
python main.py
```

### Basic Commands

#### Playback Controls
```bash
!play <song name>              # Search and play a song
!play <youtube_url>            # Play from YouTube URL
!play <spotify_url>            # Play from Spotify URL (requires API)
!pause                         # Pause current song
!resume                        # Resume playback
!skip                          # Skip current song
!stop                          # Stop and clear queue
```

#### Queue Management
```bash
!queue                         # Show current queue
!nowplaying                    # Show current song info
!clear                         # Clear the queue
```

#### Advanced Features
```bash
!volume <0-200>                # Adjust volume (100 = normal)
!autoplay on/off               # Toggle smart recommendations
!disconnect                    # Leave voice channel
!help                          # Show all commands
```

### Example Usage
```bash
# Search for a song
!play Shape of You Ed Sheeran

# Play from Spotify
!play https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3

# Play from YouTube
!play https://www.youtube.com/watch?v=JGwWNGJdvx8

# Enable autoplay for continuous music
!autoplay on
```

## 🎵 How It Works

### Smart Search Algorithm
1. **Spotify Integration**: Fetches rich metadata (title, artist, album art, duration)
2. **YouTube Matching**: Finds corresponding audio stream on YouTube
3. **Fallback System**: Direct YouTube search if Spotify fails
4. **Quality Optimization**: Selects best available audio quality

### Autoplay Intelligence
- Analyzes listening history and preferences
- Generates contextual recommendations via Spotify API
- Falls back to YouTube-based suggestions
- Maintains recommendation history to avoid repeats
- Filters by duration to maintain flow

### Network Resilience
- **Retry Mechanisms**: Automatic retry with exponential backoff
- **Connection Recovery**: Handles disconnections gracefully
- **Timeout Management**: Prevents hanging operations
- **Resource Cleanup**: Automatic cleanup of failed connections

## 📁 Project Structure

```
discord-music-bot/
├── musicbot-env/            # Virtual environment (auto-created)
├── main.py                  # Main bot file
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables
├── .env.example            # Environment template
├── README.md               # This file
├── .gitignore             # Git ignore rules
├── libopus.dll           # Opus codec library (Windows)
├── bot.log               # Bot logs (auto-created)
└── .local/               # Cache directory (auto-created)
```

## 🔧 Configuration Options

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `SPOTIFY_CLIENT_ID` | No | Spotify API client ID |
| `SPOTIFY_CLIENT_SECRET` | No | Spotify API client secret |

### Bot Settings
- **Default Volume**: 50%
- **Queue Limit**: Unlimited
- **Autoplay Duration Filter**: 5 minutes max
- **Connection Timeout**: 15 seconds
- **Auto-disconnect**: After 15 minutes of inactivity

## 🚨 Troubleshooting (Windows)

### Common Issues

#### "FFmpeg not found" or "Executable not found"
```powershell
# Option 1: Install via Chocolatey (recommended)
choco install ffmpeg

# Option 2: Manual installation
# 1. Download FFmpeg from https://ffmpeg.org/download.html#build-windows
# 2. Extract to C:\ffmpeg\
# 3. Add C:\ffmpeg\bin to PATH:
#    - Open System Properties > Environment Variables
#    - Edit PATH variable
#    - Add C:\ffmpeg\bin
#    - Restart Command Prompt
```

#### "Opus library not loaded"
```powershell
# Install PyNaCl in virtual environment
musicbot-env\Scripts\activate
pip install PyNaCl

# If still fails, download libopus.dll manually
# Place libopus.dll in the same directory as main.py
```

#### "Virtual environment not recognized"
```powershell
# Make sure to activate virtual environment before running
musicbot-env\Scripts\activate

# Check if activated - prompt should show (musicbot-env)
```

#### Bot not responding
1. Check bot token validity in `.env` file
2. Verify bot permissions in Discord server
3. Check Command Prompt for error messages
4. Ensure virtual environment is activated
5. Restart the bot: `Ctrl+C` then `python main.py`

#### "Module not found" errors
```powershell
# Activate virtual environment first
musicbot-env\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Performance Optimization (Windows)
- Use SSD storage for better audio caching
- Ensure stable internet connection
- Close unnecessary applications to free RAM
- Run Command Prompt as Administrator if needed
- Regular bot restarts for long-running instances

### Windows-Specific Notes
- Use PowerShell or Command Prompt as Administrator for better compatibility
- Windows Defender may flag the bot - add exception if needed
- Firewall may block connections - allow Python through Windows Firewall
- Path separators use backslash (`\`) in Windows commands

## 🤝 Contributing

### Development Setup (Windows)
```powershell
# Clone and setup
git clone https://github.com/yourusername/discord-music-bot.git
cd discord-music-bot

# Create and activate virtual environment
python -m venv musicbot-env
musicbot-env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and test
python main.py

# Submit pull request
```

### Contribution Guidelines
- Follow PEP 8 style guidelines
- Add docstrings to new functions
- Include error handling for new features
- Test with various network conditions
- Update documentation for new commands

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This bot is for educational and personal use only. Please respect YouTube's Terms of Service and Spotify's API Terms of Use. The developers are not responsible for any misuse of this software.

## 🙏 Acknowledgments

- **Discord.py** community for excellent documentation
- **yt-dlp** developers for robust video extraction
- **Spotify** for providing comprehensive music metadata API
- **FFmpeg** team for powerful audio processing capabilities

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/discord-music-bot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/discord-music-bot/discussions)
- **Documentation**: [Wiki](https://github.com/yourusername/discord-music-bot/wiki)

---

<div align="center">

**⭐ Star this repository if you found it helpful!**

Made with ❤️ for the Discord community

</div>