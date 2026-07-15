"""Minimal ASCII tab renderer.

Renders the engine's Beat model as classic monospace tab, high string on
top, tuning note names as line labels. Good enough for eyeballing output
and for Claude/other LLM clients to read; GP export is the lossless path.
"""

from __future__ import annotations

from .refinger import Beat
from .tuning import midi_to_note

BEATS_PER_LINE = 16


def render(beats: list[Beat], tuning: list[int], beats_per_line: int = BEATS_PER_LINE) -> str:
    n = len(tuning)
    labels = [midi_to_note(m).replace("#", "#") for m in tuning]
    width = max(len(l) for l in labels)
    lines_out: list[str] = []

    for start in range(0, len(beats), beats_per_line):
        chunk = beats[start:start + beats_per_line]
        rows = [f"{labels[s]:<{width}}|" for s in range(n)]
        for beat in chunk:
            cells = ["-"] * n
            for note in beat.notes:
                cells[note.string] = str(note.fret)
            cell_w = max(len(c) for c in cells) + 1
            for s in range(n):
                rows[s] += cells[s].ljust(cell_w, "-") + "-"
        rows = [r + "|" for r in rows]
        lines_out.extend(reversed(rows))  # high string on top
        lines_out.append("")
    return "\n".join(lines_out)
