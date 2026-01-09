import uvicorn
import os

if __name__ == "__main__":
    # Configuration simple pour le POC
    # Assurez-vous d'avoir votre token ici ou dans les variables d'environnement système
    # os.environ["PLEX_TOKEN"] = "VOTRE_TOKEN_SI_BESOIN"
    
    print("🚀 Démarrage du POC PlexHub...")
    print("👉 Interface disponible sur : http://localhost:8000")
    
    # Reload=True permet de modifier le code sans redémarrer (pratique pour le dév)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)