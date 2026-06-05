import sys
sys.path.insert(0, '.')
from unittest.mock import AsyncMock, MagicMock
import asyncio

async def test():
    from sources.youtube import YouTubeSource
    import sources.player
    
    src = YouTubeSource('https://www.youtube.com/watch?v=test')
    
    # Patch on the actual module where BaseAudioPlayer is defined (sources.player)
    with patch('sources.player.BaseAudioPlayer.stop', new_callable=AsyncMock) as mock_stop:
        async with src:
            pass
    
    print('mock_stop.called:', mock_stop.called)

from unittest.mock import patch
asyncio.run(test())
