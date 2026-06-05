"""Simpler debug."""
import asyncio, sys
sys.path.insert(0, '.')

from unittest.mock import AsyncMock, patch

async def test():
    from sources.youtube import YouTubeSource
    
    src = YouTubeSource('https://www.youtube.com/watch?v=test')
    
    # Patch directly on the instance
    mock_stop = AsyncMock()
    src._player.stop = mock_stop
    
    async with src:
        print('Inside context, called:', mock_stop.called)
    
    print('After async with, called:', mock_stop.called)

asyncio.run(test())
