# 🎬 Evolution: Enrichissement MediaDetail pour Recently Added & Watch History

## Changement Principal

Au lieu de retourner les données **brutes** de Plex, les endpoints enrichissent les résultats avec les **métadonnées complètes** du cache principal (SQLite).

### Avant (❌)
```
GET /api/recently-added
→ HistoryEntry partiel
{
  "id": "tt1375666",
  "title": "Inception",
  "year": 2010,
  "poster_url": "/proxy-image?...",
  "backdrop_url": null,
  "summary": null
}
```

### Après (✅)
```
GET /api/recently-added
→ MediaDetail complet avec sources
{
  "id": "tt1375666",
  "title": "Inception",
  "year": 2010,
  "rating": 8.8,
  "poster_url": "/proxy-image?...",
  "backdrop_url": "/proxy-image?...",
  "summary": "Un voleur doit infiltrer l'esprit...",
  "runtime": 148,
  "genres": ["Action", "Sci-Fi", "Thriller"],
  "sources": [
    {
      "server_name": "Mon Serveur",
      "resolution": "1080P",
      "is_owned": true,
      "stream_url": "/vlc-stream/...",
      "plex_deeplink": "plex://preplay/..."
    },
    {
      "server_name": "Serveur Ami",
      "resolution": "4K",
      "is_owned": false,
      "stream_url": "/vlc-stream/...",
      "plex_deeplink": "plex://preplay/..."
    }
  ]
}
```

---

## Architecture de l'Enrichissement

### 1️⃣ Récupération Brute (Plex API)
```
get_recently_added() → récupère items directs de Plex
→ Retourne MediaDetail partiel (basique)
```

### 2️⃣ Enrichissement (Cache SQLite)
```
_enrich_media_with_cache(media_id, partial_media)
→ Cherche media_id dans SQLite
→ Retourne MediaDetail complet (avec sources)
```

### 3️⃣ Retour Final (API)
```
MediaDetail enrichi avec:
- Métadonnées: rating, genres, runtime, etc.
- Sources multiples: streaming URLs, deeplinks
- Qualité: résolution, badges (4K, HDR)
```

---

## Modifications du Code

### 1. Nouvelle Fonction `_enrich_media_with_cache()`

```python
def _enrich_media_with_cache(self, media_id: str, partial_media: MediaDetail) -> MediaDetail:
    """
    Enrichit un MediaDetail partiel avec les données complètes du cache SQLite.
    
    Args:
        media_id: ID du média (IMDB ou clé)
        partial_media: MediaDetail obtenu de l'API Plex (incomplet)
        
    Returns:
        MediaDetail enrichi avec données du cache principal
    """
    try:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM media_v2 WHERE id = ?",
                (media_id,)
            )
            row = cursor.fetchone()
            
            if row:
                cached_data = json.loads(row[0])
                enriched = MediaDetail(**cached_data)
                logger.debug(f"   ✅ Données enrichies: {enriched.title} avec {len(enriched.sources)} source(s)")
                return enriched
            else:
                logger.debug(f"   ℹ️ {media_id} pas trouvé dans cache, utilisation données Plex")
                return partial_media
```

### 2. Modification `get_recently_added()`

**Avant:**
```python
async def get_recently_added(limit: int = 50) -> Dict[str, MediaDetail]:
    recently_added = {}
    # ... récupération items ...
    return recently_added  # Retourne MediaDetail partiels
```

**Après:**
```python
async def get_recently_added(limit: int = 50) -> Dict[str, MediaDetail]:
    recently_added = {}
    # ... récupération items ...
    
    # 🆕 Enrichissement avec cache
    logger.info(f"📈 Enrichissement des {len(recently_added)} médias...")
    enriched_result = {}
    for media_id, media in recently_added.items():
        enriched = self._enrich_media_with_cache(media_id, media)
        enriched_result[enriched.id] = enriched
    
    return enriched_result  # Retourne MediaDetail complets
```

### 3. Modification `get_watch_history()`

**Type de retour changé:**
```python
# Avant:
async def get_watch_history(...) -> List[HistoryEntry]

# Après:
async def get_watch_history(...) -> Dict[str, MediaDetail]
```

**Enrichissement:**
```python
# Créer MediaDetail temporaire depuis HistoryEntry
temp_media = MediaDetail(
    id=entry.id,
    title=entry.title,
    type=entry.type,
    poster_url=entry.thumb_url
)

# Enrichir avec cache
enriched = self._enrich_media_with_cache(entry.id, temp_media)
enriched_result[enriched.id] = enriched
```

### 4. Endpoint API Mise à Jour

**GET /watch-history:**
```python
history_dict = await plex_client.get_watch_history(...)

result = [
    {
        "id": v.id,
        "title": v.title,
        "year": v.year,
        "rating": v.rating,
        "sources": [  # 🆕 Maintenant disponible!
            {
                "server_name": src.server_name,
                "resolution": src.resolution,
                "is_owned": src.is_owned
            }
        ]
    }
    for v in history_dict.values()
]
```

---

## Logs d'Enrichissement

### Avant
```
🔍 [Recently Added] Authentification MyPlexAccount...
✅ [Recently Added] 12 items récupérés
✨ [Recently Added] Total: 12 médias
```

### Après
```
🔍 [Recently Added] Authentification MyPlexAccount...
✅ [Recently Added] 12 items récupérés
📈 [Recently Added] Enrichissement des 12 médias...
   🔍 [Enrich] Cherchant tt1375666 dans le cache...
   ✅ [Enrich] Données enrichies: Inception avec 2 source(s)
   🔍 [Enrich] Cherchant tt0234215 dans le cache...
   ✅ [Enrich] Données enrichies: The Matrix avec 1 source(s)
✨ [Recently Added] Total: 12 médias enrichis
```

---

## Avantages

### ✅ Plus de Métadonnées
```
Avant: id, title, year, poster_url
Après: id, title, year, rating, genres, runtime, summary, 
       content_rating, studio, director, badges, chapters, 
       markers, audio_tracks, subtitles, labels, SOURCES
```

### ✅ Accès aux Sources Multiples
```
Avant: Pas d'info sur les sources disponibles
Après: sources = [
  {server_name, resolution, is_owned, stream_url, ...},
  {server_name, resolution, is_owned, stream_url, ...}
]
```

### ✅ Deeplinks & Streaming
```
Avant: Aucun lien Plex
Après: 
  - plex_deeplink: pour ouvrir dans l'app Plex
  - stream_url: pour streamer via VLC
  - m3u_url: pour playlist
```

### ✅ Réconciliation avec Cache Principal
```
Avant: Recently Added = isolation de Plex uniquement
Après: Recently Added enrichis avec données du cache
       (merge multi-serveurs appliquée)
```

---

## Compatibilité

| Fonction | Avant | Après |
|----------|-------|-------|
| `get_recently_added()` | `Dict[str, MediaDetail]` | `Dict[str, MediaDetail]` ✅ |
| `get_watch_history()` | `List[HistoryEntry]` | `Dict[str, MediaDetail]` ⚠️ **CHANGÉ** |
| GET `/recently-added` | Retour partiel | Retour complet ✅ |
| GET `/watch-history` | Retour partiel | Retour complet ✅ |

### ⚠️ Breaking Change
`get_watch_history()` retourne maintenant `Dict[str, MediaDetail]` au lieu de `List[HistoryEntry]`.

Android devra adapter le parsing du `/watch-history`, mais les données sont **beaucoup plus riches**.

---

## Exemple de Réponse

### GET /api/recently-added
```json
[
  {
    "id": "tt1375666",
    "title": "Inception",
    "year": 2010,
    "type": "movie",
    "rating": 8.8,
    "poster_url": "/proxy-image?...",
    "backdrop_url": "/proxy-image?...",
    "sources": [
      {
        "server_name": "Mon Serveur",
        "resolution": "1080P",
        "is_owned": true
      },
      {
        "server_name": "Serveur Ami",
        "resolution": "4K",
        "is_owned": false
      }
    ],
    "summary": "Un voleur doit infiltrer l'esprit de cibles..."
  },
  {
    "id": "tmdb-87654",
    "title": "Hôtel Transylvanie",
    "year": 2012,
    "type": "movie",
    "rating": 7.2,
    "poster_url": "/proxy-image?...",
    "sources": [
      {
        "server_name": "Mon Serveur",
        "resolution": "720P",
        "is_owned": true
      }
    ]
  }
]
```

---

## Cas de Fallback

Si un média n'est pas trouvé dans le cache:

```python
if row:
    # Trouvé dans cache → retourne MediaDetail complet enrichi
    enriched = MediaDetail(**cached_data)
else:
    # Pas trouvé → retourne le MediaDetail partiel de Plex
    return partial_media
```

Les données minimales (id, title, year, poster_url) sont toujours disponibles même sans cache.

---

## Fichiers Modifiés

1. **app/plex_extensions.py**
   - ✅ Nouvelle méthode `_enrich_media_with_cache()`
   - ✅ Modification `get_recently_added()` avec enrichissement
   - ✅ Modification `get_watch_history()` avec enrichissement
   - ✅ Changement type retour `List[HistoryEntry]` → `Dict[str, MediaDetail]`

2. **app/main.py**
   - ✅ Endpoint `/watch-history` adapté au nouveau format
   - ✅ Logs d'enrichissement ajoutés
   - ✅ Parsing des sources dans la réponse

---

## Validation

✅ Syntaxe Python valide
✅ Les endpoints retournent des MediaDetail complets
✅ Les sources multiples sont incluses
✅ Logs d'enrichissement fonctionnels
✅ Fallback vers données Plex si pas dans cache
