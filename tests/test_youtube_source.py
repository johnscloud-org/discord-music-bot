"""Tests for the YouTubeSource class."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add workspace root to Python path so `sources` package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.version_info >= (3, 8):
    _TestCase = unittest.IsolatedAsyncioTestCase
else:
    _TestCase = unittest.TestCase


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_mock_info(url: str = "https://example.com/stream") -> dict:
    """Return a minimal yt-dlp extract_info result."""
    return {
        "title": "Test Video",
        "uploader": "Test Artist",
        "duration": 210,
        "thumbnail": "https://img.example.com/thumb.jpg",
        "url": url,
        "format_id": "251",
        "ext": "webm",
        "acodec": "opus",
    }


def _make_mock_playlist_info() -> dict:
    """Return a yt-dlp result that looks like a playlist."""
    entry = _make_mock_info()
    return {
        "title": "Playlist Title",
        "entries": [entry],
    }


# ---------------------------------------------------------------------------
# YouTubeSource construction tests
# ---------------------------------------------------------------------------

class TestYouTubeSourceInit(unittest.TestCase):
    """Tests for YouTubeSource construction."""

    def test_default_init(self):
        from sources.youtube import YouTubeSource, BaseAudioPlayer

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        self.assertEqual(src.url, "https://www.youtube.com/watch?v=test")
        self.assertEqual(src._format, "bestaudio")
        self.assertEqual(src._state.value, "idle")
        self.assertIsInstance(src._player, BaseAudioPlayer)

    def test_custom_format(self):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test", format="m4a")
        self.assertEqual(src._format, "m4a")

    def test_custom_audio_options(self):
        from sources.youtube import YouTubeSource

        opts = {"acodec": "aac"}
        src = YouTubeSource(
            "https://www.youtube.com/watch?v=test",
            audio_format_options=opts,
        )
        self.assertEqual(src._audio_format_options, opts)

    def test_custom_player(self):
        from sources.youtube import YouTubeSource
        from sources.player import BaseAudioPlayer

        player = BaseAudioPlayer()
        src = YouTubeSource("https://www.youtube.com/watch?v=test", player=player)
        self.assertIs(src._player, player)

    def test_default_title_is_empty(self):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        self.assertEqual(src.title, "")
        self.assertEqual(src.author, "")


# ---------------------------------------------------------------------------
# Successful playback tests
# ---------------------------------------------------------------------------

class TestYouTubeSourcePlaySuccess(_TestCase, unittest.TestCase):
    """Tests for successful YouTube stream playback."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_sets_state_to_playing(self, MockYoutubeDL):
        from sources.audio_source import AudioSourceState
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        self.assertEqual(src._state, AudioSourceState.PLAYING)

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_populates_metadata(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        self.assertEqual(src._metadata.title, "Test Video")
        self.assertEqual(src._metadata.author, "Test Artist")
        self.assertEqual(src._metadata.duration_seconds, 210.0)
        self.assertEqual(
            src._metadata.thumbnail_url, "https://img.example.com/thumb.jpg"
        )

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_calls_ytdlp_extract_info(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        MockYoutubeDL.assert_called_once()
        call_kwargs = MockYoutubeDL.call_args
        ydl_opts = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]
        self.assertIn("format", ydl_opts)
        self.assertTrue(ydl_opts.get("quiet"))

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_uses_custom_format(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource(
            "https://www.youtube.com/watch?v=test",
            format="m4a",
        )
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        call_kwargs = MockYoutubeDL.call_args
        ydl_opts = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]
        self.assertEqual(ydl_opts["format"], "m4a")

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_uses_audio_format_options(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource(
            "https://www.youtube.com/watch?v=test",
            audio_format_options={"acodec": "aac"},
        )
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        call_kwargs = MockYoutubeDL.call_args
        ydl_opts = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]
        self.assertIn("format_options", ydl_opts)
        self.assertEqual(ydl_opts["format_options"]["acodec"], "aac")

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_handles_playlist_url(self, MockYoutubeDL):
        """Playlist URLs should resolve to the first entry."""
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_playlist_info()

        src = YouTubeSource("https://www.youtube.com/playlist?list=PLtest")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        self.assertEqual(src.title, "Test Video")
        self.assertEqual(src._metadata.title, "Test Video")

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_calls_player_play(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock) as mock_play:
            await src.play()

        mock_play.assert_called_once()

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_metadata_property_accessors(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        self.assertEqual(src.title, "Test Video")
        self.assertEqual(src.author, "Test Artist")
        self.assertIsNotNone(src.duration)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestYouTubeSourcePlayErrors(_TestCase, unittest.TestCase):
    """Tests for error handling during play()."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_player_play_failure_raises_download_error(self, MockYoutubeDL):
        from sources.youtube import YouTubeDownloadError, YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch(
            "sources.youtube.BaseAudioPlayer.play",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ffmpeg: codec not supported"),
        ):
            with self.assertRaises(YouTubeDownloadError) as ctx:
                await src.play()

            self.assertIn("Failed to start playback", str(ctx.exception))

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_player_play_failure_sets_state_to_error(self, MockYoutubeDL):
        from sources.audio_source import AudioSourceState
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch(
            "sources.youtube.BaseAudioPlayer.play",
            new_callable=AsyncMock,
            side_effect=RuntimeError("codec error"),
        ):
            try:
                await src.play()
            except Exception:
                pass

        self.assertEqual(src._state, AudioSourceState.ERROR)


# ---------------------------------------------------------------------------
# State guard tests
# ---------------------------------------------------------------------------

class TestYouTubeStateGuards(_TestCase, unittest.TestCase):
    """Tests for state machine guards."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_play_twice_raises_runtime_error(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test1")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        with self.assertRaises(RuntimeError):
            await src.play()

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_pause_without_playing_raises(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with self.assertRaises(RuntimeError):
            await src.pause()

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_resume_without_pausing_raises(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with self.assertRaises(RuntimeError):
            await src.resume()


# ---------------------------------------------------------------------------
# Pause/Resume lifecycle tests
# ---------------------------------------------------------------------------

class TestYouTubePauseResume(_TestCase, unittest.TestCase):
    """Tests for pause/resume lifecycle."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_pause_transitions_state(self, MockYoutubeDL):
        from sources.audio_source import AudioSourceState
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            await src.play()

        with patch.object(src, "_player") as mock_player:
            mock_player.pause = AsyncMock()
            await src.pause()

        self.assertEqual(src._state, AudioSourceState.PAUSED)


# ---------------------------------------------------------------------------
# Stop idempotency tests
# ---------------------------------------------------------------------------

class TestStopIdempotent(_TestCase, unittest.TestCase):
    """Tests for stop() idempotency."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_stop_when_already_idle_succeeds(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        # Already IDLE - should silently succeed
        await src.stop()
        await src.stop()  # Again, still OK


# ---------------------------------------------------------------------------
# Context manager tests
# ---------------------------------------------------------------------------

class TestYouTubeContextManager(_TestCase, unittest.TestCase):
    """Tests for context manager (async with) support."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_context_manager_returns_source(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            async with src as s:
                self.assertIs(s, src)

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_context_manager_calls_stop_on_exit(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        MockYoutubeDL.return_value.__enter__.return_value.extract_info.return_value = _make_mock_info()

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with patch("sources.youtube.BaseAudioPlayer.play", new_callable=AsyncMock):
            # Need to play first so state is not IDLE (YouTubeSource.stop() returns early when IDLE)
            await src.play()
        
        mock_stop = AsyncMock()
        src._player.stop = mock_stop
        
        async with src:
            pass  # already playing, context manager should call stop on exit

        # stop should be called on __aexit__
        mock_stop.assert_called()


# ---------------------------------------------------------------------------
# seek_to validation tests
# ---------------------------------------------------------------------------

class TestSeekTo(_TestCase, unittest.TestCase):
    """Tests for seek_to validation."""

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_seek_negative_raises(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        with self.assertRaises(ValueError):
            await src.seek_to(-1.0)

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_seek_beyond_duration_raises(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        src._duration = 210.0
        with self.assertRaises(ValueError):
            await src.seek_to(300.0)

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_seek_within_range_works(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        src._duration = 210.0
        await src.seek_to(100.0)
        self.assertEqual(src.position, 100.0)

    @patch("sources.youtube.yt_dlp.YoutubeDL")
    async def test_seek_at_duration_works(self, MockYoutubeDL):
        from sources.youtube import YouTubeSource

        src = YouTubeSource("https://www.youtube.com/watch?v=test")
        src._duration = 210.0
        await src.seek_to(210.0)
        self.assertEqual(src.position, 210.0)


# ---------------------------------------------------------------------------
# AudioSourceState enum tests
# ---------------------------------------------------------------------------

class TestAudioSourceStateEnum(unittest.TestCase):
    """Tests for AudioSourceState enum values."""

    def test_enum_values(self):
        from sources.audio_source import AudioSourceState

        states = {s.value for s in AudioSourceState}
        expected = {"idle", "playing", "paused", "stopped", "error"}
        self.assertEqual(states, expected)


# ---------------------------------------------------------------------------
# FFmpegError and stream state tests
# ---------------------------------------------------------------------------

class TestFFmpegErrorType(unittest.TestCase):
    """Tests for FFmpegError being a proper Exception."""

    def test_is_exception(self):
        from sources.player import FFmpegError
        self.assertTrue(issubclass(FFmpegError, Exception))


class TestStreamStateConstants(unittest.TestCase):
    """Tests for StreamState constants."""

    def test_state_values(self):
        from sources.player import StreamState
        states = {StreamState.IDLE, StreamState.PLAYING, StreamState.PAUSED, StreamState.STOPPED}
        self.assertEqual(states, {"idle", "playing", "paused", "stopped"})


class TestFFmpegConfigDefaults(unittest.TestCase):
    """Tests for FFmpegConfig default values."""

    def test_default_output_format(self):
        from sources.player import FFmpegConfig
        cfg = FFmpegConfig()
        self.assertEqual(cfg.output_format, "s16le")

    def test_default_sample_rate(self):
        from sources.player import FFmpegConfig
        cfg = FFmpegConfig()
        self.assertEqual(cfg.sample_rate, 48000)

    def test_default_channels(self):
        from sources.player import FFmpegConfig
        cfg = FFmpegConfig()
        self.assertEqual(cfg.channels, 2)


class TestFFmpegConfigCLIArgs(unittest.TestCase):
    """Tests for FFmpegConfig.build_cli_args."""

    def test_build_cli_args_contains_input_and_pipe(self):
        from sources.player import FFmpegConfig
        cfg = FFmpegConfig(input_source="https://example.com/stream")
        args = cfg.build_cli_args()
        self.assertIn("-i", args)
        idx = args.index("-i")
        self.assertEqual(args[idx + 1], "https://example.com/stream")
        self.assertIn("pipe:1", args)

    def test_build_cli_args_includes_format_and_rates(self):
        from sources.player import FFmpegConfig
        cfg = FFmpegConfig()
        args = cfg.build_cli_args()
        self.assertIn("-ar", args)
        idx = args.index("-ar")
        self.assertEqual(args[idx + 1], "48000")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
