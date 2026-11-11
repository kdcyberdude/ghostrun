# Recreation from one ROM

Start a new Hermes chat: `Use ghostrun to recreate /path/to/game.nes in 2D and then 3D, and record both.`

`ghostrun_init` defaults to `recreate`: preserve observed level geometry, collectible placement, rules and progression, using independently written simulation and matching reconstructed assets. The goal is visually indistinguishable 2D play apart from negligible differences with no gameplay effect. Do not substitute a new maze, new rules, one-level scope or a search player for requested training. `mechanics` remains an explicit remix option. `faithful` is for importing prepared licensed assets; independent recreation does not require that import mode. Never extract ROM maps, tables or code.

Discover and verify the reward, train and evaluate the policy, measure gameplay observables, iterate on full routes, then build 3D with the same simulation. A trained policy need not win immediately: the agent diagnoses, resumes training and reports measured policy coverage. Search may help test rewards or explore, but is not proof a policy learned to play. Honor user budgets and report incomplete when exhausted.

Before the oracle stage, verify numeric observations for player and every enemy, modes/timers, score, lives, progression and ending. Discover these from controlled play and RAM/screen correlation. Missing observations are work for the reference agent; the builder must not guess them and call the game verified. Use `step` with `{"buttons":["LEFT"],"frames":240,"per_frame":true}` to receive every frame in one request. Include the reset observation as frame zero. No ROM, RAM dumps or map tables cross the oracle.

## Completion manifest

Use `ghostrun_recreation_check(slug, manifest)` throughout the loop. Paths are relative to the manifest. For each requested level include distinct clear, fresh heldout clear, and death/recovery input routes. Reference, independently simulated rebuild, and a repeated reference run must contain contiguous `f` values starting at zero, identical `buttons`, and all declared numeric fields on every frame. `terminal: 1` denotes the scoped ending. The repeat checks whether reset and inputs reproduce randomness. Statistical-only randomness evidence needs separate review and cannot claim exact trajectory completion.

```json
{
  "levels": ["first-maze"],
  "cases": ["clear", "heldout", "death-recovery"],
  "fields": {
    "player": {"player_x": 2, "player_y": 2},
    "enemies": {"ghost0_x": 2, "ghost0_y": 2},
    "rules": {"score": 0, "power_active": 0, "pellets_remaining": 0},
    "outcome": {"lives": 0, "terminal": 0}
  },
  "randomness": "reproduced-from-reset",
  "unresolved": [],
  "routes": [
    {"level":"first-maze", "kind":"clear", "reference":"clear.ref.jsonl", "rebuild":"clear.new.jsonl", "repeat":"clear.repeat.jsonl"},
    {"level":"first-maze", "kind":"heldout", "reference":"heldout.ref.jsonl", "rebuild":"heldout.new.jsonl", "repeat":"heldout.repeat.jsonl"},
    {"level":"first-maze", "kind":"death-recovery", "reference":"death.ref.jsonl", "rebuild":"death.new.jsonl", "repeat":"death.repeat.jsonl"}
  ]
}
```

This example is not sufficient enemy coverage: declare every ghost and its modes and relevant mechanics. The reference agent and parent review the checklist against the actual game, confirm routes reach the stated endings, and inspect rendered behaviour. Small numeric bounds never excuse a collision or outcome change. The checker verifies supplied evidence, not that every possible input has been tested or that the agent declared every mechanic. Never fabricate traces, inject reference state or hide gameplay behind a fixture.

For recreate mode, passing the `gate` stage requires the completion manifest path as `evidence`; a prose claim or local regression PASS cannot pass it. Existing mechanics/faithful ledgers retain their previous stage sequence.

## 3D delivery

Create procedural mesh assets and an independently launchable 3D build alongside 2D. Record both complete playthroughs. Pass the `visual3d` stage with a delivery JSON path as evidence:

```json
{
  "recreation": "completion.json",
  "route_reference": "clear.ref.jsonl",
  "simulation": "headless.jsonl",
  "render2d": "2d.jsonl",
  "render3d": "3d.jsonl",
  "assets3d": "assets3d/kit.mjs",
  "build2d": "dist2d/index.html",
  "build3d": "dist3d/index.html",
  "video2d": "videos/2d.mp4",
  "video3d": "videos/3d.mp4",
  "video_original": "videos/original.mp4",
  "session_recording": "session.cast"
}
```

The parity traces must contain the same contiguous per-frame `f`, `state_hash` and `audio_events` rows from the actual three targets. The checker revalidates recreation, checks artifact presence and probes both videos with ffprobe. The parent must additionally launch both builds, check 2D runs without 3D assets, inspect recordings for complete play and assess 3D performance. A video existing alone does not prove completion. Capture the Hermes session from the launch with the host's terminal recorder and preserve the recording through continuation sessions.

## Prepared assets and builder context

Before starting the builder, prepare matching tiles, sprites, animations and audio from authorized observations or independent reconstruction. Never extract ROM code/maps/tables. Record every file in `assets/manifest.json`:

```json
{"files":[{"path":"sprites.png","source":"observed reset/play frames, capture set 1","method":"observed-frame","sha256":"<64-character file hash>"}]}
```

Allowed methods are `observed-frame`, `observed-audio`, `authored`. Include applicable notices/licences as files in the manifest. Use relative paths. All files must exist, be nonempty and match their SHA-256. Import with `ghostrun_assets_import`; then mark `assets` passed. Recreate builders are refused until a valid kit exists. Keep private ROM paths, RAM, emulator state and reward/training files out of the kit.

Launch the builder in a fresh context with its cwd set to the returned builder workspace. A subagent is optional; a separate Hermes session works too. Never use `cd` to pretend an existing reference conversation has forgotten its context. `ghostrun_builder_enter` rejects an already reference-marked session. When multiple builders fix independent bugs, give each separate files/worktrees, then merge and run every route again.

## Reference-pinned game contract

Before passing verify in recreate mode, write a JSON contract with `full_game: true`, a `scope_basis` explaining observed progression/ending and any repeating rule regimes, and the complete `levels`, `cases`, `fields`, `not_applicable` objects. Pass this path as verify evidence; the reference ledger pins it. The completion manifest must copy those four objects exactly, so builders cannot shrink scope or loosen limits. The sample first-maze manifest is a format example, not evidence that Pac-Man has only one maze or ghost. Declare every requested level/rule regime and all enemies/mechanics.

Use `cases: ["clear", "heldout", "death-recovery"]` when death/recovery exists. Otherwise omit that case and explain absence. Each of player/enemies/rules/outcome must have numeric fields or explicit absence evidence in `not_applicable`. For example, a falling-piece game can have `fields.enemies: {}`, `not_applicable.enemies: "No enemies in repeated controlled play"`, no lives field, and only clear/heldout routes to its defined ending. Do not fabricate observations to fit Pac-Man's mechanics. Every game must expose `terminal` for its declared ending. The parent reviews the full-game claim; the checker cannot independently prove the agent discovered every rule.

Delivery parity is tied to the accepted clear/heldout route selected by `route_reference`. All targets must cover its complete frame range, use its exact `buttons` each frame, contain nonempty `state_hash` and list-valued `audio_events`, and finish with `terminal: 1`. Videos must be at least the measured route duration (allowing half a second of container timing difference), not preview clips.

## Training acceptance

Pass explore in recreate mode with an evaluation JSON path as evidence. It contains `checkpoint`, its `checkpoint_sha256`, and at least two `plays` entries, each with `controller: "trained-policy"` and `trace`. Paths are relative to this evaluation file. Each trace must contain every frame from reset, list-valued applied `buttons`, numeric/string `level` identifiers matching all declared contract levels/regimes, and final `terminal: 1`. The reference agent must verify that this ending is the requested game ending and that the recorded controls came from that checkpoint's actual policy, not search or replay. Failed policies remain incomplete and return to diagnosis/training. Search routes cannot satisfy this stage.

Reference/repeat traces must retain raw oracle coordinates, numeric values and applied buttons. The completion tool and recreate stage transitions authenticate them against private oracle recordings; local fixtures or fabricated matching JSON cannot stand in for native play. Reset and every applied frame are recorded by the oracle. Collect new runs with this version before using the completion checker; older chunk-only logs cannot authenticate full routes.

A reference contract may be expanded with more levels, route cases or fields, or tighter tolerances. Its prior scope and limits cannot be removed or loosened. Expanding it preserves the prior contract/stage snapshot and resets downstream stages to pending, requiring new training coverage and comparisons.

Delivery also requires a complete original-game video (`video_original`) and the Hermes terminal recording (`session_recording`, asciinema v2). Record the original game through the reference process, including actual gameplay/audio; do not label a remake video as original. The default reference backend uses stable-retro's NES core; a video from it is not a recording of the separate FCEUX desktop application. If FCEUX itself is explicitly requested, capture that application separately. The terminal recording must contain actual output, not only an empty recording header.

## Visible 2D output

The completion manifest must also name `visual_route`, selecting a completed clear/heldout reference path, and `visuals`, at least three distinct frame pairs including reset and ending:

```json
{"visual_route":"clear.ref.jsonl","visuals":[
 {"f":0,"reference":"screens/native-0.png","rebuild":"screens/threejs-0.png"},
 {"f":100,"reference":"screens/native-100.png","rebuild":"screens/threejs-100.png"},
 {"f":200,"reference":"screens/native-200.png","rebuild":"screens/threejs-200.png"}
]}
```

Use actual route frame numbers. Native screenshots are authenticated against private oracle captures and numeric observations. Rebuild captures must come from the actual browser rendering driven by the same inputs, at native resolution without shifting, cropping or resizing to manufacture agreement. Fixed image bounds allow tiny color/edge variance but reject visibly different or blank output. These sampled checks supplement full per-frame numeric comparisons; the parent still inspects representative gameplay, animation and capture provenance.

For an explicit 2D-only request, omit 3D artifact/parity/video keys from delivery and mark `visual3d` `skipped` with that delivery manifest as evidence. The plugin still checks completed 2D recreation, 2D/hash/audio parity, original/2D videos and terminal recording. Never skip 3D when it was requested. Other stages cannot be skipped.

## Oracle readiness and exact policy inputs

The endpoint is pinned privately when the game is initialized and mirrored into the builder's `.oracle.json`; changing TMPDIR between processes does not create a second address. `ghostrun_oracle_start` must return `ready:true` after a real hello before a builder starts. Startup failures return the private server log and its error tail. Healthy servers from another session are reused without taking ownership; the tool does not stop unowned servers.

A recorded policy input route can be supplied as `{"decisions":[{"buttons":["RIGHT"],"frames":1},{"buttons":["UP"],"frames":7}]}` to `ghostrun_oracle_start`'s route argument. Apply these exact decisions to both games. This format does not translate policy outputs through a search action set. Preserve the checkpoint hash, evaluation provenance and measured boot/input alignment separately; replaying a trained policy's recorded decisions is not evidence that a search route was learned.

Oracle reset reports `boot_frames` separately from gameplay `frame: 0`. Use it when aligning a policy recording that includes power-on/controller boot frames; do not send boot inputs again to an already booted oracle. Verify the aligned reset image/state and preserve any additional neutral frames applied by the evaluator. Compare boot/title behaviour separately if it is part of the requested output; a gameplay route does not prove the title sequence matches.
