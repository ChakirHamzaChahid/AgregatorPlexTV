import uvicorn
import os
import multiprocessing

if __name__ == "__main__":
    # Configuration pour le serveur
    # Note : Le PLEX_TOKEN est idéalement chargé via le fichier .env ou les variables système
    
    # On calcule le nombre de workers idéal
    # Pour votre Ryzen 3600 (12 threads) et 4Go de RAM, 4 workers est le "sweet spot"
    # Chaque worker consommera entre 150 et 250 Mo de RAM.
    env_workers = os.getenv("NB_WORKERS")
    
    if env_workers:
        nb_workers = int(env_workers)
    else:
        # Ton calcul par défaut si rien n'est spécifié
        nb_workers = 4
    
    print(f"🚀 Démarrage de PlexHub en mode Multi-Workers ({nb_workers} workers)...")
    print(f"📦 Limite RAM estimée : ~{(nb_workers * 250)} Mo")
    print("👉 Interface provisoire disponible sur : http://IP:8000")
    
    # Lancement du serveur
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8186, 
        workers=nb_workers,  # Active le multi-processing
        reload=False,        # Doit être False pour utiliser les workers
        access_log=True      # Garde les logs d'accès pour server.log
    )