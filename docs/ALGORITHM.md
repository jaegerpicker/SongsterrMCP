# Transposition & Re-Fingering Algorithm

## Problem statement

Given a tab written for tuning **S** (source) with *m* strings, produce an equivalent
tab for tuning **T** (target) with *n* strings, such that every note sounds at the same
absolute pitch (or shifted by a chosen interval), and the resulting fingering is
physically playable and idiomatic.

This is *not* string-to-string substitution. Two tunings with different interval
structures (e.g. 6-string C standard vs. strings 7–2 of a B-standard 7-string, where
the major third sits between different string pairs) cannot be mapped shape-for-shape.
The only invariant that survives any tuning change is absolute pitch, so the engine
round-trips through pitch space:

```
(string, fret) --src tuning--> MIDI pitch --(+shift)--> candidate (string, fret) set on target
```

## Pipeline

### 1. Decode
For each note: `pitch = src_tuning[string] + fret`. Tunings are stored low→high as
MIDI numbers; Guitar Pro's high-to-low string numbering is flipped at the I/O
boundary only (`gp_io._flip`).

### 2. Optional key shift
`semitone_shift` is applied in pitch space, before re-fingering. Tuning changes and
key changes are therefore the same operation with different parameters — transposing
Dragonaut from C standard to B standard *at pitch* is `shift=0`; playing it a half
step down "as if the 7-string were the original instrument" is `shift=-1`.

### 3. Range repair
Pitches below the target's lowest open string or above `lowest + max_fret` are
octave-shifted toward range and a warning is emitted. (C standard → B standard 7 never
triggers this; the reverse direction does, for anything on the low B below C2.)

### 4. Candidate generation (per note)
Every `(string, fret)` on the target with `target_tuning[string] + fret == pitch`,
`0 ≤ fret ≤ 24`. A pitch typically has 1–4 candidates on a 7-string.

### 5. Chord constraint solving (per beat)
Cartesian product of note candidates, filtered:
- all notes on **distinct strings**;
- fret span of fretted notes ≤ 4 (open strings exempt — this is the standard
  barre-reachability heuristic).

Survivors are scored statically — `2·span + 0.05·mean_fret − 0.5·open_count` — and
pruned to the best 24 per beat. Span dominates (unplayable stretches are worse than
anything); mild preference for low positions and open strings.

### 6. Same-string chains
Slides, hammer-ons, and pull-offs are only meaningful within one string. Pass 1
groups linked notes into chains; each chain is pinned to a single target string that
can reach *all* of its pitches (preferring the lowest position). If no single string
works, the constraint is dropped with a warning (the notes survive, the slide becomes
a shift). Bends and vibrato don't constrain string choice and pass through; **natural
harmonics do not survive re-fingering** in general (they live at fixed node frets)
and should be flagged — currently a known gap, see Limitations.

### 7. Sequence optimization (beam search)
Fingering the whole piece is a shortest-path problem: nodes are per-beat fingering
combos, edge weight is hand-movement cost between consecutive beats:

```
move = |fret_center(cur) − fret_center(prev)|      (open strings excluded from center)
cost = move                    if move ≤ 4
     = move + 1.5·(move − 4)   otherwise           (position jumps punished superlinearly)
```

Exact DP over all combos is feasible but wasteful; a beam of width 16 over
statically-pruned combos is effectively optimal for real tabs (candidate sets are
tiny) and keeps worst-case cost linear in song length.

### 8. Re-encode
Winning combos are written back into the beat model, then into the Guitar Pro track
with the new string set (`gp_io.write_beats`). ASCII rendering is available for
quick inspection and for LLM-readable output over MCP.

## Known limitations / roadmap

- **Contour preservation.** The cost function optimizes ergonomics, not idiom. Given
  F2 after a low-string chug run, it may choose E-string fret 1 over B-string fret 6 —
  same pitch, easier reach, but it leaves the chug string and changes timbre (thicker
  string, different pick attack). Fix: add a term rewarding *relative string contour*
  similarity to the source (`penalty · |Δ(string rank)|`), exposed as a
  `preserve_contour` weight. For doom/stoner material you want this turned up.
- **Natural harmonics** need detection and either remapping to valid node frets for
  the new string or conversion to fretted notes + warning.
- **Voice 2 / multi-voice measures** are ignored (first voice only).
- **Capo semantics** aren't modeled; a `capo` parameter is a trivial extension
  (offset target frets during candidate generation).
- **Left-hand fingering** (which finger, not just which fret) is out of scope; the
  span heuristic stands in for it.

## Why not shape mapping with special cases?

Tempting when the tunings are a half step apart, but it breaks exactly where it's
least visible: any tuning pair with different interval structure has at least one
string where shapes silently produce wrong intervals (the G string in the
C-std→B-std-7 case is *identical* while every other string shifts — a uniform
"+1 fret" rule corrupts every lick that touches it). Pitch-space round-tripping has
no special cases and is equally correct for exotic targets (drop tunings, 8-string,
bass).
