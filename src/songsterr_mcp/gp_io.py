"""Adapter between pyguitarpro's object model and the engine's Beat model.

Guitar Pro numbers strings 1..N from HIGH to LOW; the engine indexes the
tuning list LOW to HIGH. All flipping happens here and nowhere else.

Lossy notes: the scaffold round-trips pitch, duration, ties, and the
effects that constrain fingering (slides / hammer-ons / pull-offs). Other
effects (bends, vibrato, harmonics, palm mutes...) are preserved by
carrying the original pyguitarpro note object in Beat.meta and re-applying
what still makes sense — natural harmonics in particular may not survive a
tuning change and are flagged by the engine as warnings. Tighten this as
the project matures.
"""

from __future__ import annotations

import guitarpro

from .refinger import Beat, Note


def track_tuning(track: "guitarpro.Track") -> list[int]:
    """Low->high MIDI tuning for a GP track."""
    return [s.value for s in sorted(track.strings, key=lambda s: s.value)]


def _flip(track_string_count: int, gp_string_number: int) -> int:
    """GP string number (1=high) -> low->high index, and back (symmetric)."""
    return track_string_count - gp_string_number


def load_beats(track: "guitarpro.Track") -> list[Beat]:
    n = len(track.strings)
    beats: list[Beat] = []
    for measure in track.measures:
        voice = measure.voices[0]  # scaffold: first voice only
        for gp_beat in voice.beats:
            notes = []
            for gp_note in gp_beat.notes:
                effects = set()
                if gp_note.effect.slides:
                    effects.add("slide")
                if gp_note.effect.hammer:
                    effects.add("hammer")
                notes.append(Note(
                    string=_flip(n, gp_note.string),
                    fret=gp_note.value,
                    effects=frozenset(effects),
                    tie=gp_note.type == guitarpro.NoteType.tie,
                ))
            beats.append(Beat(
                notes=notes,
                rest=not notes,
                meta={"gp_beat": gp_beat},
            ))
    return beats


def write_beats(song: "guitarpro.Song", track_index: int, beats: list[Beat], dst_tuning: list[int]) -> None:
    """Rewrite a track in place with re-fingered beats and a new tuning."""
    track = song.tracks[track_index]
    n = len(dst_tuning)
    track.strings = [
        guitarpro.GuitarString(number=i + 1, value=dst_tuning[n - 1 - i])
        for i in range(n)
    ]
    it = iter(beats)
    for measure in track.measures:
        for gp_beat in measure.voices[0].beats:
            beat = next(it)
            for gp_note, note in zip(gp_beat.notes, beat.notes):
                gp_note.string = _flip(n, note.string)
                gp_note.value = note.fret


def load_song(path: str) -> "guitarpro.Song":
    return guitarpro.parse(path)


def save_song(song: "guitarpro.Song", path: str) -> None:
    guitarpro.write(song, path)
