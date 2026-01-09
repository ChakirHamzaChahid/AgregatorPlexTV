# tests/test_streaming.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.asyncio
async def test_stream_video_fallback_logic():
    # On mock le client HTTPX interne
    with patch("app.main.http_client.get", new_callable=AsyncMock) as mock_get, \
         patch("app.main.http_client.stream", new_callable=AsyncMock) as mock_stream:
        
        # Scénario : 
        # 1. Le test de transcodage (/decision) renvoie 400 (Refusé)
        # 2. Le fallback (Direct Play) est alors tenté
        
        mock_get.return_value.status_code = 400 # /decision échoue
        
        # On simule le stream du fallback qui réussit (200)
        mock_stream.return_value.__aenter__.return_value.status_code = 200
        mock_stream.return_value.__aenter__.return_value.aiter_bytes = AsyncMock(return_value=[b"chunk_video"])

        # Appel API
        with TestClient(app) as client:
            response = client.get("/vlc-stream/session123?server=http://plex:32400&path=/key&token=xyz")
            
            # On consomme le stream pour déclencher la logique
            list(response.iter_bytes())

        # Vérifications
        assert mock_get.call_count == 1 # On a bien tenté l'optimisation
        # On vérifie que le stream a été appelé avec les paramètres de fallback (directPlay=1)
        call_args = mock_stream.call_args[1]['params']
        assert call_args['directPlay'] == 1