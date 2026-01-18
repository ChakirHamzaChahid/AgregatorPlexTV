# Utilisation de Python 3.13 slim pour minimiser l'empreinte RAM sur vos 4 Go
FROM python:3.13-slim

# Installation des dépendances système nécessaires pour Pillow (traitement d'images WebP)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Définition du répertoire de travail
WORKDIR /app

# Copie et installation des dépendances Python
# On utilise --no-cache-dir pour garder l'image légère
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de l'intégralité du code source
COPY . .


# Désactiver le buffering Python pour que les logs apparaissent immédiatement dans Docker
ENV PYTHONUNBUFFERED=1

# Création des dossiers cache et logs
RUN mkdir -p /app/cache_assets /app/logs

# L'application écoute sur le port 8000
EXPOSE 8000

# Lancement via run.py qui gère le multi-processing (4 workers pour votre Ryzen 3600)
CMD ["python", "run.py"]