"""Pitch-preserving re-fingering between tunings / string counts.

The engine works on a tuning-agnostic model (Note/Beat) rather than on
Guitar Pro objects directly; gp_io adapts to and from pyguitarpro.

Pipeline (see docs/ALGORITHM.md for the full write-up):
  1. Decode: (string, fret) + source tuning -> absolute MIDI pitch.
  2. Optional semitone shift (actual key changes, not just tuning moves).
  3. Candidate generation: every (string, fret) on the target tuning that
     produces the pitch, per note; combined per beat with playability
     constraints (distinct strings, bounded fret span).
  4. Beam search across the beat sequence minimizing hand movement,
     preferring open strings and low positions, and respecting
     same-string constraints for slides/legato chains.
  5. Emit warnings for anything unplayable (octave-shifted as a fallback).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace

MAX_FRET = 24
CHORD_SPAN = 4          # max fret span within one beat (open strings exempt)
BEAM_WIDTH = 16
COMBOS_PER_BEAT = 24

# Effects that chain a note to the *next* note on the same string.
SAME_STRING_EFFECTS = {"slide", "hammer", "pull"}


@dataclass(frozen=True)
class Note:
    """One played note. `string` is a low->high index into the tuning."""
    string: int
    fret: int
    effects: frozenset[str] = frozenset()
    tie: bool = False


@dataclass
class Beat:
    notes: list[Note]
    duration: int = 4          # denominator-style (4 = quarter), opaque to the engine
    dotted: bool = False
    rest: bool = False
    meta: dict = field(default_factory=dict)  # round-trip payload for gp_io


@dataclass
class RefingerResult:
    beats: list[Beat]
    warnings: list[str]


def _pitch(note: Note, tuning: list[int]) -> int:
    return tuning[note.string] + note.fret


def _candidates(pitch: int, tuning: list[int], max_fret: int) -> list[tuple[int, int]]:
    """All (string, fret) positions producing `pitch` on `tuning`."""
    out = []
    for s, open_pitch in enumerate(tuning):
        f = pitch - open_pitch
        if 0 <= f <= max_fret:
            out.append((s, f))
    return out


def _combo_cost(combo: tuple[tuple[int, int], ...]) -> float:
    """Static playability cost of one beat fingering."""
    fretted = [f for _, f in combo if f > 0]
    span = (max(fretted) - min(fretted)) if len(fretted) > 1 else 0
    height = sum(fretted) / len(fretted) if fretted else 0.0
    open_bonus = -0.5 * sum(1 for _, f in combo if f == 0)
    return span * 2.0 + height * 0.05 + open_bonus


def _beat_combos(
    pitches: list[int],
    tuning: list[int],
    max_fret: int,
    pinned: dict[int, int],
) -> list[tuple[tuple[int, int], ...]]:
    """Playable fingerings for one beat.

    pinned: note index -> forced string (legato/slide chain constraints).
    """
    per_note: list[list[tuple[int, int]]] = []
    for i, p in enumerate(pitches):
        cands = _candidates(p, tuning, max_fret)
        if i in pinned:
            cands = [c for c in cands if c[0] == pinned[i]]
        if not cands:
            return []
        per_note.append(cands)

    combos = []
    for combo in itertools.product(*per_note):
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue
        fretted = [f for _, f in combo if f > 0]
        if len(fretted) > 1 and max(fretted) - min(fretted) > CHORD_SPAN:
            continue
        combos.append(combo)
    combos.sort(key=_combo_cost)
    return combos[:COMBOS_PER_BEAT]


def _center(combo: tuple[tuple[int, int], ...], prev: float) -> float:
    fretted = [f for _, f in combo if f > 0]
    return sum(fretted) / len(fretted) if fretted else prev


def _transition_cost(prev_center: float, combo) -> float:
    center = _center(combo, prev_center)
    move = abs(center - prev_center)
    # Big position jumps hurt more than linearly.
    return move + (move - 4) * 1.5 if move > 4 else move


def refinger(
    beats: list[Beat],
    src_tuning: list[int],
    dst_tuning: list[int],
    semitone_shift: int = 0,
    max_fret: int = MAX_FRET,
    beam_width: int = BEAM_WIDTH,
) -> RefingerResult:
    """Re-finger `beats` from src_tuning onto dst_tuning, preserving pitch
    (plus optional semitone_shift). Returns new beats + warnings.
    """
    warnings: list[str] = []
    lo, hi = min(dst_tuning), max(dst_tuning) + max_fret

    # ---- Pass 1: pitches, range fixes, and same-string chain pinning ----
    beat_pitches: list[list[int]] = []
    # chains[i] = list of (beat_idx, note_idx) groups that must share a string
    pin_groups: list[list[tuple[int, int]]] = []
    open_chain: dict[int, list[tuple[int, int]]] = {}  # src string -> group

    for bi, beat in enumerate(beats):
        pitches = []
        for ni, note in enumerate(beat.notes):
            p = _pitch(note, src_tuning) + semitone_shift
            if p < lo or p > hi:
                shift = 12 if p < lo else -12
                while p < lo or p > hi:
                    p += shift
                warnings.append(
                    f"beat {bi}: pitch out of range on target tuning; "
                    f"octave-shifted ({'+' if shift > 0 else ''}{shift})"
                )
            pitches.append(p)

            # Chain bookkeeping: a slide/hammer/pull links this note to the
            # next note on the same source string.
            if note.string in open_chain:
                open_chain[note.string].append((bi, ni))
                if not (note.effects & SAME_STRING_EFFECTS):
                    pin_groups.append(open_chain.pop(note.string))
            elif note.effects & SAME_STRING_EFFECTS:
                open_chain[note.string] = [(bi, ni)]
        beat_pitches.append(pitches)
    pin_groups.extend(open_chain.values())

    # Resolve each chain to a single target string all its pitches can reach.
    pinned: dict[tuple[int, int], int] = {}
    for group in pin_groups:
        if len(group) < 2:
            continue
        pitches = [beat_pitches[bi][ni] for bi, ni in group]
        viable = [
            s for s in range(len(dst_tuning))
            if all(0 <= p - dst_tuning[s] <= max_fret for p in pitches)
        ]
        if not viable:
            warnings.append(
                f"beats {group[0][0]}–{group[-1][0]}: legato/slide chain has no "
                f"single-string mapping on target tuning; constraint dropped"
            )
            continue
        # Prefer the lowest playable position.
        best = min(viable, key=lambda s: max(p - dst_tuning[s] for p in pitches))
        for key in group:
            pinned[key] = best

    # ---- Pass 2: beam search over per-beat fingerings ----
    # state: (cost, combo_per_beat_so_far..., center) — we only keep tails.
    States = list[tuple[float, float, list[tuple[tuple[int, int], ...]]]]
    states: States = [(0.0, 2.0, [])]  # cost, hand center (start ~2nd fret), history

    for bi, pitches in enumerate(beat_pitches):
        if not pitches:  # rest
            for st in states:
                st[2].append(())
            continue
        beat_pins = {ni: s for (b, ni), s in pinned.items() if b == bi}
        combos = _beat_combos(pitches, dst_tuning, max_fret, beat_pins)
        if not combos:
            # Retry without pins as a last resort.
            combos = _beat_combos(pitches, dst_tuning, max_fret, {})
            if combos:
                warnings.append(f"beat {bi}: dropped same-string constraint to stay playable")
        if not combos:
            warnings.append(f"beat {bi}: unplayable on target tuning; notes dropped")
            for st in states:
                st[2].append(())
            continue

        next_states: States = []
        for cost, center, hist in states:
            for combo in combos:
                c = cost + _combo_cost(combo) + _transition_cost(center, combo)
                next_states.append((c, _center(combo, center), hist + [combo]))
        next_states.sort(key=lambda s: s[0])
        states = next_states[:beam_width]

    best = min(states, key=lambda s: s[0])[2]

    # ---- Pass 3: rebuild beats ----
    out_beats: list[Beat] = []
    for beat, combo in zip(beats, best):
        new_notes = [
            replace(note, string=s, fret=f)
            for note, (s, f) in zip(beat.notes, combo)
        ]
        out_beats.append(Beat(new_notes, beat.duration, beat.dotted, beat.rest, beat.meta))
    return RefingerResult(out_beats, warnings)
