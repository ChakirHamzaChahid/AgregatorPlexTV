
import asyncio
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.config import settings
from plexapi.myplex import MyPlexAccount

def test_scan_speed(include_extras=False):
    print(f"\n--- Testing Scan Speed (includeExtras={include_extras}) ---")
    token = settings.PLEX_TOKEN
    if not token:
        print("No token.")
        return

    account = MyPlexAccount(token=token)
    resources = account.resources()
    server_resource = next((r for r in resources if "server" in r.provides), None)
    
    if not server_resource:
        print("No server.")
        return

    server = server_resource.connect()
    sections = server.library.sections()
    movie_section = next((s for s in sections if s.type == 'movie'), None)
    
    if not movie_section:
        print("No movie section.")
        return

    print(f"Server: {server.friendlyName}")
    print(f"Section: {movie_section.title}")
    
    start_time = time.time()
    # Fetch a subset to test speed, but plexapi.all() usually fetches everything. 
    # container_start/size might work if supported by library.all, but typically library.all fetches all.
    # We'll try fetching up to 10 items. library.all() returns a list.
    # Wait, 'all' might not support maxresults. 'search' does.
    # But we want to simulate what refresh_library does: section.all()
    
    # section.all() supports **kwargs which are passed to 'key'.
    # e.g. section.all(includeExtras=1)
    
    # To avoid fetching 1000 items, let's just fetch a few if possible, 
    # but section.all usually gets everything.
    # Let's try section.search(limit=5, includeExtras=include_extras) which is safer for test.
    
    print("Fetching 5 items...")
    items = movie_section.search(limit=5, includeExtras=include_extras)
    
    duration = time.time() - start_time
    print(f"Fetch took: {duration:.4f}s")
    
    trailers_count = 0
    for item in items:
        # If includeExtras worked, item.extras should be populated without network call?
        # Typically plexapi objects lazy load. We need to check if 'extras' attribute is set/populated 
        # or if accessing it triggers a reload.
        # We can check item._data or similar to see if 'extras' XML tag was present.
        
        # In plexapi, extras are usually a property that calls self.reload() if key not in attributes.
        # But if we pass includeExtras=1, maybe the XML has it.
        
        # Let's try to access it and measure time.
        t0 = time.time()
        try:
            # We iterate to force access
            if item.extras:
                trailers_count += 1
        except: pass
        dt = time.time() - t0
        print(f"  Item {item.title}: Extras access took {dt:.4f}s")

    print(f"Total items with extras: {trailers_count}")

if __name__ == "__main__":
    test_scan_speed(include_extras=False)
    test_scan_speed(include_extras=True)
