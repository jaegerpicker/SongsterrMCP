"""Engine tests — the Dragonaut case (C standard 6 -> B standard 7) plus basics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from songsterr_mcp.refinger import Beat, Note, refinger
from songsterr_mcp.tuning import TUNING_PRESETS, describe_tuning, note_to_midi, resolve_tuning

C_STD = TUNING_PRESETS["c_standard"]        # C2 F2 A#2 D#3 G3 C4
B7 = TUNING_PRESETS["b_standard_7"]         # B1 E2 A2 D3 G3 B3 E4


def pitches(beats, tuning):
    return [[tuning[n.string] + n.fret for n in b.notes] for b in beats]


def test_tuning_presets():
    assert describe_tuning(C_STD) == "C2 F2 A#2 D#3 G3 C4"
    assert describe_tuning(B7) == "B1 E2 A2 D3 G3 B3 E4"
    assert resolve_tuning("B1 E2 A2 D3 G3 B3 E4") == B7


def test_pitch_preserved_low_riff():
    # Low-C-string riff (Dragonaut-style chugging): frets 0,0,3,5 on string 0
    beats = [Beat([Note(0, f)]) for f in (0, 0, 3, 5)]
    out = refinger(beats, C_STD, B7)
    assert pitches(out.beats, B7) == pitches(beats, C_STD)
    # Everything should land on the low B string, one fret up
    assert all(b.notes[0].string == 0 and b.notes[0].fret == f + 1
               for b, f in zip(out.beats, (0, 0, 3, 5)))
    assert not out.warnings


def test_power_chord():
    # C5 in C standard: root on string 0 fret 0, fifth on string 1 fret 2
    beats = [Beat([Note(0, 0), Note(1, 2)])]
    out = refinger(beats, C_STD, B7)
    got = sorted(pitches(out.beats, B7)[0])
    assert got == sorted([note_to_midi("C2"), note_to_midi("G2")])
    strings = {n.string for n in out.beats[0].notes}
    assert len(strings) == 2  # distinct strings


def test_g_string_identity():
    # The G string is identical in both tunings; pitch must survive regardless
    # of where the engine chooses to put it.
    beats = [Beat([Note(4, 5)])]  # G3 + 5 = C4
    out = refinger(beats, C_STD, B7)
    assert pitches(out.beats, B7)[0] == [note_to_midi("C4")]


def test_slide_chain_same_string():
    beats = [
        Beat([Note(0, 3, effects=frozenset({"slide"}))]),
        Beat([Note(0, 8)]),
    ]
    out = refinger(beats, C_STD, B7)
    assert out.beats[0].notes[0].string == out.beats[1].notes[0].string
    assert pitches(out.beats, B7) == pitches(beats, C_STD)


def test_out_of_range_octave_shift():
    # Reverse direction: 7-string low B doesn't exist on C standard
    beats = [Beat([Note(0, 0)])]  # B1 on the 7-string
    out = refinger(beats, B7, C_STD)
    assert out.warnings
    assert pitches(out.beats, C_STD)[0] == [note_to_midi("B2")]  # octave up


def test_semitone_shift():
    beats = [Beat([Note(0, 0)])]  # C2
    out = refinger(beats, C_STD, C_STD, semitone_shift=2)
    assert pitches(out.beats, C_STD)[0] == [note_to_midi("D2")]
