import socket
import logging
from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger("Discovery")

class DiscoveryService:
    def __init__(self, port: int = 8000):
        self.port = port
        self.zeroconf = None
        self.info = None

    def _get_local_ip(self):
        """Récupère l'IP LAN réelle utilisée pour sortir vers Internet."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # On simule une connexion vers une IP publique pour savoir quelle carte est utilisée
            s.connect(('1.1.1.1', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def start(self):
        """Lance le service mDNS UNIQUEMENT sur l'interface principale."""
        try:
            local_ip = self._get_local_ip()
            
            if local_ip == '127.0.0.1':
                logger.warning("⚠️ Aucune IP réseau détectée. mDNS annulé.")
                return

            logger.info(f"📢 Configuration mDNS stricte sur : {local_ip}")

            # Définition du service
            self.info = ServiceInfo(
                "_http._tcp.local.",
                "PlexHub._http._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "version": "1.0.0",
                    "path": "/api/movies"
                },
                server="plexhub.local."
            )

            # --- FORÇAGE DE L'INTERFACE ---
            # On passe une liste contenant UNIQUEMENT l'IP locale.
            # Zeroconf n'essaiera même pas de regarder les autres cartes (VPN, Docker, etc.)
            self.zeroconf = Zeroconf(interfaces=[local_ip])
            
            self.zeroconf.register_service(self.info)
            logger.info(f"✅ mDNS actif (Interface isolée : {local_ip})")
            
        except Exception as e:
            # Si ça échoue ici, c'est que même la carte principale bloque le Multicast.
            # On log l'erreur mais on laisse l'app tourner.
            logger.error(f"❌ Impossible de démarrer mDNS sur {local_ip}")
            logger.error(f"👉 Cause : {e}")
            logger.warning("👉 L'application reste accessible, mais la découverte auto est désactivée.")

    def stop(self):
        if self.zeroconf:
            try:
                self.zeroconf.unregister_service(self.info)
                self.zeroconf.close()
            except: pass

discovery_service = DiscoveryService()