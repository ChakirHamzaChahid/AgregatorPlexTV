#!/usr/bin/env python3
"""
Test de la normalisation de titre et extraction de clé unique.
"""

import sys
sys.path.insert(0, '/c/Users/chakir/AgregatorPlexTV')

from app.plex_client import PlexClient

# Test 1: Normalisation de titre
print("=" * 60)
print("TEST 1: Normalisation de Titre")
print("=" * 60)

test_titles = [
    "Inception",
    "INCEPTION",
    "Inception ",
    " Inception",
    "Inceptïon",  # accent
    "Inception: Rêve Lucide",
    "Pokémon: La Série",
    "  Multiple   Spaces  ",
    "Café français",
    "Résumé de théâtre",
]

for title in test_titles:
    normalized = PlexClient._normalize_title(title)
    print(f"'{title:30s}' → '{normalized}'")

# Test 2: Mock item pour tester _get_unique_key
print("\n" + "=" * 60)
print("TEST 2: Extraction de Clé Unique")
print("=" * 60)

class MockGuid:
    def __init__(self, id_str):
        self.id = id_str

class MockItem:
    def __init__(self, title, year, guids=None):
        self.title = title
        self.year = year
        self.guids = guids or []

# Créer un client
client = PlexClient()

# Test cases
test_cases = [
    # Case 1: IMDB ID disponible
    MockItem(
        "Inception",
        2010,
        [
            MockGuid("imdb://tt1375666"),
            MockGuid("tmdb://27205"),
        ]
    ),
    # Case 2: Seulement TMDB
    MockItem(
        "Hôtel Transylvanie",
        2012,
        [
            MockGuid("tmdb://87654"),
        ]
    ),
    # Case 3: Pas d'ID, fallback titre
    MockItem(
        "Film Obscur",
        2005,
        []
    ),
    # Case 4: Pas d'année
    MockItem(
        "Titre Sans Année",
        None,
        []
    ),
    # Case 5: Titre avec caractères spéciaux
    MockItem(
        "Pokémon: Génération Z",
        2024,
        [
            MockGuid("tmdb://1234"),
        ]
    ),
]

for i, item in enumerate(test_cases, 1):
    key, source = client._get_unique_key(item)
    print(f"\nCase {i}: {item.title} ({item.year})")
    print(f"  Key: {key}")
    print(f"  Source: {source}")

print("\n" + "=" * 60)
print("✅ Tests complétés!")
print("=" * 60)
