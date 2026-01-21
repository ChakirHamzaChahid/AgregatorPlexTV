import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.asyncio
async def test_stream_video_direct_play_priority():
    # On mock le client HTTPX interne
    with patch("app.main.http_client.get", new_callable=AsyncMock) as mock_get, \
         patch("app.main.http_client.stream", new_callable=AsyncMock) as mock_stream:
        
        # Scénario : 
        # 1. Le test de Direct Play renvoie 400 (Refusé)
        # 2. Le fallback (Transcode) est alors tenté
        
        # Premier appel (Direct Play) échoue, Second appel (Transcode) réussit
        mock_stream.return_value.__aenter__.side_effect = [
            AsyncMock(status_code=400), # Direct Play Fail
            AsyncMock(status_code=200, aiter_bytes=AsyncMock(return_value=[b"chunk_video"])) # Transcode Success
        ]

        # Appel API
        with TestClient(app) as client:
            response = client.get("/vlc-stream/session123?server=http://plex:32400&path=/key&token=xyz")
            
            # On consomme le stream pour déclencher la logique
            list(response.iter_bytes())

        # Vérifications
        assert mock_stream.call_count == 2 # On a bien tenté les deux
        
        # Premier appel = Direct Play
        call_args_1 = mock_stream.call_args_list[0][1]['params']
        assert call_args_1['directPlay'] == 1
        
        # Second appel = Transcode (directPlay=0)
        call_args_2 = mock_stream.call_args_list[1][1]['params']
        assert call_args_2['directPlay'] == 0

@pytest.mark.asyncio
async def test_stream_video_with_offset():
    """Vérifie que le paramètre offset est correctement transmis."""
    with patch("app.main.http_client.stream", new_callable=AsyncMock) as mock_stream:
        
        # Le stream réussit du premier coup (Opti)
        mock_stream.return_value.__aenter__.return_value.status_code = 200
        mock_stream.return_value.__aenter__.return_value.aiter_bytes = AsyncMock(return_value=[b"video_data"])

        with TestClient(app) as client:
            # On appelle avec un offset de 120 secondes
            response = client.get("/vlc-stream/session123?server=http://plex:32400&path=/key&token=xyz&offset=120")
            list(response.iter_bytes())

        # Vérification des arguments passés à Plex
        call_args = mock_stream.call_args[1]['params']
        assert call_args['offset'] == 120