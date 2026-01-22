
import asyncio
import sys
import logging
from pathlib import Path

# Setup path
sys.path.append(str(Path(__file__).parent))

from app.config import settings
from app.plex_client import PlexClient
from plexapi.myplex import MyPlexAccount

# Configure logging to see our debug prints
logging.basicConfig(level=logging.INFO)

async def verify_trailer_logic():
    print("--- Verifying Trailer Logic ---")
    
    # Initialize Client
    client = PlexClient()
    
    # We need to manually drive the process to test _process_item
    token = settings.PLEX_TOKEN
    account = MyPlexAccount(token=token)
    resource = next((r for r in account.resources() if "server" in r.provides), None)
    
    if not resource:
        print("No server found")
        return

    print(f"Connecting to {resource.name}...")
    server = resource.connect()
    section = next((s for s in server.library.sections() if s.type == "movie"), None)
    
    if not section:
        print("No movie section")
        return

    # Fetch one item with trailers (we know from previous run that '96uma' has one)
    # We can try to search for it or just take the first few
    items = section.all(maxresults=5)
    
    target_item = None
    for item in items:
        # Check if it has extras using the API directly first to be sure
        if item.extras():
             target_item = item
             print(f"Found item with extras: {item.title}")
             break
    
    if not target_item:
        print("No item with extras found in top 5. Searching deeper or aborting.")
        # Try search?
        # target_item = section.get("Inception") 
        return

    # Now verify _process_item logic
    print(f"Testing _process_item on: {target_item.title}")
    
    # Clean cache
    client.raw_cache.clear()
    
    # Process
    await client._process_item(target_item, "movie", resource, server)
    
    # Check Result
    key, _ = client._get_unique_key(target_item)
    cached_data = client.raw_cache[key][0]
    
    trailers = cached_data.get('trailers', [])
    print(f"Trailers found in cache: {len(trailers)}")
    for t in trailers:
        print(f"  - {t['title']} (Key: {t['key']})")
        
    if len(trailers) > 0:
        print("✅ SUCCESS: Trailers successfully extracted and cached.")
    else:
        print("❌ FAILURE: No trailers found in cache.")

if __name__ == "__main__":
    asyncio.run(verify_trailer_logic())
