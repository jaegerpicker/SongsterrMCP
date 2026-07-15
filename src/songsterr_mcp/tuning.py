"""Tuning representation, presets, and pitch utilities.

Convention: tunings are stored LOW -> HIGH as MIDI note numbers.
(Guitar Pro / Songsterr store strings 1..N high-to-low; gp_io handles
the flip at the boundary so everything internal stays low->high.)
"""

from __future__ import annotations

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOTE_ALIASES = {
    "DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#",
}


def note_to_midi(name: str) -> int:
    """'E2' -> 40, 'A#1' -> 34. Octave numbering: C4 = 60 (middle C)."""
    name = name.strip().upper()
    for i in range(len(name)):
        if name[i].isdigit() or name[i] == "-":
            pitch, octave = name[:i], name[i:]
            break
    else:
        raise ValueError(f"Note {name!r} is missing an octave (e.g. 'E2')")
    pitch = _NOTE_ALIASES.get(pitch, pitch)
    if pitch not in NOTE_NAMES:
        raise ValueError(f"Unknown pitch class {pitch!r}")
    return (int(octave) + 1) * 12 + NOTE_NAMES.index(pitch)


def midi_to_note(midi: int) -> str:
    """40 -> 'E2'."""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _std(high: str, count: int = 6, extra_low: list[str] | None = None) -> list[int]:
    """Build a standard-intervals tuning ending at `high` (low->high MIDI)."""
    # Standard 6-string intervals low->high: P4, P4, P4, M3, P4
    top = note_to_midi(high)
    offsets = [-24, -19, -14, -9, -5, 0]  # relative to the high string
    pitches = [top + o for o in offsets]
    for n in (extra_low or []):
        pitches.insert(0, note_to_midi(n))
    return pitches


TUNING_PRESETS: dict[str, list[int]] = {
    # --- 6-string standards ---
    "e_standard": _std("E4"),
    "eb_standard": _std("D#4"),
    "d_standard": _std("D4"),
    "db_standard": _std("C#4"),
    "c_standard": _std("C4"),
    "b_standard_6": _std("B3"),
    # --- 6-string drops ---
    "drop_d": [note_to_midi(n) for n in ["D2", "A2", "D3", "G3", "B3", "E4"]],
    "drop_db": [note_to_midi(n) for n in ["C#2", "G#2", "C#3", "F#3", "A#3", "D#4"]],
    "drop_c": [note_to_midi(n) for n in ["C2", "G2", "C3", "F3", "A3", "D4"]],
    "drop_b": [note_to_midi(n) for n in ["B1", "F#2", "B2", "E3", "G#3", "C#4"]],
    # --- 7-string ---
    "b_standard_7": _std("E4", extra_low=["B1"]),
    "a_standard_7": _std("D4", extra_low=["A1"]),
    "drop_a_7": [note_to_midi(n) for n in ["A1", "E2", "A2", "D3", "G3", "B3", "E4"]],
    # --- 8-string ---
    "fs_standard_8": _std("E4", extra_low=["F#1", "B1"]),
    "drop_e_8": [note_to_midi(n) for n in ["E1", "B1", "E2", "A2", "D3", "G3", "B3", "E4"]],
    # --- bass ---
    "bass_standard_4": [note_to_midi(n) for n in ["E1", "A1", "D2", "G2"]],
    "bass_standard_5": [note_to_midi(n) for n in ["B0", "E1", "A1", "D2", "G2"]],
}


def resolve_tuning(spec: str | list[str] | list[int]) -> list[int]:
    """Resolve a tuning spec into low->high MIDI numbers.

    Accepts a preset name ('b_standard_7'), a list of note names low->high
    (['B1','E2','A2','D3','G3','B3','E4']), a space/comma-separated string
    of the same, or a list of raw MIDI ints.
    """
    if isinstance(spec, str):
        key = spec.strip().lower().replace(" ", "_").replace("-", "_")
        if key in TUNING_PRESETS:
            return list(TUNING_PRESETS[key])
        parts = [p for p in spec.replace(",", " ").split() if p]
        if len(parts) > 1:
            return [note_to_midi(p) for p in parts]
        raise ValueError(
            f"Unknown tuning {spec!r}. Use a preset "
            f"({', '.join(sorted(TUNING_PRESETS))}) or explicit notes "
            f"low->high like 'B1 E2 A2 D3 G3 B3 E4'."
        )
    if all(isinstance(x, int) for x in spec):
        return list(spec)  # type: ignore[arg-type]
    return [note_to_midi(str(n)) for n in spec]


def describe_tuning(tuning: list[int]) -> str:
    """[35, 40, ...] -> 'B1 E2 A2 D3 G3 B3 E4'."""
    return " ".join(midi_to_note(m) for m in tuning)
