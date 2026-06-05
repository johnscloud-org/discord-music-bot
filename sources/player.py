"""FFmpeg-backed audio player for Discord voice streaming."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FFmpegConfig:
    """Configuration for the FFmpeg subprocess.

    Attributes:
        input_source: Input URI or file path (e.g., 'https://...stream' or '/path/to/file.mp3').
        output_format: Audio sample format (e.g., 's16le' for PCM signed 16-bit little-endian).
        sample_rate: Output sample rate in Hz.
        channels: Number of audio channels (1 = mono, 2 = stereo).
        buffer_size: Internal buffer size in bytes.
    """

    input_source: str = ""
    output_format: str = "s16le"
    sample_rate: int = 48000
    channels: int = 2
    buffer_size: int = field(default=65536)

    def build_cli_args(self) -> list[str]:
        """Build FFmpeg command-line arguments for PCM output.

        Returns:
            List of CLI arguments including the input source and PCM pipe config.
        """
        return [
            "-i", self.input_source,
            "-f", self.output_format,
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            "pipe:1",
        ]


class FFmpegError(Exception):
    """Raised when the FFmpeg process encounters an error."""

    pass


class StreamState:
    """Non-enum stream state holder (mutable, comparable)."""

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class BaseAudioPlayer:
    """Manages an FFmpeg subprocess for PCM audio streaming.

    The player creates an async FFmpeg process that reads from the configured
    input source and writes raw PCM to ``pipe:1``. A background read loop
    drains the pipe in chunks.

    Lifecycle (managed externally via AudioSource):
        - ``play()`` starts the FFmpeg subprocess and launches the read loop.
        - ``pause()`` pauses audio by stopping the read loop without killing FFmpeg.
        - ``resume()`` restarts the read loop.
        - ``stop()`` kills the FFmpeg process and cleans up resources.

    Context manager support is provided via ``__aenter__``/``__aexit__``.
    """

    def __init__(self, config: Optional[FFmpegConfig] = None) -> None:
        self.config = config or FFmpegConfig()
        self._process: asyncio.subprocess.Process | None = None
        self._state: str = StreamState.IDLE
        self._reader_task: asyncio.Task | None = None
        self._buffer_size = self.config.buffer_size

    # -- State ---------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    # -- Public API ----------------------------------------------------------

    async def play(self) -> None:
        """Start the FFmpeg subprocess and begin PCM reading."""
        if self._state != StreamState.IDLE:
            raise RuntimeError(
                f"Cannot start playback in state {self._state}"
            )

        args = self.config.build_cli_args()
        logger.info("Starting FFmpeg with args: %s", args)

        self._process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        self._state = StreamState.PLAYING
        logger.info("FFmpeg process started (pid=%s)", self._process.pid)

    async def pause(self) -> None:
        """Pause audio by halting the read loop."""
        if self._state != StreamState.PLAYING:
            raise RuntimeError(f"Cannot pause in state {self._state}")
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._state = StreamState.PAUSED

    async def resume(self) -> None:
        """Resume audio by restarting the read loop."""
        if self._state != StreamState.PAUSED:
            raise RuntimeError(f"Cannot resume in state {self._state}")
        self._reader_task = asyncio.create_task(self._read_loop())
        self._state = StreamState.PLAYING

    async def stop(self) -> None:
        """Kill the FFmpeg process and clean up."""
        if self._state == StreamState.IDLE or self._state == StreamState.STOPPED:
            return

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._reader_task = None

        # Kill FFmpeg process
        if self._process and self._process.returncode is None:
            self._process.kill()
            try:
                await self._process.wait()
            except ProcessLookupError:
                pass  # already dead
        self._state = StreamState.STOPPED
        self._process = None

    # -- Context manager -----------------------------------------------------

    async def __aenter__(self) -> "BaseAudioPlayer":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # -- Internal helpers ----------------------------------------------------

    async def _read_loop(self) -> None:
        """Background task that reads PCM data from FFmpeg stdout."""
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                chunk = await asyncio.wait_for(
                    self._process.stdout.read(self._buffer_size),
                    timeout=30.0,
                )
                if not chunk:
                    break  # EOF or error
                # In a real implementation, this would feed PCM data to
                # the Discord voice library (e.g., opus encoder).
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("PCM read loop error: %s", exc)
            if self._state != StreamState.STOPPED:
                self._state = StreamState.IDLE
