# ⚠️ Cas Sans ID IMDB

## Qu'est-ce qui se passe ?

### Si le film N'A PAS d'ID IMDB

```python
# plex_client.py, ligne 449-461

imdb_id = None
if item.guids:
    for guid in item.guids:
        if 'imdb' in guid.id:
            match = re.search(r'tt\d+', guid.id)
            if match: imdb_id = match.group(0)
            break

# ❌ Pas de GUID IMDB → imdb_id reste None
# Fallback : Titre + Année
key = imdb_id if imdb_id else f"{item.title}-{item.year}"
# key = "Inception-2010" (pas "tt1375666")
```

---

## Scénarios

### Scénario 1: Film avec IMDB ID ✅

```
item.guids = [
    {id: "imdb://tt1375666"},
    {id: "tmdb://..."},
]

imdb_id = "tt1375666"
key = "tt1375666"

raw_cache["tt1375666"].append({...})
```

### Scénario 2: Film SANS IMDB ID ❌

```
item.guids = [
    {id: "tmdb://87654"},
    {id: "plex://..."},
    # Pas d'IMDB!
]

imdb_id = None
key = "Inception-2010"  # Fallback titre-année

raw_cache["Inception-2010"].append({...})
```

---

## Problème du Fallback Titre-Année

### ⚠️ Risque: Faux Doublons

Si le même titre existe en plusieurs années:

```
Serveur A: Inception (2010) → key = "Inception-2010"
Serveur B: Inception (2024 - remake hypothétique) → key = "Inception-2024"

Résultat: 2 entrées différentes ✅ Correct


MAIS si Année manquante/erronée:

Serveur A: Inception (no year) → key = "Inception-None"
Serveur B: Inception (2010) → key = "Inception-2010"

Résultat: 2 entrées de Inception! ❌ Faux doublon
```

### ⚠️ Risque: Même titre, serveurs différents

```
Serveur A: Inception (2010) → "Inception-2010"
Serveur B: Inception (2010) → "Inception-2010"

Résultat: Bon, ils mergent ✅

MAIS avec métadonnées légèrement différentes:

Serveur A: title="Inception", year=2010
Serveur B: title="Inception ", year=2010  # Espace!

Comparaison: "Inception-2010" != "Inception -2010"

Résultat: 2 doublons! ❌
```

---

## Étapes du Fallback

### 1️⃣ Extraction du GUID

```python
if item.guids:  # Quelque chose à chercher ?
    for guid in item.guids:
        if 'imdb' in guid.id:  # Contient "imdb" ?
            match = re.search(r'tt\d+', guid.id)
            if match:  # Regex match ?
                imdb_id = match.group(0)  # Extraire
                break
```

### 2️⃣ Fallback Titre+Année

```python
key = imdb_id if imdb_id else f"{item.title}-{item.year}"

# Si imdb_id = "tt1375666"  → key = "tt1375666"
# Si imdb_id = None         → key = "Inception-2010"
```

### 3️⃣ Utilisation

```python
# Même clé sur serveurs différents = merge
raw_cache["Inception-2010"].append(serveur_A)
raw_cache["Inception-2010"].append(serveur_B)
# → fusion automatique dans _build_api_cache()
```

---

## Cas Limites

### Cas 1: Film très ancien (pas d'IMDB)
```
Film obscur de 1920 sans IMDB
→ key = "Nosferatu-1920"
→ Fonctionne si titre+année unique
```

### Cas 2: Film sans année
```
item.year = None
→ key = "Inception-None"
→ Risque: tous les films sans année avec même titre = même clé ❌
```

### Cas 3: Titre mal formaté
```
Serveur A: title = "Inception" 
Serveur B: title = "INCEPTION"
→ key_A = "Inception-2010"
→ key_B = "INCEPTION-2010"
→ 2 doublons! ❌
```

---

## Améliorations Possibles

### ✅ Normaliser le titre

```python
import unicodedata

def normalize_title(title):
    # Minuscules
    title = title.lower().strip()
    # Supprimer accents
    title = ''.join(
        c for c in unicodedata.normalize('NFD', title)
        if unicodedata.category(c) != 'Mn'
    )
    # Supprimer caractères spéciaux
    title = ''.join(c if c.isalnum() or c == ' ' else '' for c in title)
    return title

key = imdb_id if imdb_id else f"{normalize_title(item.title)}-{item.year}"
# "Inception-2010" au lieu de "INCEPTION-2010"
```

### ✅ Fallback progressif

```python
def get_unique_key(item):
    # Priority 1: IMDB ID
    if item.guids:
        for guid in item.guids:
            if 'imdb' in guid.id:
                match = re.search(r'tt\d+', guid.id)
                if match: return match.group(0)
    
    # Priority 2: TMDB ID (fallback secondaire)
    if item.guids:
        for guid in item.guids:
            if 'tmdb' in guid.id:
                match = re.search(r'\d+', guid.id)
                if match: return f"tmdb-{match.group(0)}"
    
    # Priority 3: Titre + Année
    return f"{normalize_title(item.title)}-{item.year}"
```

### ✅ Hash du contenu (dernier recours)

```python
import hashlib

def get_unique_key(item):
    # Essayer IMDB
    if imdb_id: return imdb_id
    
    # Fallback: hash du titre/année/durée
    fingerprint = f"{item.title}-{item.year}-{item.duration}".lower()
    return f"hash-{hashlib.md5(fingerprint.encode()).hexdigest()[:8]}"
```

---

## Comportement Actuel

```
┌─────────────────────────────┐
│ Film Plex reçu              │
└────────────┬────────────────┘
             │
      ┌──────▼──────┐
      │ A IMDB ID?  │
      └──┬───────┬──┘
       OUI     NON
        │       │
        │    ┌──▼──────────────┐
        │    │ A Titre+Année?  │
        │    └──┬───────────┬──┘
        │      OUI        NON
        │       │          │
        │       │      ┌───▼──────────┐
        │       │      │ A RatingKey? │
        │       │      └──┬────────┬──┘
        │       │        OUI      NON
        │       │         │        │
    ┌───▼──┐┌──▼───┐┌────▼──┐┌───▼──┐
    │IMDB  ││Title-││Rating  ││Error │
    │ID    ││Year  ││Key     ││Skip  │
    └──────┘└──────┘└────────┘└──────┘
```

---

## Risques & Limitations

| Cas | Probabilité | Impact | Solution |
|-----|------------|--------|----------|
| Film sans IMDB | Moyen | Fallback titre-année | Normalisation +  TMDB fallback |
| Titre variable | Bas | Faux doublons | Normalisation du titre |
| Année manquante | Bas | Key avec "None" | Valider avant traitement |
| Même titre 2 années | Bas | Correct merge | Pas de problème (années différentes) |

---

## Logs pour Diagnostiquer

Ajouter un log si fallback utilisé:

```python
imdb_id = None
if item.guids:
    for guid in item.guids:
        if 'imdb' in guid.id:
            match = re.search(r'tt\d+', guid.id)
            if match:
                imdb_id = match.group(0)
                logger.debug(f"✅ IMDB ID: {item.title} = {imdb_id}")
                break

if not imdb_id:
    logger.warning(f"⚠️ NO IMDB ID: {item.title} ({item.year}) - Using fallback")
    # Montrer les GUIDs disponibles
    if item.guids:
        guids_info = ", ".join([g.id for g in item.guids])
        logger.debug(f"   Available GUIDs: {guids_info}")

key = imdb_id if imdb_id else f"{item.title}-{item.year}"
```

---

## Résumé

### Si IMDB ID existe ✅
```
key = "tt1375666"
Déduplication robuste
```

### Si IMDB ID manque ⚠️
```
key = "Inception-2010"
Risque de faux doublons si:
  - Titre mal formaté
  - Année manquante
  - Variantes de titre
```

### Recommandation
Ajouter une étape de **normalisation du titre** et un **fallback TMDB** avant de résorter au fallback titre-année.
