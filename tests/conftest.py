"""
pytest configuration et fixtures globales.

Définit:
- Configuration de test globale
- Fixtures partagées
- Hooks pour le reporting
"""

import pytest
import sys
from pathlib import Path

# Ajouter le répertoire root au path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# CONFIGURATION PYTEST
# =============================================================================

def pytest_configure(config):
    """Configuration initiale de pytest"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (deselect with '-m \"not asyncio\"')"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (deselect with '-m \"not slow\"')"
    )

def pytest_collection_modifyitems(config, items):
    """Modifier les items collectés"""
    for item in items:
        # Auto-mark asyncio tests
        if "asyncio" in str(item.fspath):
            item.add_marker(pytest.mark.asyncio)

# =============================================================================
# FIXTURES GLOBALES
# =============================================================================

@pytest.fixture(scope="session")
def test_config():
    """Configuration commune pour tous les tests"""
    return {
        "plex_token": "test-token-12345",
        "plex_server": "http://192.168.1.100:32400",
        "api_base": "http://localhost:8000/api",
        "cache_ttl": 300,
        "max_streams": 4,
        "stream_chunk_size": 8192
    }

@pytest.fixture(scope="function", autouse=True)
def reset_mocks():
    """Reset tous les mocks avant chaque test"""
    yield
    # Cleanup après chaque test

@pytest.fixture
def mock_logger():
    """Mock du logger pour éviter la pollution des logs"""
    from unittest.mock import MagicMock
    return MagicMock()

@pytest.fixture
def mock_asyncio():
    """Mock asyncio pour les tests"""
    from unittest.mock import AsyncMock
    return {
        "sleep": AsyncMock(),
        "gather": AsyncMock(),
        "to_thread": AsyncMock()
    }

# =============================================================================
# MARKERS
# =============================================================================

@pytest.fixture(scope="session")
def markers():
    """Marqueurs disponibles pour les tests"""
    return {
        "asyncio": "Tests asynchrones",
        "integration": "Tests d'intégration",
        "slow": "Tests lents"
    }

# =============================================================================
# REPORTING
# =============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Customiser le reporting des tests"""
    outcome = yield
    rep = outcome.get_result()
    
    if call.when == "call":
        if rep.outcome == "failed":
            # Log additionnel pour les tests échoués
            pass
