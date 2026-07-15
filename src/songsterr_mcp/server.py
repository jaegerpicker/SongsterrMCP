"""songsterr_mcp — MCP server for fetching and transposing Songsterr tabs.

Tools:
  songsterr_search_songs    — find songs by pattern
  songsterr_get_tab         — download a song's Guitar Pro source, list tracks + tunings
  songsterr_transpose       — re-finger a track onto a new tuning / string count
  songsterr_list_tunings    — enumerate tuning presets

Run: `python -m songsterr_mcp.server` (stdio transport).
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from . import ascii_tab, gp_io
from .client import SongsterrClient
from .refinger import refinger
from .tuning import TUNING_PRESETS, describe_tuning, resolve_tuning

mcp = FastMCP("songsterr_mcp")
_client = SongsterrClient()


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pattern: str = Field(..., description="Search text, e.g. 'sleep dragonaut'", min_length=1)
    limit: int = Field(default=10, ge=1, le=25, description="Max results")


@mcp.tool(
    name="songsterr_search_songs",
    annotations={"title": "Search Songsterr", "readOnlyHint": True, "openWorldHint": True},
)
async def songsterr_search_songs(params: SearchInput) -> str:
    """Search Songsterr for songs by title/artist pattern.

    Returns JSON: [{id, title, artist}] — pass `id` to songsterr_get_tab.
    """
    results = await _client.search(params.pattern, params.limit)
    slim = [
        {
            "id": r.get("songId") or r.get("id"),
            "title": r.get("title"),
            "artist": (r.get("artist") or {}).get("name") if isinstance(r.get("artist"), dict) else r.get("artist"),
        }
        for r in results
    ]
    return json.dumps(slim, indent=2)


class GetTabInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    song_id: int = Field(..., description="Songsterr song id from songsterr_search_songs")


@mcp.tool(
    name="songsterr_get_tab",
    annotations={"title": "Fetch Tab", "readOnlyHint": True, "openWorldHint": True},
)
async def songsterr_get_tab(params: GetTabInput) -> str:
    """Download a song's Guitar Pro source file (cached locally).

    Returns JSON: {file, tracks: [{index, name, strings, tuning}]}.
    Pick a track index for songsterr_transpose.
    """
    path = await _client.download_source(params.song_id)
    song = gp_io.load_song(str(path))
    tracks = [
        {
            "index": i,
            "name": t.name,
            "strings": len(t.strings),
            "tuning": describe_tuning(gp_io.track_tuning(t)),
            "is_percussion": t.isPercussionTrack,
        }
        for i, t in enumerate(song.tracks)
    ]
    return json.dumps({"file": str(path), "tracks": tracks}, indent=2)


class TransposeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    file: str = Field(..., description="Path to a Guitar Pro file (from songsterr_get_tab, or any local .gp3/.gp4/.gp5)")
    track_index: int = Field(default=0, ge=0, description="Track to transpose")
    target_tuning: str = Field(
        ...,
        description="Preset name (e.g. 'b_standard_7', 'c_standard', 'drop_a_7') or explicit "
                    "notes low->high, e.g. 'B1 E2 A2 D3 G3 B3 E4'",
    )
    semitone_shift: int = Field(default=0, ge=-12, le=12, description="Shift actual pitch (0 = keep original key)")
    output_format: str = Field(default="ascii", pattern="^(ascii|gp5)$", description="'ascii' returns tab text; 'gp5' writes a file")
    output_path: str | None = Field(default=None, description="Where to write the gp5 (defaults next to input)")


@mcp.tool(
    name="songsterr_transpose",
    annotations={"title": "Transpose Tab", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def songsterr_transpose(params: TransposeInput) -> str:
    """Re-finger a track onto a new tuning/string count, preserving pitch.

    Set semitone_shift to also change key. Returns ASCII tab, or the path
    of a written .gp5, plus any playability warnings.
    """
    song = gp_io.load_song(params.file)
    if params.track_index >= len(song.tracks):
        return f"Error: track_index {params.track_index} out of range (song has {len(song.tracks)} tracks). Run songsterr_get_tab to list tracks."
    track = song.tracks[params.track_index]
    src = gp_io.track_tuning(track)
    dst = resolve_tuning(params.target_tuning)

    beats = gp_io.load_beats(track)
    result = refinger(beats, src, dst, semitone_shift=params.semitone_shift)

    header = (
        f"{track.name}: {describe_tuning(src)} ({len(src)} strings) -> "
        f"{describe_tuning(dst)} ({len(dst)} strings), shift {params.semitone_shift:+d}\n"
    )
    warn = ("\nWarnings:\n" + "\n".join(f"- {w}" for w in result.warnings)) if result.warnings else ""

    if params.output_format == "gp5":
        out = params.output_path or str(Path(params.file).with_suffix("")) + f".{params.target_tuning}.gp5"
        gp_io.write_beats(song, params.track_index, result.beats, dst)
        gp_io.save_song(song, out)
        return header + f"Wrote {out}" + warn
    return header + "\n" + ascii_tab.render(result.beats, dst) + warn


@mcp.tool(
    name="songsterr_list_tunings",
    annotations={"title": "List Tuning Presets", "readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def songsterr_list_tunings() -> str:
    """List available tuning presets and their notes (low->high)."""
    return json.dumps({k: describe_tuning(v) for k, v in TUNING_PRESETS.items()}, indent=2)


if __name__ == "__main__":
    mcp.run()


def main() -> None:
    mcp.run()
