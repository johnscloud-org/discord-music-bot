# discord-music-bot

Discord music bot with YouTube and local file streaming support.

## Features

- Stream audio from **YouTube** using yt-dlp
- Stream from **local files** (.mp3, .wav)
- Core audio playback abstraction (AudioSource) for easy source adapter extension
- Async FFmpeg-backed player for PCM audio output to Discord voice library

## Project Structure

    bot/            # Discord bot entry point and slash commands
    sources/        # Audio source adapters
      audio_source.py   # AudioSource ABC (abstract base class)
      youtube.py        # YouTube streaming adapter
      local_file.py     # Local file streaming adapter
    tests/          # Unit tests

## Quick Start

    from sources.youtube import YouTubeSource
    
    source = YouTubeSource("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    await source.play()
    print(f"Now playing: {source.title} by {source.author}")

## Architecture

The bot uses an AudioSource abstract base class that defines the contract for all audio sources. Each source adapter (YouTube, local file, etc.) implements this interface and delegates to BaseAudioPlayer which manages the FFmpeg subprocess for PCM audio streaming.

## Running Tests

    cd tests
    python -m unittest test_youtube_source -v
