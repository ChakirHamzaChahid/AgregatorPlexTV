# tests/test_concurrency.py
import pytest
import asyncio
from app.config import settings
from app.main import stream_semaphore

@pytest.mark.asyncio
async def test_semaphore_limit():
    # On force la limite à 2 pour le test
    settings.MAX_STREAMS = 2
    # Réinitialiser le sémaphore avec la nouvelle limite
    global stream_semaphore
    stream_semaphore = asyncio.Semaphore(2)

    async def fake_stream():
        # Simule une connexion qui occupe un slot
        if stream_semaphore.locked():
            return "BLOCKED"
        await stream_semaphore.acquire()
        try:
            await asyncio.sleep(0.1) # Reste connecté un peu
            return "OK"
        finally:
            stream_semaphore.release()

    # On lance 3 requêtes simultanées
    results = await asyncio.gather(fake_stream(), fake_stream(), fake_stream())
    
    # Résultat attendu : 2 OK, 1 BLOCKED
    assert results.count("OK") == 2
    assert results.count("BLOCKED") == 1