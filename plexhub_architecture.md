# Architecture Technique Backend PlexHub

## 1. Résumé exécutif

Le backend **PlexHub** est une API REST Python construite avec **FastAPI 0.128.0** qui agit comme un **agrégateur multi-serveurs Plex** et un **proxy de streaming**. Il :

- Découvre et se connecte à plusieurs serveurs Plex via **PlexAPI 4.17.2**.
- Scanne et **indexe** l’ensemble des bibliothèques vidéo (films/séries) dans une base **SQLite** locale (`library.db`).
- Expose une **API REST** pour consulter les médias avec tri, filtrage et recherche texte.
- Fournit un **proxy de streaming vidéo** (avec tentative de transcodage 720p puis fallback direct play) et un **proxy d’images** optimisé.
- Maintient un **cache HTTP** persistant (SQLite `http_cache.db`) pour réduire la charge sur la base de données.
- Publie sa présence sur le réseau local via **mDNS** (Zeroconf) pour faciliter la découverte par les clients.
- Gère le **multi-worker** (Gunicorn/Uvicorn) avec **élection d’un worker maître** pour éviter les tâches de fond en double.

Ce document détaille l’architecture technique, les composants, les flux, la stack et les risques.

---

## 2. Contexte et objectifs d’architecture

### 2.1. Objectifs fonctionnels

- Centraliser et unifier l’accès à des serveurs Plex multiples.
- Servir une API unique permettant :
  - De découvrir les serveurs Plex disponibles.
  - De parcourir les médias (films/séries) agrégés.
  - D’accéder aux détails des médias.
  - De streamer les contenus via un endpoint HTTP unique.
  - D’exposer des playlists M3U consommables par des players externes.

### 2.2. Objectifs non-fonctionnels

- **Performance** :
  - Scans parallèles des serveurs Plex.
  - Indexation optimisée via SQLite (indexes sur `added_at`, `title`, `type`).
  - Cache HTTP persistant sur les principales requêtes de listing.
- **Robustesse** :
  - Gestion d’un **worker maître** unique pour les tâches de fond (scan + mDNS).
  - Utilisation de `WAL` sur SQLite pour permettre l’accès concurrent.
  - Tolérance partielle aux pannes des serveurs Plex (cache SQLite local).
- **Simplicité de déploiement** :
  - Stack Python unique, dépendances encapsulées dans `requirements.txt`.
  - Déploiement simple via **Uvicorn/Gunicorn** ou Docker.
- **Sécurité minimale** :
  - Protection du `PLEX_TOKEN` dans les logs.
  - Pas de secrets codés en dur.

---

## 3. Vue d’ensemble de l’architecture

### 3.1. Composants principaux

- **App FastAPI (app/main.py)** :
  - Déclare l’application FastAPI et les routes REST.
  - Configure les middlewares (CORS, GZip).
  - Gère le cycle de vie et le multi-worker (élection maître).
  - Définit les endpoints front (index), flux vidéo, images et API.

- **Client Plex (app/plex_client.py)** :
  - Utilise `plexapi` pour se connecter à MyPlex et aux serveurs Plex.
  - Scanne les librairies vidéo (`movie`/`show`) et agrège les données.
  - Normalise les genres, ratings, et structure les `MediaDetail`.
  - Persiste dans `library.db` (SQLite) : médias, serveurs, métadonnées.

- **Service de découverte mDNS (app/discovery.py)** :
  - Utilise `zeroconf` pour publier le service HTTP sous un nom mDNS (`PlexHub._http._tcp.local.`).
  - Choisit explicitement l’interface réseau principale.

- **Modèles de données (app/models.py)** :
  - Définit l’ensemble des structures Pydantic (`MediaDetail`, `Source`, `SeasonDetail`, `EpisodeDetail`, `ServerInfo`).

- **Configuration (app/config.py)** :
  - Charge `.env` via `python-dotenv`.
  - Expose la classe `Settings` (token Plex, client_id, chemins, limites de flux, etc.).

- **Caches SQLite** :
  - `library.db` : index agrégé des médias.
  - `http_cache.db` : cache de réponses API (listes de médias).

### 3.2. Diagramme d’architecture (Mermaid)

```mermaid
graph TB
    subgraph Clients
        WebClient[Client Web]
        MobileClient[Client Mobile / Android]
        Player[Lecteur (VLC, autre)]
    end

    subgraph Backend[PlexHub Backend]
        API[FastAPI app.main]
        Cache[SharedSqliteCache<br/>http_cache.db]
        PlexClient[PlexClient<br/>library.db]
        Discovery[mDNS Zeroconf]
    end

    subgraph PlexInfra[Infrastructure Plex]
        MyPlex[MyPlex (plex.tv)]
        PlexSrv1[Plex Server A]
        PlexSrv2[Plex Server B]
    end

    Clients -->|HTTP /api/...| API
    API -->|cache get/set| Cache
    API -->|SQL query| PlexClient

    API -->|trigger scan| PlexClient
    PlexClient -->|auth + discover| MyPlex
    PlexClient -->|scan libraries| PlexSrv1
    PlexClient -->|scan libraries| PlexSrv2

    API -->|HTTP proxy stream| PlexSrv1
    API -->|HTTP proxy stream| PlexSrv2

    Discovery -->|mDNS announce| Clients

    style API fill:#4CAF50,stroke:#333
    style PlexClient fill:#2196F3,stroke:#333
    style Cache fill:#FF9800,stroke:#333
    style Discovery fill:#9C27B0,stroke:#333
```

---

## 4. Stack technologique

### 4.1. Langage et runtime

- **Python** : version exacte non spécifiée, mais compatible **3.11+ fortement recommandée**.

### 4.2. Frameworks et librairies

Extrait de `requirements.txt` :

```text
fastapi==0.128.0
uvicorn[standard]==0.40.0
gunicorn==23.0.0
httpx==0.28.1
plexapi==4.17.2
pillow==12.1.0
Jinja2==3.1.6
pydantic==2.12.5
zeroconf==0.148.0
python-multipart
python-dotenv
```

**Principales briques :**

- **FastAPI 0.128.0** : framework web ASGI, endpoints REST.
- **Uvicorn 0.40.0 [standard]** : serveur ASGI performant.
- **Gunicorn 23.0.0** : process manager pour multi-workers.
- **Pydantic 2.12.5** : modèles de données, validation et sérialisation JSON.
- **HTTPX 0.28.1** : client HTTP asynchrone employé pour le proxy streaming et les requêtes.
- **PlexAPI 4.17.2** : SDK officiel Plex.
- **Pillow 12.1.0** : traitement d’images (resize, conversion en WebP, cache disque).
- **Jinja2 3.1.6** : rendu du template frontend `index.html`.
- **Zeroconf 0.148.0** : publication mDNS sur le LAN.
- **python-dotenv** : chargement des variables d’environnement depuis `.env`.

### 4.3. Middleware & cross-cutting concerns

- **CORS** : `CORSMiddleware` autorisant toutes origines (`allow_origins=["*"]`).
- **Compression** : `GZipMiddleware` pour réponses > 1000 bytes.
- **Logging** :
  - Logger racine configuré en INFO.
  - Handler console + handler fichier rotatif `server.log`.
  - `TokenFilter` pour masquer `PLEX_TOKEN` dans les messages.
  - Réduction du bruit pour `plexapi`, `urllib3`, `multipart`, `watchfiles`.

---

## 5. Architecture logique détaillée

### 5.1. Structure du code

```text
app/
├── config.py        # Classe Settings, chargement .env
├── models.py        # Modèles Pydantic (données exposées en API)
├── plex_client.py   # Scan Plex, persistance films/séries
├── discovery.py     # Service Zeroconf/mDNS
└── main.py          # FastAPI app, routes, streaming, cache HTTP

cache_assets/        # Répertoire runtime (créé au démarrage)
├── library.db       # Base SQLite des médias scannés
├── http_cache.db    # Base SQLite du cache API
└── server_start.lock# Verrou d’élection du worker maître

requirements.txt     # Dépendances fixes
.env                 # Secrets (PLEX_TOKEN, CLIENT_ID, etc., non versionné)
server.log           # Fichier de logs rotatif
```

### 5.2. `Settings` (config.py)

Classe `Settings` (singleton instancié en bas de fichier) :

- **Secrets & identité** :
  - `PLEX_TOKEN: str` : token d’accès aux APIs Plex.
  - `CLIENT_ID: str` : identifiant client Plex (utilisé pour éviter les alertes "new device").

- **Chemins** :
  - `PROJECT_ROOT: Path` : racine projet.
  - `CACHE_DIR: Path` : répertoire `cache_assets/` (créé si absent).

- **Performance & limites** :
  - `MAX_STREAMS: int` : nombre max de flux vidéo simultanés (3 par défaut).
  - `STREAM_CHUNK_SIZE: int` : taille des chunks de streaming (2 Mo).

- **Scan Plex** :
  - `SCAN_TIMEOUT: int` : timeout connexion serveur Plex (10s).
  - `SCAN_CACHE_TTL: int` : TTL pour autoriser un auto-refresh (5 min, non directement exploité dans le code actuel du scan mais paramétrable).
  - `ONLY_OWNED: bool` : si `True`, filtre les serveurs non possédés.

### 5.3. Modèles Pydantic (models.py)

Les modèles sont des **DTO exposés par l’API** et/ou stockés sous forme JSON dans SQLite.

- **Source** : décrit une source de lecture pour un média.
  - `server_name: str`
  - `resolution: str` (ex: `1080P`)
  - `is_owned: bool`
  - `stream_url: str` (endpoint interne `/vlc-stream/...`)
  - `m3u_url: str` (endpoint interne `/playlist/...`)
  - `plex_deeplink: str` (schéma `plex://`)
  - `plex_web_url: str` (URL https://app.plex.tv/...)

- **EpisodeDetail** :
  - `id: str` (`SxxEyy`).
  - `index: int` (numéro d’épisode).
  - `title: str`.
  - `summary: str`.
  - `thumb_url: str` (URL proxifiée `/proxy-image?...`).
  - `sources: List[Source]`.

- **SeasonDetail** :
  - `index: int` (numéro de saison).
  - `title: str` (ex: `Saison 1`).
  - `episode_count: int`.
  - `episodes: List[EpisodeDetail]`.

- **MediaDetail / MovieDetail (alias)** :
  - `id: str`.
  - `type: str` (`movie` ou `show`).
  - `title: str`.
  - `year: int`.
  - `added_at: datetime`.
  - `studio: Optional[str]`.
  - `content_rating: Optional[str]`.
  - `director: Optional[str]`.
  - `genres: List[str]`.
  - `summary: str`.
  - `rating: float`.
  - `imdb_rating: Optional[float]`.
  - `rotten_rating: Optional[int]`.
  - `poster_url: str` (URL proxifiée image).
  - `sources: List[Source]` (pour films).
  - `seasons: List[SeasonDetail]` (pour séries).

- **ServerInfo** :
  - `name: str`.
  - `url: str`.
  - `owned: bool`.
  - `latency: float`.
  - `status: str` (par défaut `Online`).

### 5.4. Client Plex et persistance (plex_client.py)

#### 5.4.1. Initialisation de la base SQLite `library.db`

- Pragma d’optimisation :
  - `PRAGMA journal_mode=WAL`.
  - `PRAGMA synchronous=NORMAL`.

- Tables :

```sql
CREATE TABLE IF NOT EXISTS media_v2 (
  id TEXT PRIMARY KEY,
  title TEXT,
  year INTEGER,
  added_at TEXT,
  rating REAL,
  type TEXT,
  data TEXT
);

CREATE INDEX IF NOT EXISTS idx_added ON media_v2(added_at);
CREATE INDEX IF NOT EXISTS idx_title ON media_v2(title);
CREATE INDEX IF NOT EXISTS idx_type ON media_v2(type);

CREATE TABLE IF NOT EXISTS servers (
  name TEXT PRIMARY KEY,
  data TEXT
);

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT
);
```

- Récupération du dernier scan :
  - Lecture de `metadata` avec `key='last_scan'`.

#### 5.4.2. Scan et agrégation

- Utilise `MyPlexAccount(token=settings.PLEX_TOKEN)`.
- Récupère `resources = account.resources()`.
- Filtre `resource` pour `"server" in r.provides`.
- Si `settings.ONLY_OWNED` : garde uniquement `r.owned`.
- Pour chaque ressource serveur :
  - `resource.connect(timeout=60)` → objet `server`.
  - `server.library.sections()` → sections (films/séries).
  - Pour chaque section `type in ["movie", "show"]` :
    - `items = section.all()`.
    - Pour les séries : `item.episodes()`.

- Données brutes accumulées dans `self.raw_cache[key].append({...})` :
  - `key` = `imdb_id` si disponible, sinon `"{item.title}-{item.year}"`.
  - Contient : titres, année, ratings Plex, ratings IMDb/Rotten, genres, serveur, token, machineId, etc.

- Normalisation des genres via `GENRE_MAPPING` (fr → en) et fallback `.title()`.

- Extraction ratings externes :
  - Parcourt `item.ratings`.
  - Si `image` contient `imdb` → cast en `float`.
  - Si `image` contient `tomato` → convertit en pourcentage.

#### 5.4.3. Construction du cache API (MediaDetail)

- `_build_api_cache()` :
  - Pour chaque `key` dans `raw_cache` :
    - Choisit une instance principale priorisant `is_owned=True`.
    - Construit `poster_link` via `/proxy-image?url=...&thumb=...`.
    - Crée un `MediaDetail`.
    - Si `type=='movie'` : ajoute un `Source` par instance serveur.
    - Si `type=='show'` : construit `seasons_map` :
      - Clé : numéro de saison.
      - Valeur : dictionnaire des épisodes indexés par `index`.
      - Pour chaque épisode : crée `EpisodeDetail`, `Source` avec proxy stream/m3u.

#### 5.4.4. Sauvegarde en base

- `_prepare_upsert_batch(media_dict)` : construit la liste des tuples `(id, title, year, added_at, rating, type, data_json)`.
- `_perform_upsert_tx(conn, upsert_data)` : upsert via `ON CONFLICT(id) DO UPDATE`.
- `_perform_cleanup_tx(conn, current_scanned_ids)` :
  - Liste `existing_ids` en base.
  - Supprime les IDs qui ne sont plus présents dans le scan courant.

- Mise à jour du `last_scan_time` et stockage dans `metadata` (`key='last_scan'`).

### 5.5. Service de découverte (discovery.py)

- `_get_local_ip()` : utilise un socket UDP vers `1.1.1.1:1` pour déterminer l’IP de sortie.
- `start()` :
  - Si IP détectée n’est pas `127.0.0.1` :
    - Crée un `ServiceInfo` Zeroconf `_http._tcp.local.` nommé `PlexHub._http._tcp.local.`.
    - Adresse = IP locale, port = 8000 (par défaut dans le code).
    - Propriétés : `version=1.0.0`, `path=/api/movies`.
    - Instancie `Zeroconf(interfaces=[local_ip])` pour forcer l’interface.
    - Enregistre le service.
- `stop()` : désenregistre le service et ferme Zeroconf.

### 5.6. FastAPI app, lifecycle et cache HTTP (main.py)

#### 5.6.1. SharedSqliteCache (http_cache.db)

- Initialisation :

```sql
CREATE TABLE IF NOT EXISTS api_cache (
  key TEXT PRIMARY KEY,
  data TEXT,
  expires_at REAL
);
```

- Lecture :
  - Connexion en mode `ro` (`file:{db_path}?mode=ro`) avec timeout de 5s.
  - Vérifie `expires_at > now()`.
  - Retourne la liste des dicts JSON.

- Écriture :
  - Sérialise les modèles en JSON via `item.model_dump(mode='json')`.
  - INSER/REPLACE de `(key, data, expires_at)`.

- Stats :
  - Compte le nombre de lignes `SELECT COUNT(*) FROM api_cache`.

#### 5.6.2. Lifecycle & multi-worker

- `lifespan(app: FastAPI)` :
  - Introduit un petit `sleep` de jitter basé sur `os.getpid()` pour réduire les contentions.
  - Tente de créer `server_start.lock` en mode exclusif (`open(..., "x")`).
  - Si succès → worker maître :
    - Log `"[Worker PID] ÉLU MAÎTRE"`.
    - Démarre un `asyncio.create_task(plex_client.refresh_library(force=False))`.
    - Lance `discovery_service.start()`.
  - Si échec (FileExistsError) → worker esclave :
    - Log `"Worker Esclave - Mode passif"`.
  - À la fin :
    - Si worker maître : supprime le lock file, arrête mDNS.
    - Ferme le client HTTPX global.

#### 5.6.3. Client HTTPX global

- `timeout_config = httpx.Timeout(60.0, connect=30.0)`.
- `limits = httpx.Limits(max_keepalive_connections=settings.MAX_STREAMS + 2, max_connections=20)`.
- `http_client = httpx.AsyncClient(verify=False, timeout=timeout_config, limits=limits)`.

Utilisé pour le proxy d’images et le streaming vidéo (Plex transcoding/direct play).

---

## 6. API REST et flux applicatifs

### 6.1. Routes principales (API Router `/api`)

- `GET /api/servers` → `get_servers()` :
  - Retourne `list[ServerInfo]` depuis `plex_client.get_connected_servers()` (lecture table `servers`).

- `GET /api/movies` → `get_movies(...)` :
  - Paramètres : `page`, `size`, `type`, `sort`, `order`, `search`.
  - Utilise le cache HTTP (`SharedSqliteCache`) avec une clé combinant tous les paramètres.
  - Construit une requête SQL sur `media_v2` avec filtres et tri whitelists.
  - Désérialise `MovieDetail` depuis la colonne `data` (JSON).
  - Adapte la réponse pour les clients Android (supprime `seasons` et `sources`).

- `GET /api/movies/{movie_id}` → `get_movie_detail(movie_id)` :
  - Récupère un média précis par `id` dans `media_v2`.
  - 404 si non trouvé.

- `GET /api/cache/stats` → `get_cache_stats()` :
  - Retourne `{cache_stats: {cached_keys: <int>}, timestamp: <iso>}`.

- `POST /api/cache/clear` → `clear_cache()` :
  - Vide la table `api_cache`.

- `POST /api/refresh` → `trigger_refresh()` :
  - Si `plex_client.is_scanning` : renvoie `{status: "busy"}`.
  - Sinon : planifie en tâche de fond `plex_client.refresh_library(force=True)`.

### 6.2. Routes frontend & streaming

- `GET /` → `index()` :
  - Tente de rendre `templates/index.html` (Jinja2).
  - Fallback sur une simple string HTML si échec.

- `GET /proxy-image` → `proxy_image(url, thumb, token)` :
  - Si déjà en cache (fichier `.webp` sur disque), renvoie la version cache.
  - Sinon :
    - Télécharge l’image depuis Plex.
    - Redimensionne à 400px max de largeur.
    - Convertit en WebP (qualité 80, method 6).
    - Sauvegarde dans `cache_assets/`.
    - Retourne le fichier avec headers de cache très long (`max-age=31536000, immutable`).

- `GET /playlist/{play_id}.m3u` → `get_playlist(...)` :
  - Construit le lien vers `/vlc-stream/{play_id}` avec les bons paramètres (`server`, `path`, `token`).
  - Retourne une playlist M3U contenant une seule entrée.

- `GET /vlc-stream/{play_id}` → `stream_video(...)` :
  - Récupère `server`, `path`, `token`.
  - Crée des headers Plex spécifiques (type Chrome/Android).
  - Utilise un sémaphore pour limiter `MAX_STREAMS`.
  - Tente d’abord un stream transcoding 720p.
  - Si échec : fallback direct play.
  - Stream les données en chunk de `STREAM_CHUNK_SIZE` via HTTPX.

---

## 7. Sécurité, validation et erreurs

### 7.1. Authentification et autorisation

- **Aucune authentification applicative** :
  - Tous les endpoints sont publics sur le LAN.
  - Toute machine ayant accès au backend peut :
    - Lister les médias.
    - Déclencher un scan (`/api/refresh`).
    - Purger le cache (`/api/cache/clear`).
    - Streamer n’importe quel média.

- Authentification côté Plex via `PLEX_TOKEN`.

### 7.2. Validation d’entrées

- Utilisation des types Python + Pydantic pour les paramètres et réponses.
- Protection contre l’injection SQL : usage de `?` et `params` dans les requêtes SQLite.
- `sort` whiteliste les champs valides pour l’ORDER BY.

### 7.3. Gestion des erreurs

- Handler global `@app.exception_handler(Exception)` :
  - Log l’exception complète.
  - Retourne un JSON 500 générique :
    - `{ "detail": "Erreur interne critique du serveur. Consultez server.log." }`.

- Cas spécifiques :
  - 404 si média non trouvé.
  - 503 si sémaphore de streaming saturé.

### 7.4. Logs

- Format uniforme avec timestamp, nom de logger, niveau et message.
- Logs détaillés lors des scans (serveur, section, nombre d’items, erreurs).
- Masquage des tokens Plex dans les logs.

---

## 8. Observabilité et santé

### 8.1. Existant

- `/api/cache/stats` :
  - Permet de vérifier rapidement que le cache HTTP est accessible et de voir le nombre de clés mises en cache.

### 8.2. Manques

- Pas d’endpoint `/health` dédié.
- Pas d’export de métriques Prometheus.
- Pas de correlation-id pour tracer une requête de bout en bout.

---

## 9. Limites, risques et points sensibles

### 9.1. Limites techniques

- Absence de pagination **forcée** sur `/api/movies` : risque de réponses très volumineuses.
- Logique métier fortement couplée aux handlers FastAPI.
- Aucune gestion de versionnement de l’API.

### 9.2. Risques de sécurité

- Aucun contrôle d’accès (tous les endpoints sont ouverts).
- Pas de rate limiting sur `/api/refresh`.

### 9.3. Risques de performance

- Scan complet des bibliothèques potentiellement coûteux.
- Streaming transcoding 720p potentiellement lourd CPU.
- Fuites potentielles de ressources si le client HTTPX n’est pas systématiquement fermé dans tous les workers.

### 9.4. Recommandations d’évolution

- Ajouter :
  - Authentification (API key / JWT).
  - Rate limiting (par IP et sur `/api/refresh`).
  - Endpoints `/health` et `/metrics`.
  - Pagination obligatoire pour `/api/movies`.
- Introduire une couche "service" séparée de l’API.
- Ajout d’une suite de tests (pytest) et d’outils qualité (ruff, mypy).
