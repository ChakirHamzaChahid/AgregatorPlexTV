# 🔀 Architecture du Merge Multi-Serveurs

## Vue d'ensemble

Le système fonctionne en **2 phases** :

```
Phase 1: Scan & Collection
┌─────────────────────────────────┐
│ Serveur A: Inception (tt1375666)│
│ Serveur B: Inception (tt1375666)│
│ Serveur C: Inception (tt1375666)│
└──────────────┬──────────────────┘
               │
               ▼
         raw_cache dict
     {
       "tt1375666": [
         {serveur_A_data},
         {serveur_B_data},
         {serveur_C_data}
       ]
     }

Phase 2: Fusion & Déduplication
┌────────────────────────────────┐
│  Un seul MediaDetail("Inception"
│  avec 3 sources[A, B, C]       │
└────────────────────────────────┘
```

---

## Phase 1: Collecte des Données (`_process_item()`)

### Étape 1: Extraction Clé Unique

```python
# plex_client.py, ligne 453-461

imdb_id = None
if item.guids:
    for guid in item.guids:
        if 'imdb' in guid.id:
            match = re.search(r'tt\d+', guid.id)
            if match: 
                imdb_id = match.group(0)  # ex: "tt1375666"
                break

# Fallback si pas d'ID IMDB
key = imdb_id if imdb_id else f"{item.title}-{item.year}"
# key = "tt1375666" ou "Inception-2010"
```

### Étape 2: Stockage dans `raw_cache`

```python
# plex_client.py, ligne 584

self.raw_cache[key].append({
    'title': item.title,           # "Inception"
    'year': item.year,             # 2010
    'type': section_type,          # "movie"
    'server_name': resource.name,  # "Serveur A", "Serveur B", etc.
    'server_url': server.baseurl,  # "http://192.168.0.100:32400"
    'server_token': resource.accessToken,
    'machine_id': resource.clientIdentifier,
    'is_owned': resource.owned,    # True pour ton propre serveur
    'key': item.ratingKey,         # Plex rating key
    'play_id': item.key,           # Plex playback key
    'thumb': item.thumb,           # URL du poster
    'art': item.art,               # URL du backdrop
    'rating': item.rating,         # Note Plex
    'duration': item.duration,     # Durée en ms
    'resolution': resolution,      # "1080P", "4K", etc.
    'badges': badges,              # ["4K", "HDR", "Atmos"]
    'genres': genres,              # ["Sci-Fi", "Action"]
    'summary': item.summary,       # Description
    # ... + autres champs
})
```

### Structure `raw_cache`

```python
raw_cache = {
    "tt1375666": [  # IMDB ID (clé unique)
        {
            'title': 'Inception',
            'server_name': 'Mon Serveur',
            'is_owned': True,
            'resolution': '1080P',
            'badges': ['HDR', 'Atmos'],
            # ...
        },
        {
            'title': 'Inception',
            'server_name': 'Serveur Ami',
            'is_owned': False,
            'resolution': '4K',
            'badges': ['4K', 'HDR'],
            # ...
        },
        {
            'title': 'Inception',
            'server_name': 'Autre Serveur',
            'is_owned': False,
            'resolution': '720P',
            'badges': [],
            # ...
        }
    ]
}
```

---

## Phase 2: Fusion & Construction API (`_build_api_cache()`)

### Étape 1: Sélection du "Main"

```python
# plex_client.py, ligne 638-639

for key, instances in self.raw_cache.items():
    # Priorité: ton propre serveur > serveurs partagés
    main = next((i for i in instances if i['is_owned']), instances[0])
    # main = le premier serveur "owned"
```

### Étape 2: Construction du MediaDetail

```python
# plex_client.py, ligne 690+

media_item = MediaDetail(
    id=key,                    # "tt1375666"
    type=main['type'],         # "movie"
    title=main['title'],       # "Inception"
    year=main['year'],         # 2010
    rating=main['rating'],     # 8.8
    poster_url=poster_link,    # URL via proxy
    backdrop_url=backdrop_link,# URL via proxy
    # ... tous les champs du 'main'
)
```

### Étape 3: Ajout des Sources

```python
# plex_client.py, ligne 697-710

if main['type'] == 'movie':
    for inst in instances:  # Itère sur les 3 instances
        params = self._build_url_params(inst)
        media_item.sources.append(Source(
            server_name=inst['server_name'],      # "Mon Serveur"
            resolution=inst['resolution'],        # "1080P"
            is_owned=inst['is_owned'],            # True/False
            stream_url=f"/vlc-stream/{...}",
            m3u_url=f"/playlist/{...}",
            plex_deeplink=f"plex://preplay/...",
            plex_web_url=f"https://app.plex.tv/..."
        ))
```

### Résultat Final

```python
MediaDetail(
    id="tt1375666",
    title="Inception",
    year=2010,
    rating=8.8,
    poster_url="/proxy-image?...",
    
    sources=[
        Source(
            server_name="Mon Serveur",
            resolution="1080P",
            is_owned=True,
            stream_url="/vlc-stream/...",
            # ...
        ),
        Source(
            server_name="Serveur Ami",
            resolution="4K",
            is_owned=False,
            stream_url="/vlc-stream/...",
            # ...
        ),
        Source(
            server_name="Autre Serveur",
            resolution="720P",
            is_owned=False,
            stream_url="/vlc-stream/...",
            # ...
        )
    ]
)
```

---

## Priorités de Sélection

### 1. Clé Unique (Identification)
```
IMDB ID (tt1234567)
    ▼
"Titre-Année" (fallback)
```

### 2. Source Principale (Métadonnées)
```
Ton propre serveur (is_owned=True)
    ▼
Premier serveur partagé
```

### 3. Utilisation des Sources
```
L'API retourne TOUTES les sources
Android/Frontend choisit laquelle lire
```

---

## Exemple Concret

### Scénario
Tu as 2 serveurs :
- **Serveur A** (ton serveur) : Inception 1080P
- **Serveur B** (partagé) : Inception 4K

### Phase 1 - Scan Serveur A
```
item.title = "Inception"
item.year = 2010
item.guids = [{id: "imdb://tt1375666"}]

key = "tt1375666"
raw_cache["tt1375666"].append({
    server_name: "Serveur A",
    is_owned: True,
    resolution: "1080P",
    ...
})
```

### Phase 1 - Scan Serveur B
```
item.title = "Inception"
item.year = 2010
item.guids = [{id: "imdb://tt1375666"}]

key = "tt1375666"  # MÊME CLÉ!
raw_cache["tt1375666"].append({
    server_name: "Serveur B",
    is_owned: False,
    resolution: "4K",
    ...
})
```

### Phase 2 - Fusion
```
key = "tt1375666"
instances = [serveur_A_data, serveur_B_data]

main = serveur_A_data  # is_owned=True

MediaDetail:
  - id: "tt1375666"
  - title: "Inception"
  - poster_url: [proxy Serveur A]  # métadonnées du main
  - sources: [
      {server: "Serveur A", res: "1080P"},
      {server: "Serveur B", res: "4K"}
    ]
```

---

## Cas Spécial : Séries TV

Pour les séries, la fusion est plus complexe car il faut merger les épisodes :

```python
# plex_client.py, ligne 711-740

seasons_map = defaultdict(lambda: defaultdict(dict))
for inst in instances:  # Chaque serveur
    for ep in inst['episodes']:  # Chaque épisode
        s_idx = ep['season']
        e_idx = ep['index']
        
        if e_idx not in seasons_map[s_idx]:
            # Créer l'épisode si pas déjà présent
            seasons_map[s_idx][e_idx] = EpisodeDetail(...)
        
        # Ajouter la source à cet épisode
        seasons_map[s_idx][e_idx].sources.append(Source(...))
```

### Exemple Série
```
Serveur A: The Office - S01E01 720P
Serveur B: The Office - S01E01 1080P
Serveur B: The Office - S01E02 1080P

Résultat:
  S01E01: [Serveur A 720P, Serveur B 1080P]  ← fusion
  S01E02: [Serveur B 1080P]
```

---

## Clés de Déduplication

### Priority 1: IMDB ID
```
item.guids = [
    {id: "imdb://tt1375666"},
    {id: "tmdb://..."},
    {id: "plex://..."}
]
→ Extracte "tt1375666"
```

### Priority 2: Titre + Année
```
Si pas d'IMDB: "Inception-2010"
Risque: Si même titre, années différentes = doublons
```

---

## Architecture Actuellement

```
1. refresh_library() 
   └─ pour chaque serveur:
      ├─ _connect_and_scan()
      │  └─ pour chaque section:
      │     └─ pour chaque item:
      │        └─ _process_item()
      │           └─ raw_cache[key].append(item_data)

2. _build_api_cache()
   └─ pour chaque key dans raw_cache:
      ├─ Sélectionner main (is_owned first)
      ├─ Créer MediaDetail
      └─ Ajouter toutes les sources
```

---

## Limitation Actuelle

### ⚠️ Métadonnées non Mergées
Actuellement, seule la **première source (main)** est utilisée pour les métadonnées :

```python
media_item = MediaDetail(
    rating=main['rating'],        # ❌ Pas la moyenne de tous
    genres=main['genres'],        # ❌ Pas l'union de tous
    summary=main['summary'],      # ❌ Pas fusionné
    # ...
)
```

**Amélioration Possible:**
```python
# Moyenner les ratings
all_ratings = [i['rating'] for i in instances if i['rating']]
avg_rating = sum(all_ratings) / len(all_ratings)

# Fusionner les genres
all_genres = set()
for i in instances:
    all_genres.update(i['genres'])

# Prendre le meilleur résumé (plus long?)
best_summary = max([i['summary'] for i in instances], key=len)
```

---

## Récapitulatif

| Étape | Lieu | Fonction | Résultat |
|-------|------|----------|----------|
| **1. Collecte** | `_process_item()` | Pour chaque item de chaque serveur | `raw_cache[key].append(...)` |
| **2. Groupement** | `raw_cache` | Dict `key -> [instances]` | `raw_cache["tt1375666"] = [A, B, C]` |
| **3. Fusion** | `_build_api_cache()` | Merge les instances | Un `MediaDetail` avec N `sources` |
| **4. API** | REST endpoints | Retourne le MediaDetail | Client reçoit tout (main + sources) |

---

## Avantages

✅ **Un seul objet par film** - Pas de doublons
✅ **Métadonnées optimales** - Du meilleur serveur (owned)
✅ **Choix de la source** - Frontend/Android choisit quelle version lire
✅ **Scalabilité** - Fonctionne avec N serveurs
✅ **Déduplication robuste** - Basée sur IMDB ID (standard industriel)

## Inconvénients

❌ **Métadonnées pas mergées** - Toujours du main
❌ **Pas de score de qualité** - L'app Android doit décider
❌ **Fallback titre-année** - Risque de faux doublons si même titre différentes années
