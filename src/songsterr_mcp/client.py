"""Songsterr HTTP client.

Endpoint status (July 2026 — verify before shipping):
  - Legacy documented API (XML/JSON REST, no key):
      GET /a/ra/songs.json?pattern=<q>
      GET /a/ra/songs/byartists.json?artists=<a,b>
    Publicly documented, stable for years.
  - Modern site API (unofficial, powers the React player):
      GET /api/songs?pattern=<q>&size=<n>
      GET /api/meta/<song_id>/revisions
    Revision objects historically expose a `source` URL to the underlying
    Guitar Pro file on their CDN. Unofficial — expect breakage; keep the
    legacy endpoints as fallback.

Songsterr permits non-commercial API use; commercial use needs approval.
Be a good citizen: cache aggressively, identify yourself in User-Agent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

BASE = "https://www.songsterr.com"
USER_AGENT = "songsterr-mcp/0.1 (open-source, non-commercial; +https://github.com/CHANGEME/songsterr-mcp)"
CACHE_DIR = Path.home() / ".cache" / "songsterr_mcp"


def _cache_path(key: str, suffix: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()}{suffix}"


class SongsterrClient:
    def __init__(self, timeout: float = 20.0):
        self._http = httpx.AsyncClient(
            base_url=BASE,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search(self, pattern: str, limit: int = 10) -> list[dict]:
        """Search songs; modern endpoint with legacy fallback."""
        try:
            r = await self._http.get("/api/songs", params={"pattern": pattern, "size": limit})
            r.raise_for_status()
            return r.json()[:limit]
        except (httpx.HTTPError, json.JSONDecodeError):
            r = await self._http.get("/a/ra/songs.json", params={"pattern": pattern})
            r.raise_for_status()
            return r.json()[:limit]

    async def revisions(self, song_id: int) -> list[dict]:
        """Tab revisions for a song (newest first). Unofficial endpoint."""
        r = await self._http.get(f"/api/meta/{song_id}/revisions")
        r.raise_for_status()
        return r.json()

    async def download_source(self, song_id: int) -> Path:
        """Download the newest revision's source (Guitar Pro) file, cached."""
        revisions = await self.revisions(song_id)
        if not revisions:
            raise LookupError(f"No revisions found for song {song_id}")
        source = revisions[0].get("source")
        if not source:
            raise LookupError(
                f"Song {song_id}: revision has no source file URL. The unofficial "
                f"endpoint shape may have changed — inspect the revision JSON."
            )
        suffix = Path(httpx.URL(source).path).suffix or ".gp5"
        path = _cache_path(source, suffix)
        if path.exists():
            return path
        r = await self._http.get(source)
        r.raise_for_status()
        path.write_bytes(r.content)
        return path
