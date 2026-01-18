# 📊 Recommandations de Fonctionnalités PlexAPI à Intégrer

## Vue d'ensemble
Selon la documentation PlexAPI, votre application PlexHub récupère actuellement les éléments **de base**. Voici les fonctionnalités **prioritaires** et **bonus** à ajouter.

---

## 🔴 PRIORITÉ HAUTE - Features Essentielles

### 1. **Continue Watching / On Deck** ✅ (Partiellement implémenté)
**Status:** Votre app a `get_on_deck()` mais elle est basique

**À améliorer:**
```python
# Ajouter dans plex_client.py
async def get_on_deck(self):
    """Continue watching depuis TOUS les serveurs, pas juste le principal"""
    on_deck_items = []
    for resource in resources:
        on_deck = await asyncio.to_thread(server.library.onDeck)
        # Construire des MediaDetail complets pour chaque item
        # Inclure : view_offset, view_count, durée restante calculée
```

**Bénéfice:** Affiche ce que l'utilisateur regarde actuellement sur chaque serveur

---

### 2. **Récemment Ajouté (Recently Added)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
section.recentlyAdded(maxresults=50, libtype='movie')
section.recentlyAddedMovies(maxresults=20)
section.recentlyAddedShows(maxresults=20)
```

**À implémenter:**
```python
async def get_recently_added(self, limit=50):
    """Récupère les X derniers médias ajoutés"""
    for section in sections:
        items = await asyncio.to_thread(section.recentlyAdded, maxresults=limit)
        # Construction MediaDetail pour chaque item
```

**Bénéfice:** Dashboard avec nouveautés, découverte facile

---

### 3. **Historique de Lecture (Watch History)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
library.history(maxresults=50, mindate=datetime)
section.history(maxresults=50, mindate=datetime)
movie.lastViewedAt  # datetime
movie.viewCount     # Nombre de lectures
```

**À implémenter:**
```python
async def get_watch_history(self, limit=100, days_back=30):
    """Historique de lecture des X derniers jours"""
    min_date = datetime.now() - timedelta(days=days_back)
    history = await asyncio.to_thread(library.history, maxresults=limit, mindate=min_date)
    # Construire timeline utilisateur
```

**Bénéfice:** Analytics utilisateur, statistiques de visionnage

---

### 4. **Clients Connectés (Connected Clients)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
plex.clients()           # Tous les clients
plex.client('Nom')       # Client spécifique
client.isPlaying()
client.isStreaming()
```

**À implémenter:**
```python
async def get_active_clients(self):
    """Liste des clients actuellement connectés"""
    clients = await asyncio.to_thread(plex.clients)
    for client in clients:
        print(f"Client: {client.title}, État: {'Actif' if client.isAvailable else 'Hors ligne'}")
```

**Bénéfice:** Savoir où on peut lire, afficher état playback live

---

### 5. **Sessions Actives (Now Playing)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
plex.sessions()          # Médias en cours de lecture
for session in sessions:
    session.usernames    # Utilisateurs
    session.title
    session.viewOffset   # Position actuelle
    session.duration
    session.progressPercent
```

**À implémenter:**
```python
async def get_now_playing(self):
    """Qui regarde quoi en ce moment"""
    sessions = await asyncio.to_thread(plex.sessions)
    for session in sessions:
        return {
            "user": session.usernames[0],
            "media": session.title,
            "position": session.viewOffset,
            "duration": session.duration,
            "progress": session.progressPercent
        }
```

**Bénéfice:** Dashboard en temps réel, partage d'infos entre utilisateurs

---

### 6. **Édition des Métadonnées** ⚠️ PARTIELLEMENT
**Vous avez** : `markWatched()`, `markUnwatched()`, `updateProgress()`
**Vous n'avez pas:**
```python
movie.edit(title='', year=, rating=, summary=, **kwargs)
movie.addCollection('Favorites')
movie.removeCollection('Collection')
movie.addGenre('Action')
movie.addLabel('4K', '4K UHD', 'Watched')
movie.editContentRating('PG-13')
```

**À implémenter:**
```python
async def mark_as_favorite(self, media_id):
    """Ajouter aux favoris"""
    item = await asyncio.to_thread(server.fetchItem, media_id)
    await asyncio.to_thread(item.addLabel, 'Favorites')
    
async def rate_media(self, media_id, rating):
    """Noter un média (0-10)"""
    item = await asyncio.to_thread(server.fetchItem, media_id)
    await asyncio.to_thread(item.editUserRating, rating)
```

**Bénéfice:** Interaction complète, personnalisation librairie

---

### 7. **Recherche Avancée** ⚠️ BASIQUE
**Vous avez:** `plex.search('query')` basique
**À améliorer:**
```python
section.search(
    title='Batman',
    year=2020,
    unwatched=True,  # Non vus
    sort='rating:desc',
    filters={'genre': 'action', 'director': 'Christopher Nolan'}
)
```

**À implémenter:**
```python
async def advanced_search(self, filters):
    """Recherche avec filtres complexes"""
    # title, year, unwatched, sort, filters
    results = await asyncio.to_thread(section.search, **filters)
```

**Bénéfice:** Meilleure discoverabilité, filtres puissants

---

## 🟡 PRIORITÉ MOYENNE - Features Intéressantes

### 8. **Hubs (Découverte Algorithmique)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
library.hubs()           # Tous les hubs
section.hubs()           # Hubs section
plex.library.onDeck()    # Recommandés
```

**À implémenter:**
```python
async def get_discovery_hubs(self):
    """Hubs de découverte (algorithme Plex)"""
    hubs = await asyncio.to_thread(library.hubs)
    for hub in hubs:
        print(f"Hub: {hub.title}")
        for item in hub.items:
            # Construire MediaDetail
```

**Bénéfice:** Découverte guidée, recommandations intelligentes

---

### 9. **Extras & Trailers** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
movie.extras()           # Trailers, BTS, etc.
movie.reviews()          # Critiques IMDB, etc.
clip.subtype            # 'trailer', 'behindTheScenes', 'scene', etc.
```

**À implémenter:**
```python
# Dans _build_api_cache, ajouter un champ 'extras'
extras_list = []
if hasattr(item, 'extras'):
    for extra in item.extras[:5]:  # Top 5
        extras_list.append({
            'title': extra.title,
            'type': extra.subtype,
            'duration': extra.duration,
            'thumb': extra.thumb
        })
media_item.extras = extras_list
```

**Bénéfice:** Accès trailers, bonus, making-of

---

### 10. **Tags & Collections Enrichies** ⚠️ PARTIELLEMENT
**Vous avez:** `genres`, `collections` dans models
**Vous n'avez pas:**
```python
item.labels               # Labels personnalisés
item.moods               # Ambiances (musique)
item.styles              # Styles (musique)
library.tags('director') # Tous les réalisateurs
library.tags('actor')    # Tous les acteurs
```

**À implémenter:**
```python
# Ajouter dans models.py
class MediaDetail:
    labels: List[str] = Field(default_factory=list)  # Favoris, 4K, etc.
    
# Dans plex_client.py
labels = [l.tag for l in item.labels] if hasattr(item, 'labels') else []
```

**Bénéfice:** Filtrage avancé par tags personnalisés

---

### 11. **Informations Serveur Détaillées** ⚠️ TRÈS BASIQUE
**Vous avez:** Nom, URL, owned, latency
**Vous n'avez pas:**
```python
plex.version             # Version Plex
plex.myPlexSubscription  # Plex Pass actif
plex.transcoderVideo    # Transcodeur disponible
plex.allowSync          # Sync autorisé
plex.transcodeSessions() # Sessions transcoding
plex.activities()        # Scans, indexations en cours
plex.updater            # Mise à jour disponible
```

**À implémenter:**
```python
# Enrichir ServerInfo dans models.py
class ServerInfo:
    plex_pass: bool = False
    transcoder_available: bool = False
    version: str = ""
    active_activities: List[str] = Field(default_factory=list)
```

**Bénéfice:** Diagnostics serveur, status détaillé

---

### 12. **Playlists (Intelligentes & Manuelles)** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
plex.playlists()         # Toutes les playlists
plex.playlist('Ma Playlist')
playlist.items()         # Items playlist
playlist.smart           # True si intelligente
```

**À implémenter:**
```python
async def get_playlists(self):
    """Récupère toutes les playlists"""
    playlists = await asyncio.to_thread(plex.playlists)
    for pl in playlists:
        items = await asyncio.to_thread(pl.items)
        # Construire liste d'items
```

**Bénéfice:** Gestion playlists, sharing collections

---

### 13. **Acteurs & Équipe (Cast & Crew)** ⚠️ COMMENTÉ
**Vous avez le modèle** mais **commenté** à cause du coût performance

**À implémenter correctement:**
```python
# Dans _process_item, récupérer les acteurs AVEC LIMIT
cast_list = []
if hasattr(item, 'roles') and item.roles:
    for role in item.roles[:10]:  # Limite à 10 (performance)
        cast_list.append({
            'name': role.tag,
            'role': role.role or 'Unknown',
            'thumb': role.thumb
        })

# Ajouter au raw_cache
"cast": cast_list
```

**Bénéfice:** Infos acteurs, recherche par acteur

---

### 14. **Transcodage & Optimisation** ❌ NON IMPLÉMENTÉ
**Attributs disponibles:**
```python
item.optimize(
    target='mobile',
    deviceProfile='Android',
    videoQuality=VIDEO_QUALITY_10_MBPS_1080p
)
```

**Note:** Feature avancée pour mobile sync

---

## 🟢 PRIORITÉ BASSE - Features Bonus

### 15. **Téléchargements** ❌ NON IMPLÉMENTÉ
```python
movie.download(savepath='/downloads', keep_original_name=False)
```
**Note:** Hors scope pour UI web

---

### 16. **Photothèque** ❌ NON IMPLÉMENTÉ
**Si vous supportez les sections photo:**
```python
photo_section = library.section('Photos')
albums = photo_section.searchPhotoAlbums()
photos = album.photos()
```

---

### 17. **Musique** ❌ NON IMPLÉMENTÉ
**Si vous supportez les sections musique:**
```python
music_section = library.section('Musique')
artists = music_section.searchArtists()
albums = artist.albums()
tracks = album.tracks()
```

---

### 18. **Webhooks & Real-time** ❌ NON IMPLÉMENTÉ
```python
plex.startAlertListener(callback)  # WebSocket
# Notifications real-time de changements
```

---

## 📋 Checklist d'Implémentation

### Phase 1 - ESSENTIEL (1-2 semaines)
- [ ] Recently Added
- [ ] Watch History
- [ ] Active Sessions / Now Playing
- [ ] Édition métadonnées (Favoris, Notes)
- [ ] Recherche avancée

### Phase 2 - IMPORTANT (1 semaine)
- [ ] Hubs / Découverte
- [ ] Extras & Trailers
- [ ] Playlists
- [ ] Serveur info enrichies

### Phase 3 - OPTIMISATION (1 semaine)
- [ ] Cast & Crew (acteurs)
- [ ] Labels personnalisés
- [ ] Sessions actives en temps réel

### Phase 4 - FUTUR (Bonus)
- [ ] Musique
- [ ] Photos
- [ ] Webhooks

---

## 🎯 Implémentation Rapide - Ordre Recommandé

### 1️⃣ **Recently Added** (15 min)
Ajouter `section.recentlyAdded()` au scan

### 2️⃣ **Continue Watching amélioré** (30 min)
Faire retourner `MediaDetail` complètes avec `view_offset`

### 3️⃣ **Métadonnées éditables** (45 min)
Ajouter endpoints API pour `markFavorite()`, `rate()`

### 4️⃣ **Active Sessions** (30 min)
Endpoint `/api/now-playing` retournant sessions Plex

### 5️⃣ **Historique** (30 min)
Endpoint `/api/history` avec filtrage dates

### 6️⃣ **Recherche avancée** (1h)
Améliorer logique search avec filtres

---

## 💡 Impact sur l'UX

| Feature | Impact | Difficulté | Temps |
|---------|--------|-----------|-------|
| Recently Added | ⭐⭐⭐ Haut | Facile | 15m |
| History | ⭐⭐⭐ Haut | Facile | 30m |
| Sessions | ⭐⭐⭐ Haut | Moyen | 1h |
| Favorites | ⭐⭐⭐ Haut | Facile | 30m |
| Hubs | ⭐⭐ Moyen | Moyen | 1h |
| Playlists | ⭐⭐ Moyen | Moyen | 1h30 |
| Cast | ⭐ Bas | Difficile | 1h |
| Extras | ⭐ Bas | Facile | 30m |

---

## 🚀 Quick Win - À faire en premier

### `get_recently_added()` - 15 minutes
```python
async def get_recently_added(self, limit=20):
    """Retourner les X derniers médias ajoutés"""
    new_cache = {}
    for section in sections:
        items = await asyncio.to_thread(section.recentlyAdded, maxresults=limit)
        for item in items:
            new_cache[item.ratingKey] = self._convert_to_media_detail(item)
    return new_cache
```

### Endpoint API `/api/recently-added`
```python
@app.get('/api/recently-added')
async def recently_added():
    return plex_client.get_recently_added(limit=50)
```

### Affichage template
```html
<div x-show="filters.type === 'new'">
    <div class="grid grid-cols-5 gap-3">
        <template x-for="item in recentlyAdded">
            <!-- Card item -->
        </template>
    </div>
</div>
```

---

## 📝 Conclusion

**Votre app est déjà fonctionnelle à 60-70%.**

Les **meilleures améliorations rapides** sont :
1. Recently Added (découverte)
2. Watch History (engagement)  
3. Active Sessions (présence)
4. Favorites (personnalisation)
5. Advanced Search (puissance)

Chacune prend **30-60 minutes** et apporte **énormément de valeur**.

