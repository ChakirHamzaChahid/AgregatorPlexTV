
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.config import settings
from plexapi.myplex import MyPlexAccount

async def main():
    print("--- Trailer Reproduction Script ---")
    token = settings.PLEX_TOKEN
    print(f"Token present: {bool(token)}")
    
    if not token:
        print("No token found. Exiting.")
        return

    account = MyPlexAccount(token=token)
    print("Logged into MyPlex")
    
    resources = account.resources()
    server_resource = next((r for r in resources if "server" in r.provides), None)
    
    if not server_resource:
        print("No server resource found.")
        return

    print(f"Connecting to server: {server_resource.name}")
    try:
        server = server_resource.connect()
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    print("Connected!")
    
    # Find a movie section
    sections = server.library.sections()
    movie_section = next((s for s in sections if s.type == 'movie'), None)
    
    if not movie_section:
        print("No movie section found.")
        return
        
    print(f"Using section: {movie_section.title}")
    
    # Get a few items
    items = movie_section.all(maxresults=5)
    
    for item in items:
        print(f"\nChecking movie: {item.title}")
        
        # Check extras
        try:
            print("  Fetching extras...")
            extras = item.extras()
            print(f"  Found {len(extras)} extras.")
            for extra in extras:
                print(f"    - Type: {extra.type}, Subtype: {getattr(extra, 'subtype', 'N/A')}, Title: {extra.title}")
                if getattr(extra, 'subtype', '') == 'trailer':
                    print(f"      -> TRAILER FOUND! Key: {extra.key}")
        except Exception as e:
            print(f"  Error fetching extras: {e}")

if __name__ == "__main__":
    asyncio.run(main())
