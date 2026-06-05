"""Core audio source abstraction for the Discord music bot."""

from __future__ import annotations

import asyncio
import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AudioSourceState(enum.Enum):
    """State of an audio source lifecycle."""

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class CodecInfo:
    """Codec/format information about a loaded stream.

    Attributes:
        codec_name: Name of the audio codec (e.g., 'pcm_s16le').
        sample_rate: Sample rate in Hz.
        channels: Number of audio channels.
        duration_seconds: Total duration, or None if unknown.
    """

    codec_name: str = "pcm_s16le"
    sample_rate: int = 48000
    channels: int = 2
    duration_seconds: Optional[float] = None


class FFmpegError(Exception):
    """Raised when FFmpeg encounters an error."""

    pass


class AudioSource(ABC):
    """Abstract base class for audio sources.

    Subclasses must implement `play()`, `pause()`, `resume()`, and `stop()`
    along with the `position`, `duration`, and `codec_info` properties.

    The lifecycle state machine is:
        IDLE  --play-->  PLAYING  --pause-->  PAUSED
         ^  |             |                              |
         |  +-------------+<--resume---------------------+
         |
         +---stop----------------------------------------+

    All state transitions that cannot be performed in the current state
    should raise a ``RuntimeError`` with a descriptive message.
    """

    def __init__(self) -> None:
        self._state: AudioSourceState = AudioSourceState.IDLE
        self._duration: Optional[float] = None
        self._position: float = 0.0
        self._codec_info: CodecInfo = CodecInfo()
        self._player: BaseAudioPlayer | None = None

    @property
    def state(self) -> AudioSourceState:
        """Current playback state."""
        return self._state

    @property
    def position(self) -> float:
        """Current playback position in seconds."""
        return self._position

    @property
    def duration(self) -> Optional[float]:
        """Total duration of the stream in seconds, or None if unknown."""
        return self._duration

    @property
    def codec_info(self) -> CodecInfo:
        """Codec/format information for this source."""
        return self._codec_info

    @property
    def is_playing(self) -> bool:
        return self._state == AudioSourceState.PLAYING

    @abstractmethod
    async def play(self) -> None:
        """Start playing the audio source.

        Resolves the stream URI, fetches metadata, and starts playback.
        Transitions state from IDLE to PLAYING.
        """
        ...

    @abstractmethod
    async def pause(self) -> None:
        """Pause playback. Only valid when in PLAYING state."""
        ...

    @abstractmethod
    async def resume(self) -> None:
        """Resume playback. Only valid when in PAUSED state."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop playback and reset to IDLE state."""
        ...

    async def seek_to(self, offset: float) -> None:
        """Seek to a position in the stream.

        Args:
            offset: Target position in seconds. Must be >= 0 and <= duration.

        Raises:
            ValueError: If offset is negative or beyond the stream duration.
        """
        if offset < 0:
            raise ValueError(f"Seek offset must be non-negative, got {offset}")
        if self._duration is not None and offset > self._duration:
            raise ValueError(
                f"Seek offset {offset} exceeds duration {self._duration}"
            )
        self._position = offset

    def _set_state(self, new_state: AudioSourceState) -> None:
        """Internal state setter with logging."""
        old_state = self._state
        self._state = new_state
        logger.debug("AudioSource state transition: %s -> %s", old_state.value, new_state.value)
