# Film and gameplay recordings

[Watch the GhostRun film](https://kdcyberdude.github.io/ghostrun-arcade/film/) — an 86-second introduction with narration, gameplay and a first-level 3D preview. The page has a built-in player and a download link.

[Play Mario](https://kdcyberdude.github.io/ghostrun-arcade/) — the interactive 2D browser game.

[Browse the game source](https://github.com/kdcyberdude/ghostrun-arcade) — Three.js code and local setup instructions.

[Download gameplay recordings](https://github.com/kdcyberdude/ghostrun-lab/releases/tag/gameplay-with-sound-20261112) — separate original-NES and Three.js clips with sound, plus capture metadata. These are recording archives, separate from the narrated film.

For engineering measurements and known differences, see [Reliability](RELIABILITY.md) and the arcade's [verification notes](https://github.com/kdcyberdude/ghostrun-arcade/blob/main/docs/VERIFICATION.md).

## Capture the plugin working

For a new game such as a single Pac-Man maze, save the Hermes transcript, plugin revision, commands, tool results, elapsed time and any human interventions. Record the initial workspace and final playable output. Report stages that failed or were skipped, including training, reward verification and the optional 3D upgrade. A montage of older research footage is useful context, but cannot stand in for this run.

For an under-90-second overview, use the actual successful stages: the initial request, a reward check, training or a clearly labelled existing checkpoint, an oracle interaction, a measured rebuild improvement and the playable result. Put detailed timings and failures in the accompanying run report. Show the same gameplay moment in 2D and 3D to make the visual upgrade clear.

## Reuse the recording tools

The [training lab](https://github.com/kdcyberdude/ghostrun-lab#record-the-mario-players-on-all-32-levels) already provides `scripts/record_all_levels.sh`. Its dry run checks inputs and writers without loading a model. The [existing v2 all-level recordings](https://github.com/kdcyberdude/ghostrun-lab/releases/tag/recordings-v2-20261111) are published with their action logs, all mood scores and a per-level audit (23 clears, 8 game overs, 1 capped attempt).

| Player | Recording method | Important limit |
|---|---|---|
| v1 | Record the full deterministic route in its nes_py reference, then cut by level | Uses fixed CPU-cycle slices; do not replay as PPU frames |
| v2 | Evaluate all eight moods from each saved entrance, retain clear first, then furthest x, then longest play | Later entrances are constructed training starts, not evidence of a continuous full-game run |

Keep each selected video with its action log, checkpoint hash, start state description, frame-clock convention and all mood scores. v2 selection is based on progress before duration, so standing still cannot win merely by producing a longer video. Saved entrances are required for per-level v2 runs and are not included in the public policy-only download.

## Compare the reference, 2D and 3D

Replay identical controller bytes using the corresponding initial state and clock. Check numeric state and transitions before assembling a side-by-side video. Preserve raw frames and report divergence; do not shift captures or splice different actions to make them agree. Matching 2D and 3D simulation proves renderer equivalence on those inputs, not fidelity to the original game.

A recording report should link the source revisions, model cards, action logs, selection results and comparison output. State separately which levels were reached from power-on, which were launched from saved entrances, and which were actually cleared.
