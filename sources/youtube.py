"""Source adapter for streaming audio from YouTube via yt-dlp."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError, UnavailableVideoError as YtDlpUnavailableError

from .audio_source import (
    AudioSource,
    AudioSourceState,
    CodecInfo,
)
from .player import BaseAudioPlayer, FFmpegConfig, StreamState

logger = logging.getLogger(__name__)


# Mapping from yt-dlp error codes to friendly exception types.
class YouTubeUnavailableError(Exception):
    """Video is unavailable (takedown, private, region-locked, etc.)."""

    pass


class YouTubeDownloadError(Exception):
    """A network or download-level failure with yt-dlp."""

    pass


@dataclass
class VideoMetadata:
    """Extracted metadata from a YouTube video.

    Attributes:
        title: Video title.
        author: Video uploader / channel name.
        duration_seconds: Duration of the video in seconds, or None if unknown.
        thumbnail_url: URL to the thumbnail image, or None.
        stream_url: Direct stream URL resolved by yt-dlp.
        format_id: yt-dlp format ID selected for playback.
    """

    title: str = ""
    author: str = ""
    duration_seconds: Optional[float] = None
    thumbnail_url: Optional[str] = None
    stream_url: str = ""
    format_id: str = ""


class YouTubeSource(AudioSource):
    """Audio source that streams audio from YouTube using yt-dlp.

    Resolves a YouTube URL into a direct audio stream and exposes
    video metadata (title, author, duration).  Playback is delegated
    to an internal ``BaseAudioPlayer`` backed by FFmpeg.

    Error handling:
        - **Unavailable / private videos** raise ``YouTubeUnavailableError``.
        - **Network errors** raise ``YouTubeDownloadError``.
        - Both subclasses of ``Exception``, so callers can choose how broad
          their catch-clause should be.

    Example usage::

        source = YouTubeSource("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        await source.play()
        print(source.title)   # "Rick Astley - Never Gonna Give You Up"
        print(source.duration)  # 212.0
    """

    def __init__(
        self,
        url: str,
        *,
        format: Optional[str] = "bestaudio",  # noqa: A002
        audio_format_options: Optional[dict[str, Any]] = None,
        player: Optional[BaseAudioPlayer] = None,
    ) -> None:
        super().__init__()
        self.url = url
        self._format = format
        self._audio_format_options = audio_format_options or {}
        self._metadata: VideoMetadata = VideoMetadata()

        if player is not None:
            self._player = player
        else:
            self._player = BaseAudioPlayer(
                config=FFmpegConfig(
                    output_format="s16le",
                    sample_rate=48000,
                    channels=2,
                    input_source=self.url,
                )
            )

    # -- Public accessors (metadata) -----------------------------------------

    @property
    def title(self) -> str:
        """Video title."""
        return self._metadata.title

    @property
    def author(self) -> str:
        """Video uploader / channel name."""
        return self._metadata.author

    # -- AudioSource abstract method implementation --------------------------

    async def play(self) -> None:
        """Start playing audio from the YouTube URL.

        1. Uses yt-dlp to resolve a direct stream URL and fetch metadata.
        2. Configures the internal ``BaseAudioPlayer`` with the stream.
        3. Starts playback.

        Raises:
            YouTubeUnavailableError: Video is unavailable, private, region-locked, etc.
            YouTubeDownloadError: Network-level failure (e.g. cannot resolve URL).
        """
        if self._state != AudioSourceState.IDLE:
            raise RuntimeError(
                f"Cannot play YouTubeSource in state {self._state.value}; "
                f"expected IDLE."
            )

        try:
            info = await asyncio.get_running_loop().run_in_executor(
                None, self._extract_info
            )
        except YtDlpDownloadError as exc:
            # Covers network failures, invalid URLs, format selection errors, etc.
            logger.error("YouTubeDownloadError for %s: %s", self.url, exc)
            self._set_state(AudioSourceState.ERROR)
            raise YouTubeDownloadError(str(exc)) from exc
        except YtDlpUnavailableError as exc:
            # Private, region-locked, takedown, etc.
            logger.warning("YouTubeUnavailableError for %s: %s", self.url, exc)
            self._set_state(AudioSourceState.ERROR)
            raise YouTubeUnavailableError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected yt-dlp error for %s: %s", self.url, exc)
            self._set_state(AudioSourceState.ERROR)
            raise YouTubeDownloadError(
                f"Failed to extract stream info: {exc}"
            ) from exc

        # Populate metadata
        self._metadata = VideoMetadata(
            title=info.get("title", ""),
            author=info.get("uploader", info.get("author", "")),
            duration_seconds=float(info.get("duration", 0)) if info.get("duration") else None,
            thumbnail_url=info.get("thumbnail"),
            stream_url=info.get("url", self.url),
            format_id=info.get("format_id", ""),
        )

        # Update CodecInfo
        audio_ext = (info.get("ext") or "m4a").lower()
        self._codec_info = CodecInfo(
            codec_name=audio_ext,
            sample_rate=int(info.get("filesize", 0)) if info.get("acodec") else 48000,
            channels=self._player.config.channels if self._player.config else 2,
            duration_seconds=self._metadata.duration_seconds,
        )

        # Set the stream URL as input for the player
        if self._player:
            self._player.config.input_source = info.get("url", self.url)

        # Propagate duration to parent AudioSource state
        self._duration = self._metadata.duration_seconds

        try:
            await self._player.play()
        except Exception as exc:
            self._set_state(AudioSourceState.ERROR)
            raise YouTubeDownloadError(
                f"Failed to start playback: {exc}"
            ) from exc

        self._set_state(AudioSourceState.PLAYING)

    async def pause(self) -> None:
        """Pause the current playback."""
        if self._state != AudioSourceState.PLAYING:
            raise RuntimeError(
                f"Cannot pause YouTubeSource in state {self._state.value}; "
                f"expected PLAYING."
            )
        await self._player.pause()
        self._set_state(AudioSourceState.PAUSED)

    async def resume(self) -> None:
        """Resume the current playback."""
        if self._state != AudioSourceState.PAUSED:
            raise RuntimeError(
                f"Cannot resume YouTubeSource in state {self._state.value}; "
                f"expected PAUSED."
            )
        await self._player.resume()
        self._set_state(AudioSourceState.PLAYING)

    async def stop(self) -> None:
        """Stop playback and reset to IDLE."""
        if self._state == AudioSourceState.IDLE:
            return  # already stopped, idempotent
        await self._player.stop()
        self._set_state(AudioSourceState.IDLE)

    # -- Internal helpers ----------------------------------------------------

    def _extract_info(self) -> dict:
        """Extract video info via yt-dlp (runs in executor thread)."""
        ydl_opts = {
            "format": self._format,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": "-",  # we don't write to disk
        }
        if self._audio_format_options:
            ydl_opts["format_options"] = self._audio_format_options

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if not info:
                raise YtDlpUnavailableError(
                    f"yt-dlp returned empty result for {self.url}"
                )
            # For playlist URLs, get the first item.
            if info.get("entries"):
                info = info["entries"][0]
            return info

    async def __aenter__(self) -> "YouTubeSource":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
