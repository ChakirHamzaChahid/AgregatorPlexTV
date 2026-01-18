# Spécification Fonctionnelle & Technique Détaillée – PlexHub Backend

## 1. Objet du document

Ce document décrit la **spécification détaillée** du backend PlexHub, basée strictement sur le code et les éléments fournis :

- Comportement fonctionnel de chaque endpoint.
- Structures de données exposées (schémas JSON, modèles Pydantic).
- Règles métier visibles.
- Contrats d’API (entrées/sorties, erreurs).
- Contraintes techniques et de performance.

Ce document est complémentaire au document **d’architecture technique** et se concentre sur le **"quoi"** et le **"comment précis"** des fonctionnalités.

---

## 2. Domaine fonctionnel

### 2.1. Périmètre

Le backend PlexHub couvre les fonctionnalités suivantes :

1. **Découverte et agrégation de serveurs Plex** :
   - Connexion à un compte MyPlex via un **token Plex**.
   - Découverte des serveurs Plex associés (possédés ou partagés).
   - Filtrage optionnel pour conserver uniquement les serveurs possédés.

2. **Indexation et unification des bibliothèques vidéo** :
   - Scan des sections `movie` et `show` de chaque serveur.
   - Agrégation des items (films/séries) dans une base SQLite locale.
   - Déduplication des médias présents sur plusieurs serveurs (clé = IMDb id ou titre+année).

3. **Exposition d’une API REST** pour :
   - Lister les serveurs Plex connus.
   - Lister les médias (films/séries) avec filtres et tri.
   - Accéder au détail d’un média.
   - Obtenir des informations sur le cache HTTP.
   - Déclencher un rafraîchissement manuel de la bibliothèque.

4. **Streaming vidéo et playlists** :
   - Fournir un endpoint de **streaming vidéo** HTTP.
   - Fournir un endpoint pour générer une **playlist M3U** pointant vers le flux.

5. **Proxy d’images** :
   - Télécharger, optimiser (resize + WebP) et mettre en cache les posters.

6. **Découverte réseau (mDNS)** :
   - Publication d’un service mDNS permettant aux clients sur le LAN de localiser l’API.


### 2.2. Hors périmètre

- Gestion des utilisateurs/permissions internes à PlexHub.
- Gestion de profils, watchlists, historique de visionnage.
- Gestion des sous-titres, metadata avancée (cast complet, etc.).
- UI/Frontend (seulement un index minimal est servi).

---

## 3. Modèle de données fonctionnel

### 3.1. Entité `Source`

Représente **une source de lecture** (stream) pour un film ou un épisode.

```json
{
  "server_name": "PlexServer-A",
  "resolution": "1080P",
  "is_owned": true,
  "stream_url": "/vlc-stream/uuid?server=...&path=...&token=...",
  "m3u_url": "/playlist/uuid.m3u?server=...&path=...&token=...&title=...",
  "plex_deeplink": "plex://preplay/?metadataKey=/library/metadata/123&server=...",
  "plex_web_url": "https://app.plex.tv/desktop/#!/server/.../details?key=/library/metadata/123"
}
```

### 3.2. Entité `EpisodeDetail`

```json
{
  "id": "S01E01",
  "index": 1,
  "title": "Pilot",
  "summary": "Description de l’épisode",
  "thumb_url": "/proxy-image?url=...&thumb=...&token=...",
  "sources": [ { ... Source ... } ]
}
```

### 3.3. Entité `SeasonDetail`

```json
{
  "index": 1,
  "title": "Saison 1",
  "episode_count": 10,
  "episodes": [ { ... EpisodeDetail ... } ]
}
```

### 3.4. Entité `MediaDetail` / `MovieDetail`

Représente un **film ou une série**.

```json
{
  "id": "tt1234567",          // ou "Titre-2020" si pas d’IMDB ID
  "type": "movie",            // "movie" ou "show"
  "title": "Inception",
  "year": 2010,
  "added_at": "2024-01-01T12:34:56",
  "studio": "Warner Bros",
  "content_rating": "PG-13",
  "director": "Christopher Nolan",
  "genres": ["Action", "Sci-Fi"],
  "summary": "Résumé du film...",
  "rating": 8.5,
  "imdb_rating": 8.8,
  "rotten_rating": 87,
  "poster_url": "/proxy-image?url=...&thumb=...&token=...",
  "sources": [ { ... Source ... } ],
  "seasons": [ { ... SeasonDetail ... } ]
}
```

**Remarque** :
- Pour un film : `sources` est rempli, `seasons` généralement vide.
- Pour une série : `seasons` est rempli, `sources` utilisé de manière indirecte au niveau épisode.

### 3.5. Entité `ServerInfo`

```json
{
  "name": "PlexServer-A",
  "url": "http://192.168.1.10:32400",
  "owned": true,
  "latency": 34.5,
  "status": "Online"
}
```

---

## 4. Spécification des endpoints

Tous les endpoints exposés (sauf `/`) sont préfixés par `/api` via `APIRouter(prefix="/api")`.

### 4.1. GET `/api/servers`

#### 4.1.1. Description

Retourne la liste des serveurs Plex connus et persistés dans SQLite, issus du dernier scan.

#### 4.1.2. Requête

- Méthode : `GET`
- Paramètres : **aucun**.

#### 4.1.3. Réponse

- Code 200 :

```json
[
  {
    "name": "PlexServer-A",
    "url": "http://192.168.1.10:32400",
    "owned": true,
    "latency": 34.5,
    "status": "Online"
  }
]
```

- Codes d’erreur : pas de cas particulier prévu (erreurs DB non gérées explicitement → 500 générique via handler global).

#### 4.1.4. Règles métier

- Les serveurs sont lus depuis la table `servers` de `library.db`.
- Les entrées sont mises à jour lors de chaque scan complet (`refresh_library`).

---

### 4.2. GET `/api/movies`

#### 4.2.1. Description

Retourne une liste de médias (films et/ou séries) selon des critères de filtrage, tri et, optionnellement, pagination.

#### 4.2.2. Paramètres

Tous les paramètres sont passés en **query string** :

- `page: int | None` :
  - Si renseigné conjointement avec `size`, active le **mode Android** (payload allégé).
- `size: int | None` :
  - Nombre d’éléments par page.
- `type: str | None` :
  - Filtre sur `"movie"` ou `"show"`.
- `sort: str = "added_at"` :
  - Clé de tri.
  - Valeurs autorisées : `"added_at"`, `"title"`, `"year"`, `"rating"`.
  - Toute autre valeur est mappée par défaut à `"added_at"`.
- `order: str = "desc"` :
  - Ordre de tri, `"asc"` ou `"desc"`.
  - Toute autre valeur est traitée comme `"desc"`.
- `search: str | None` :
  - Sous-chaîne recherchée dans `title` ou `summary` (via `LIKE %search%`).

#### 4.2.3. Comportement fonctionnel

1. **Détermination du mode Android** :
   - Si `page is not None` ET `size is not None` → `is_android_mode = True`.
   - Sinon → `is_android_mode = False`.

2. **Clé de cache** :
   - Concaténation des paramètres : `movies_{page}_{size}_{type}_{sort}_{order}_{search}`.

3. **Consultation du cache HTTP** :
   - `cached_data = _api_cache.get(cache_key)`.
   - Si non nul :
     - Log `"CACHE HIT"`.
     - Reconstruit des `MovieDetail` à partir des dicts JSON et retourne la liste.

4. **Construction de la requête SQL** si MISS :
   - Base : `SELECT data FROM media_v2 WHERE 1=1`.
   - Si `type` défini : `AND type = ?`.
   - Si `search` non vide : `AND (title LIKE ? OR summary LIKE ?)`.
   - Détermination de `sort_col` :
     - `valid_sorts = {"added_at": "added_at", "title": "title", "year": "year", "rating": "rating"}`.
     - `sort_col = valid_sorts.get(sort, "added_at")`.
   - `sort_dir = "ASC"` si `order.lower() == "asc"`, sinon `"DESC"`.
   - Ajout : `ORDER BY {sort_col} {sort_dir}, title ASC`.
   - Si `is_android_mode` : ajout de `LIMIT ? OFFSET ?` avec `offset = (page - 1) * size`.

5. **Exécution SQL et transformation** :
   - Connexion à `library.db`.
   - `MovieDetail.model_validate_json(row['data'])` pour chaque ligne.
   - `base_url` est actuellement une chaîne vide (`""`) → pas d’impact effectif sur les URLs.
   - En mode Android :
     - `m.seasons = []` et `m.sources = []` pour réduire la taille de la réponse.
   - Hors Android :
     - Normalisation des URLs relatives (commençant par `/`) pour `poster_url`, `stream_url`, `m3u_url`, etc. (dans le code, `base_url` est vide, c’est donc un comportement neutre pour l’instant).

6. **Mise en cache** :
   - `_api_cache.set(cache_key, results, ttl_seconds=3600)`.

7. **Réponse** :
   - Retourne `List[MovieDetail]` (films et séries mélangés si `type` non spécifié).

#### 4.2.4. Réponses

- 200 OK : Tableau de `MovieDetail`.
- 500 Internal Server Error :
  - En cas d’erreur SQL : `HTTPException(status_code=500, detail="Database error")`.
  - En cas d’autres erreurs non capturées : renvoyé via le handler global.

---

### 4.3. GET `/api/movies/{movie_id}`

#### 4.3.1. Description

Retourne le détail complet d’un média identifié par son `id` dans la table `media_v2`.

#### 4.3.2. Requête

- Méthode : `GET`
- Paramètre de chemin :
  - `movie_id: str` : identifiant du média (ex: `tt1234567` ou `"Inception-2010"`).

#### 4.3.3. Traitement

1. Connexion SQLite sur `library.db`.
2. `SELECT data FROM media_v2 WHERE id = ?`.
3. Si aucun résultat :
   - Log d’avertissement.
   - `HTTPException(status_code=404, detail="Média introuvable")`.
4. Sinon :
   - `m = MovieDetail.model_validate_json(row['data'])`.
   - Normalisation des URLs relatives pour `poster_url`, `sources[].stream_url`, `sources[].m3u_url`, `seasons[].episodes[].thumb_url`, etc. (même remarque : `base_url` vide actuellement).

#### 4.3.4. Réponses

- 200 OK : objet `MovieDetail`.
- 404 Not Found : média non trouvé.
- 500 Internal Server Error : erreur inattendue (DB, parsing JSON, etc.).

---

### 4.4. GET `/api/cache/stats`

#### 4.4.1. Description

Expose des informations basiques sur le cache HTTP.

#### 4.4.2. Réponse

- 200 OK :

```json
{
  "cache_stats": {
    "cached_keys": 42
  },
  "timestamp": "2026-01-17T20:00:00.123456"
}
```

---

### 4.5. POST `/api/cache/clear`

#### 4.5.1. Description

Vide intégralement le cache HTTP.

#### 4.5.2. Réponse

- 200 OK :

```json
{
  "status": "Cache cleared"
}
```

#### 4.5.3. Effets de bord

- Efface toutes les lignes de `api_cache` dans `http_cache.db`.
- Les prochaines requêtes `/api/movies` redéclencheront des accès à `library.db`.

---

### 4.6. POST `/api/refresh`

#### 4.6.1. Description

Déclenche un **scan manuel** des serveurs Plex, indépendamment du cooldown anti-spam (via `force=True`).

#### 4.6.2. Traitement

1. Si `plex_client.is_scanning == True` :
   - Retourne `{ "message": "Scan déjà en cours", "status": "busy" }`.
2. Sinon :
   - Log du déclenchement manuel.
   - Ajoute une tâche de fond `background_tasks.add_task(plex_client.refresh_library, force=True)`.
   - Retourne `{ "message": "Scan démarré", "status": "accepted" }`.

#### 4.6.3. Réponses

- 200 OK : toujours (busy ou accepted).

#### 4.6.4. Règles métier

- Le scan forcé ignore le cooldown d’1 heure (anti-spam) qui s’applique aux scans automatiques (lifespan).

---

### 4.7. GET `/`

#### 4.7.1. Description

Retourne la page d’index HTML (frontend). 

#### 4.7.2. Traitement

- Tente de rendre `templates/index.html` via Jinja2.
- En cas d’erreur (template manquant ou autre) :
  - Retourne une simple string HTML (`"<h1>PlexHub Ready</h1>"` dans le code réel, tronqué ici).

---

### 4.8. GET `/proxy-image`

#### 4.8.1. Description

Proxy d’images Plex avec optimisation (resize + WebP) et **cache disque**.

#### 4.8.2. Paramètres

- `url: str` : base URL du serveur Plex (utilisé pour reconstruire l’URL finale).
- `thumb: str` : chemin du poster sur le serveur Plex (`item.thumb`).
- `token: str` : token Plex à utiliser pour l’appel.

#### 4.8.3. Traitement

1. Si `thumb` vide → HTTP 404.
2. Génère un "safe filename" à partir de `thumb` (remplacement de certains caractères) et construit `cachepath = settings.CACHE_DIR / safename`.
3. Si `cachepath.exists()` :
   - Retourne directement `FileResponse(cachepath)` avec headers :
     - `Cache-Control: public, max-age=31536000, immutable`.
     - `Access-Control-Allow-Origin: *`.
4. Sinon :
   - Construit `fullurl` à partir de `url` et `thumb` avec query `X-Plex-Token=...`.
   - Télécharge l’image via `http_client.get(fullurl)`.
   - Ouvre l’image avec Pillow, convertit en RGB si nécessaire.
   - Redimensionne à 400px de largeur max avec ratio conservé.
   - Sauvegarde en `.webp` (qualité 80 / method 6) dans `cachepath`.
   - Retourne `FileResponse(cachepath)` avec headers de cache.

#### 4.8.4. Réponses

- 200 OK : fichier image WebP.
- 404 Not Found :
  - `thumb` manquant.
  - Erreur d’accès à l’image Plex.

---

### 4.9. GET `/playlist/{play_id}.m3u`

#### 4.9.1. Description

Génère dynamiquement une playlist **M3U** contenant une seule entrée pointant vers le flux `/vlc-stream/{play_id}`.

#### 4.9.2. Paramètres

- Path : `play_id: str`.
- Query :
  - `server: str` : URL du serveur Plex.
  - `path: str` : chemin de la ressource Plex.
  - `token: str` : token Plex.
  - `title: str` : nom affiché de la ressource.

#### 4.9.3. Réponse

- 200 OK :

```text
#EXTM3U
#EXTINF:-1,My Movie Title
http://<backend>/vlc-stream/<play_id>?server=...&path=...&token=...
```

- `Content-Type: application/x-mpegurl`.

---

### 4.10. GET `/vlc-stream/{play_id}`

#### 4.10.1. Description

Fournit un flux vidéo HTTP pour un média Plex, avec :

- Tentative de **transcodage optimisé 720p**.
- Fallback en **direct play** (pas de transcodage) si le transcoding échoue.
- Contrôle de la **concurrence** via un sémaphore.

#### 4.10.2. Paramètres

- Path : `play_id: str` (identifiant de session unique).
- Query :
  - `server: str` : base URL du serveur Plex (ex: `http://192.168.1.10:32400`).
  - `path: str` : chemin metadata Plex (`item.key`).
  - `token: str` : token Plex.

#### 4.10.3. Règles et comportement

1. Si `stream_semaphore` est déjà saturé :
   - Log "Slots pleins".
   - `HTTPException(status_code=503, detail="Serveur saturé")`.

2. Sinon :
   - Acquisition du sémaphore.
   - Construction de headers "Chrome-like" via `plex_client.get_chrome_headers()`.
   - Construits deux sets de `params` pour Plex :
     - `params_opti` pour transcoding (ex: `videoResolution=1280x720`, `maxVideoBitrate=4000`, `videoCodec=h264`, `audioCodec=aac`, `session=play_id`).
     - `params_fallback` pour direct play (`directPlay=1`, `directStream=1`, sans contraintes de qualité strictes).

3. Essai 1 :
   - Requête HTTPX en mode streaming sur `server + "/video/:/transcode/universal/start"` avec `params_opti`.
   - Si `status_code == 200` :
     - Itère sur `r.aiter_bytes(settings.STREAM_CHUNK_SIZE)` et yield les chunks.
   - Sinon :
     - Log et bascule `usefallback = True`.

4. Essai 2 (fallback) si nécessaire :
   - Même principe avec `params_fallback`.

5. `finally` :
   - Relâchement du sémaphore.
   - Log de fin de stream.

#### 4.10.4. Réponse

- 200 OK : `StreamingResponse` avec `Content-Type: video/x-matroska`.
- 503 Service Unavailable : sémaphore saturé.
- 500 éventuels si erreur réseau non gérée explicitement.

---

## 5. Scénarios d’usage typiques

### 5.1. Application mobile type Android TV

1. Au lancement, l’app appelle `GET /api/movies?page=1&size=50&type=movie&sort=added_at&order=desc`.
2. L’app récupère un tableau de `MovieDetail` **sans `seasons` ni `sources`** (mode Android allégé).
3. Lorsqu’un film est sélectionné, l’app appelle `GET /api/movies/{movie_id}` pour récupérer les détails complets, y compris les `sources`.
4. Pour lancer la lecture dans VLC :
   - Appelle `GET /playlist/{play_id}.m3u?...`.
   - VLC consomme cette M3U et ouvre `/vlc-stream/{play_id}` en HTTP.

### 5.2. Utilisation côté LAN (PC)

1. L’utilisateur ouvre `http://plexhub:8000/` dans son navigateur.
2. Le frontend appelle `/api/movies` et `/api/servers` pour initialiser la vue.
3. L’utilisateur clique sur un média → l’app appelle `/api/movies/{movie_id}`.
4. Lecture vidéo via un lecteur intégré ou via VLC avec l’URL de stream.

---

## 6. Contraintes techniques et non-fonctionnelles

### 6.1. Performance

- **Cache SQLite** pour `/api/movies` : TTL 1h.
- **Index SQLite** sur `added_at`, `title`, `type` pour améliorer les requêtes.
- **Sémaphore** limitant la concurrence streaming (`MAX_STREAMS`).

### 6.2. Sécurité

- Pas d’authentification au niveau API PlexHub (confiance sur le LAN).
- Authentification côté Plex via `PLEX_TOKEN`.
- Masquage du token dans les logs.

### 6.3. Qualité et robustesse

- Aucune suite de tests automatique visible.
- Code défensif mais présence de `try/except: pass` dans certaines zones critiques (risque d’erreurs silencieuses).

---

## 7. Évolutions possibles

- Ajout d’authentification (API Key / JWT).
- Ajout de pagination stricte et obligatoire.
- Ajout de métriques Prometheus et health-checks.
- Introduction d’une couche "service" claire pour la logique métier.
- Suite de tests (pytest) couvrant :
  - Parsing/normalisation Plex.
  - Endpoint de listing/tri/recherche.
  - Endpoints de streaming (mocks HTTPX).
