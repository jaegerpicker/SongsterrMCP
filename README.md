# songsterr-mcp

MCP server for fetching Songsterr tabs and transposing them between tunings and
string counts — e.g. taking a song tabbed for 6-string C standard and re-fingering
it, pitch-perfect, for a 7-string in B standard.

**Status: scaffold.** The transposition engine is implemented and tested; the
Songsterr client uses a mix of documented-legacy and unofficial endpoints that need
live verification (see below).

## Tools

| Tool | Purpose |
|---|---|
| `songsterr_search_songs` | Find songs by title/artist pattern |
| `songsterr_get_tab` | Download a song's Guitar Pro source (cached), list tracks + tunings |
| `songsterr_transpose` | Re-finger a track onto a new tuning/string count; ASCII or .gp5 out |
| `songsterr_list_tunings` | Enumerate tuning presets |

Typical flow: search → get_tab (pick a track) → transpose with
`target_tuning="b_standard_7"` → read the ASCII or open the written `.gp5`.
`semitone_shift` changes actual key; `0` preserves the original pitch across the
tuning change.

## Install & run

```bash
pip install -e .
python -m songsterr_mcp.server        # stdio transport
```

Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "songsterr": { "command": "python", "args": ["-m", "songsterr_mcp.server"] }
  }
}
```

Tests: `pytest tests/`

## Architecture

```
src/songsterr_mcp/
├── server.py      # FastMCP tool definitions (thin; no business logic)
├── client.py      # Songsterr HTTP client + on-disk cache (~/.cache/songsterr_mcp)
├── gp_io.py       # pyguitarpro <-> engine model adapter; ALL string-number
│                  #   flipping (GP is high->low, engine is low->high) lives here
├── refinger.py    # the engine: pitch decode -> candidates -> beam search
├── tuning.py      # presets, note<->MIDI, tuning spec parsing
└── ascii_tab.py   # monospace tab rendering
```

The engine never touches Guitar Pro objects or HTTP — it operates on a neutral
`Beat`/`Note` model, so it's independently testable and reusable (e.g. against
alphaTex or MusicXML sources later). See `docs/ALGORITHM.md` for the full
re-fingering algorithm, cost model, and known limitations.

## Songsterr API caveats

- Legacy REST endpoints (`/a/ra/songs.json?pattern=`) are publicly documented,
  keyless, and stable.
- The modern endpoints (`/api/songs`, `/api/meta/{id}/revisions`, and the revision
  `source` URL pointing at the underlying Guitar Pro file) are **unofficial** —
  they power Songsterr's own player and can change without notice. `client.py`
  falls back to legacy where possible and fails with inspectable errors elsewhere.
- Songsterr permits non-commercial API use; commercial use requires their approval.
  This project caches downloads and sends an identifying User-Agent — keep it that
  way.

## License

Intended license: [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)
(drop the license text into `LICENSE` before publishing). Note the pedantry that
matters for your README badges: noncommercial licenses are *source-available*, not
OSI-approved open source. PolyForm NC is the cleanest widely-recognized choice for
"free for everyone except commercial exploitation" and pairs naturally with
Songsterr's own non-commercial API terms.

Tab content fetched through this tool is copyrighted musical composition belonging
to its rights holders; this tool is for personal practice use.
