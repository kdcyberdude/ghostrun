# Record a demo people can verify

The Mario rebuild and published players demonstrate the research behind GhostRun. They do not establish that the Hermes plugin rebuilt Mario in one unattended run. The plugin's recorded 28-tool integration test uses a generated cartridge. Keep these demonstrations labelled separately.

## Published showcase

The [70-second demo](https://github.com/kdcyberdude/ghostrun-arcade/releases/tag/v0.2.0-demo) includes native recordings, actual Hermes builder initialization, an experimental first-level 3D preview and a same-input 2D/3D clip. Its attached provenance identifies each source and the soundtrack. [Play the public 2D game](https://kdcyberdude.github.io/ghostrun-arcade/) and see [current verification and limitations](https://github.com/kdcyberdude/ghostrun-arcade/blob/main/docs/VERIFICATION.md).

The public release is 2D only. Recovered 3D code and assets are preserved on [a separate preview branch](https://github.com/kdcyberdude/ghostrun-arcade/tree/codex/recovered-3d-preview) for later work. The combined development build passed 1,131 tests and production interface checks. A 900-frame comparison preserves simulation state and 15 audio events across both renderers. A full replay of the fixed native route currently fails after reaching 1-2, so these clips are not presented as a native-equivalent 32-level browser clear.

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
