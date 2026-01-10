# 📺 PlexHub Backend (VPerf)

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**PlexHub** est un agrégateur haute performance pour serveurs Plex, conçu spécifiquement pour être déployé sur un NAS  avec des ressources optimisées. Il centralise le contenu de plusieurs serveurs dans une interface unique, fluide et légère.



## 🚀 Caractéristiques du Lot 1 (Stable)

* **Architecture Multi-Worker** : Optimisé pour le multiprocessing (Uvicorn) avec 4 workers et gestion d'un "Worker Maître" via verrouillage atomique pour éviter les scans redondants.
* **Moteur SQLite (Mode WAL)** : Persistance des données ultra-rapide sur SSD NVMe, permettant des accès concurrents sans verrouillage.
* **Optimisation d'Image (Pillow/WebP)** : Proxy d'images qui redimensionne et convertit les posters en WebP à la volée pour économiser l'espace et la bande passante.
* **Streaming Robuste** : Gestion de flux via sémaphore avec bascule automatique entre transcodage 720p et Direct Play.
* **Découverte mDNS** : Annonce automatique du service sur le réseau local via Zeroconf pour une intégration simplifiée.
* **Hardening & Sécurité** : Filtrage des tokens dans les logs et gestion des secrets via variables d'environnement (`python-dotenv`).

## 🛠️ Installation & Déploiement

### Prérequis
* Python 3.13+
* Un compte Plex et un Token valide
* Docker & Docker Compose



### 🐳 Stack Docker de Production
Voici la configuration recommandée pour votre `docker-compose.yml`:

```yaml
services:
  plexhub:
      image: ghcr.io/chakirhamzachahid/agregatorplextv:feature_serie
      container_name: plexhub-backend
      restart: unless-stopped
      network_mode: host
      environment:
        - PLEX_TOKEN=*********VOTRE TOKEN*********
        - TZ=Europe/Paris
      volumes:
        - /mnt/app-config/plexhub:/app/cache_assets
        - /mnt/app-config/plexhub/logs:/app/logs
      deploy:
        resources:
          limits:
            memory: 4G
            cpus: '2.0'
