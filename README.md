📺 PlexHub Backend (VPerf)
PlexHub est un agrégateur haute performance pour serveurs Plex, conçu spécifiquement pour être déployé sur un NAS avec des ressources optimisées.

Il permet de centraliser le contenu de plusieurs serveurs Plex (les vôtres et ceux partagés) dans une interface unique, fluide et légère.

🚀 Caractéristiques du Lot 1 (Stable)
Architecture Multi-Worker : Optimisé pour le multiprocessing (Uvicorn/Gunicorn) avec gestion intelligente d'un "Worker Maître" pour éviter les scans redondants.

Moteur SQLite (Mode WAL) : Persistance des données ultra-rapide sur SSD NVMe, permettant des lectures/écritures simultanées sans verrouillage de base de données.

Optimisation d'Image (Pillow/WebP) : Proxy d'images intelligent qui redimensionne et convertit les posters en WebP pour économiser l'espace disque et accélérer le chargement IHM.

Streaming Robuste : Système de proxy vidéo avec bascule automatique (720p Transcode -> Direct Play) et gestion de slots simultanés via sémaphore.

Découverte mDNS : Annonce automatique du service sur le réseau local via Zeroconf.

Hardening & Sécurité : Filtrage automatique des tokens dans les logs et gestion des secrets via variables d'environnement.

🛠️ Installation
Prérequis
Python 3.13+

Un compte Plex avec un Token valide

Docker & Docker Compose (pour le déploiement NAS)

Configuration
Clonez le dépôt :

Bash

git clone https://github.com/votre-compte/PlexHub-Backend.git
cd PlexHub-Backend
Créez un fichier .env à la racine :

Plaintext

PLEX_TOKEN=votre_token_plex_ici
Déploiement via Docker (Recommandé)
Le projet est optimisé pour tourner avec une limite de 4 Go de RAM.

Bash

docker-compose up -d --build
📈 Structure du Projet
run.py : Point d'entrée gérant le multi-processing.

app/main.py : API FastAPI et logique de proxy.

app/plex_client.py : Moteur de scan et interface SQLite.

app/models.py : Schémas de données Pydantic.

cache_assets/ : Stockage de la base library.db et des images optimisées.

# ====================================================================
  # PLEXHUB BACKEND - Votre agrégateur Python
  # ====================================================================
  plexhub:
    build: .
    container_name: plexhub-backend
    restart: unless-stopped
    network_mode: host
    environment:
      - PLEX_TOKEN=${PLEX_TOKEN}
      - TZ=${TZ}
    volumes:
      - /mnt/app-config/plexhub:/app/cache_assets
      - /mnt/app-config/plexhub/logs/server.log:/app/server.log
    depends_on:
      - plex
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'

Développé par Chakir El Arram – Ingénieur IT & Scrum Master.
