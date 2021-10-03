import logging
from pathlib import Path

# https://ep2019.europython.eu/media/conference/slides/KNhQYeQ-downloading-a-billion-files-in-python.pdf
import requests

log = logging.getLogger(__name__)

def download(uri, dest: Path, force: bool = False):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_dir():
        dest = dest / uri.rpartition("/")[2]
    if dest.exists() and not force:
        log.debug("dest file present, not reloading %s", dest)
        return dest
    with requests.get(uri, stream=True) as r:
        r.raise_for_status()
        with dest.open("wb") as fp:
            for chunk in r.iter_content(chunk_size=8192): 
                fp.write(chunk)
    return dest
            

