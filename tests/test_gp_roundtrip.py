"""Full-pipeline test: synth GP5 -> gp_io -> refinger -> gp_io -> GP5.

Covers the string-number flipping (GP is 1..N high->low, engine is
low->high indexed) that lives only in gp_io, which the pure-engine tests
can't reach. Beat construction pitfall: pyguitarpro beats need an explicit
BeatStatus.normal and a duration, or the GP5 reader merges everything into
a single beat at start time zero.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import guitarpro
import pytest

from songsterr_mcp import gp_io
from songsterr_mcp.refinger import refinger
from songsterr_mcp.tuning import TUNING_PRESETS

C_STD = TUNING_PRESETS["c_standard"]
B7 = TUNING_PRESETS["b_standard_7"]

# (gp_string, fret) per beat; GP string 6 is the LOW string on a 6-string.
RIFF = ([(6, 0)], [(6, 0)], [(6, 3)], [(6, 5)], [(6, 0), (5, 2)])


@pytest.fixture
def gp5_path(tmp_path):
    song = guitarpro.Song()
    track = song.tracks[0]
    n = len(C_STD)
    track.strings = [
        guitarpro.GuitarString(number=i + 1, value=C_STD[n - 1 - i]) for i in range(n)
    ]
    voice = track.measures[0].voices[0]
    for fret_sets in RIFF:
        beat = guitarpro.Beat(voice)
        beat.status = guitarpro.BeatStatus.normal
        beat.duration = guitarpro.Duration(value=8)
        for gp_string, fret in fret_sets:
            note = guitarpro.Note(beat)
            note.string, note.value = gp_string, fret
            note.type = guitarpro.NoteType.normal
            beat.notes.append(note)
        voice.beats.append(beat)
    path = tmp_path / "riff.gp5"
    guitarpro.write(song, str(path))
    return str(path)


def _pitches(track):
    tuning = gp_io.track_tuning(track)
    return [
        sorted(tuning[n.string] + n.fret for n in b.notes)
        for b in gp_io.load_beats(track)
    ]


def test_load_flips_strings(gp5_path):
    track = gp_io.load_song(gp5_path).tracks[0]
    assert gp_io.track_tuning(track) == C_STD
    beats = gp_io.load_beats(track)
    assert len(beats) == len(RIFF)
    # GP string 6 (low) must become engine index 0
    assert [n.string for n in beats[0].notes] == [0]
    # note order within a beat is not guaranteed by the GP5 round-trip
    assert sorted((n.string, n.fret) for n in beats[-1].notes) == [(0, 0), (1, 2)]


def test_transpose_roundtrip_preserves_pitch(gp5_path, tmp_path):
    song = gp_io.load_song(gp5_path)
    track = song.tracks[0]
    before = _pitches(track)

    result = refinger(gp_io.load_beats(track), C_STD, B7)
    assert not result.warnings
    gp_io.write_beats(song, 0, result.beats, B7)
    out = tmp_path / "riff.b7.gp5"
    gp_io.save_song(song, str(out))

    reloaded = gp_io.load_song(str(out)).tracks[0]
    assert gp_io.track_tuning(reloaded) == B7
    assert len(reloaded.strings) == 7
    assert _pitches(reloaded) == before
