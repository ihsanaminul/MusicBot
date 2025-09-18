# Discord Music Bot

## Overview

This is a Discord music bot built with Python that provides music streaming capabilities from YouTube and Spotify integration. The bot allows users to play, queue, and control music playback in Discord voice channels. It uses yt-dlp for YouTube audio extraction, discord.py for Discord API interaction, and Spotipy for Spotify playlist/track integration.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Bot Framework
- **Discord.py Framework**: Built on discord.py 2.3.2 with command extension for structured command handling
- **Command Prefix**: Uses '!' as the command prefix for bot interactions
- **Intents Configuration**: Configured with message content intents to read and respond to user commands
- **Error Handling**: Implements reconnection capabilities and comprehensive logging system

### Audio Processing Pipeline
- **YouTube Audio Extraction**: Uses yt-dlp (YouTube-DL successor) for downloading and extracting audio from YouTube videos
- **FFmpeg Integration**: Leverages FFmpeg for audio processing and streaming optimization with reconnection and buffering options
- **Audio Format Optimization**: Configured to extract best available audio quality while maintaining performance

### Music Queue Management
- **Deque-based Queue System**: Implements a double-ended queue (deque) for efficient music queue operations
- **Asynchronous Processing**: Uses asyncio for non-blocking audio operations and concurrent request handling
- **Session Management**: Maintains playback state and queue persistence during bot operation

### Configuration Management
- **Environment Variables**: Uses python-dotenv for secure configuration management
- **Logging System**: Comprehensive logging setup with both file and console output
- **Error Recovery**: Implements reconnection logic and error handling for network interruptions

### Audio Streaming Architecture
- **Optimized Streaming**: FFmpeg configured with reconnection parameters and buffer optimization
- **Network Resilience**: Includes retry mechanisms and connection recovery for unstable network conditions
- **Performance Tuning**: Audio format selection prioritizes compatibility and streaming efficiency

## External Dependencies

### Music Services Integration
- **Spotify API**: Integrated via Spotipy library for playlist and track metadata retrieval
- **YouTube**: Primary audio source through yt-dlp for content extraction and streaming

### Core Libraries
- **Discord.py**: Official Discord API wrapper for bot functionality
- **yt-dlp**: YouTube content extraction and audio processing
- **Spotipy**: Spotify Web API client for music metadata
- **aiohttp**: Asynchronous HTTP client for API requests
- **PyNaCl**: Voice connection encryption and audio processing

### System Dependencies
- **FFmpeg**: External binary required for audio processing and streaming
- **Python Environment**: Requires Python with asyncio support for concurrent operations

### Authentication Requirements
- **Discord Bot Token**: Required for Discord API access and bot authentication
- **Spotify Credentials**: Client ID and Client Secret for Spotify API integration
- **Environment Configuration**: Secure storage of API credentials via .env file