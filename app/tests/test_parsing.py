# tests/test_parsing.py
import pytest
from app.plex_client import PlexClient
from unittest.mock import MagicMock

@pytest.mark.asyncio
async def test_process_item_robustness():
    client = PlexClient()
    
    # Mock d'un objet Plex "cassé" (sans année, sans note, sans genres)
    broken_item = MagicMock()
    broken_item.title = "Film Cassé"
    broken_item.year = None  # Cas fréquent
    broken_item.rating = None
    broken_item.genres = []
    broken_item.summary = None
    broken_item.guids = []
    broken_item.media = [] # Pas d'info média
    
    # Mock des ressources serveur
    resource = MagicMock()
    resource.name = "TestServer"
    server = MagicMock()
    server._baseurl = "http://fake:32400"
    
    # Exécution : Cela ne doit PAS lever d'exception
    client._process_item(broken_item, "movie", resource, server)
    
    # Vérification
    cache_keys = list(client.raw_cache.keys())
    assert len(cache_keys) == 1
    stored_item = client.raw_cache[cache_keys[0]][0]
    
    assert stored_item['year'] == 0
    assert stored_item['rating'] == 0.0
    assert stored_item['resolution'] == "SD" # Fallback par défaut