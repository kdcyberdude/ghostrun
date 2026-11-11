# GhostRun

**Recreate NES games as browser games you can play and change.**

GhostRun gives Hermes the tools to learn how a game plays, rebuild its levels and mechanics, and check the result against the original. Start with a 2D recreation, then change the levels, difficulty or look—including a 3D version.

**[Watch the film](https://kdcyberdude.github.io/ghostrun-arcade/film/)** · **[Play Mario](https://kdcyberdude.github.io/ghostrun-arcade/)** · **[Game source](https://github.com/kdcyberdude/ghostrun-arcade)**

The film introduces GhostRun through our Mario recreation, with gameplay and a first-level 3D preview.

Writing a playable scene is easier than reproducing a whole game's physics, enemies and level transitions. GhostRun gives the agent a reference it can test: a trained player to explore the game, and a black box it can ask "if I press this, what happens next?"

## What it does

| | Stage | What happens |
|---|---|---|
| 🧠 | **Understand** | The agent reads the game's RAM while it plays and writes a reward function, then has to prove it against what's on screen. |
| 🎮 | **Learn to play** | A pixel-only policy trains on thousands of NES consoles running on one GPU. |
| 🩺 | **Self-correct** | A watcher checks training in the background. If the reward is wrong, the agent debugs it, fixes it, proves the fix and resumes. |
| 🔒 | **Black box** | The trained player goes behind a socket. Actions in, frames out. |
| 🏗️ | **Rebuild** | A separate builder agent recreates mechanics from observation, with access to the reference restricted by the plugin's isolation hook. |
| ✅ | **Check it** | Per-frame traces and a regression gate that rejects changed reference traces or tolerances. |
| ✨ | **Upgrade** | The result runs at any resolution, in 2D or 3D, and it's real code you can extend. |

The 2D rebuild stays independently playable. An optional 2.5D or 3D version lives alongside it with separate renderer code, assets, build outputs and launch commands. Both may share gameplay simulation code; adding 3D must preserve the 2D version.

## Why it's useful

- **Preserve and remaster.** Old games become readable code, checked frame by frame, that runs at 4K or in 3D.
- **Test games automatically.** Replay a player's routes and catch regressions in the measured behaviour.
- **Mod and remix.** Levels, difficulty and accessibility become code changes, not ROM hacks.
- **Rebuild anything you can only observe.** The oracle pattern fits legacy UIs and firmware, not just games.
- **Learn from it.** Reward design, CUDA emulation and recurrent PPO in one small, working codebase, with the real bugs written up.

More in [Applications](docs/APPLICATIONS.md).

## Why a plugin

A prompt can't do this. GhostRun adds things only a plugin can:

- a CUDA training environment and a resumable trainer
- a background watcher that costs no tokens while training is healthy
- a hook that stops builder sessions reaching the game
- a stage ledger that survives crashes and context loss

## What runs on your computer

- **GPU environment:** includes the parallel rollout environment, reward code and trainer. Setup fetches a pinned NeSLE revision, applies the included emulator extensions, and compiles locally with `git`, `nvcc`, `c++` and your configured Python. It uses `nvidia-smi` to check GPU use. The same patch is published as a NeSLE fork at [kdcyberdude/NeSLE](https://github.com/kdcyberdude/NeSLE), branch `ghostrun`. See [GPU environment](docs/GPU_ENGINE.md).
- **Files:** reads the ROM you provide and stores training files and rebuilt games in the configured folders.
- **Background work:** its tools can start GPU training, a local service that runs the reference game, and a training watcher. The watcher can wake the agent to edit the game's reward function and restart training, with a limit of three fixes per game.
- **Privacy:** no telemetry or stored credentials.

See [the full disclosure](CATALOG.md) for details.

## Install

Install from [kdcyberdude/ghostrun](https://github.com/kdcyberdude/ghostrun), or follow [Contributing](CONTRIBUTING.md#local-checks) for a local source checkout:

```bash
hermes plugins install kdcyberdude/ghostrun
hermes plugins enable ghostrun
```

The short catalog command, `hermes plugins install ghostrun`, becomes available after the Hermes catalog entry is accepted.

Training needs an NVIDIA GPU with CUDA and a Python with [`requirements-runtime.txt`](requirements-runtime.txt) installed. Point the plugin at it with the `python` setting.

## Use it

New runs use two parallel branches: improve the learned player, and provisionally recreate the observed scenes from that player’s actual inputs. A losing policy is valid provisional data; final completion requires successful learned coverage and matching independent gameplay. Requested 3D and recordings follow verified 2D. See [the recreation workflow and completion evidence](docs/RECREATION.md). A measured full-route completion check is separate from the regression gate.

Give Hermes a game ROM and ask:

> Use the ghostrun pipeline on `/path/to/game.nes`.

Check progress at any time with `/ghostrun <game>`.

## Test it

```bash
uv run --no-project --with-requirements requirements-dev.txt python -m pytest tests --ignore=tests/integration -q
```

The CPU unit suite runs without Hermes or a GPU. See [Contributing](CONTRIBUTING.md) for setup.

The end-to-end check runs all declared tools through a real Hermes install. Its docstring has the instructions: [`tests/integration/hermes_itest.py`](tests/integration/hermes_itest.py).

## Status

Early preview, developed from single-game research and a focused set of training and integration checks. Broad validation across a large game library is ongoing.

GhostRun builds on earlier single-game player and reconstruction work. This plugin brings reward discovery, GPU training, a training watcher, a black-box oracle and trace comparison into Hermes. The current training work extends that foundation across games and genres. See [Results](docs/RESULTS.md) for the single-game results, infrastructure measurements and ongoing experiments.

The Mario research project spans 32 levels. For measured results, supported workflows and current limitations, see [Results](docs/RESULTS.md) and [Reliability](docs/RELIABILITY.md).

## Code and trained players

- [Training lab](https://github.com/kdcyberdude/ghostrun-lab): trainer, 12 reward readers, configs, result tables and per-level recording scripts. Its README identifies additions beyond this plugin's bundled trainer.
- [Mario v1 player](https://huggingface.co/kdcyberdude/ghostrun-smb-policy-v1): demonstration-assisted player with a deterministic route through all 32 levels.
- [Mario v2 player](https://huggingface.co/kdcyberdude/ghostrun-smb-policy-v2): partially trained recurrent policy with eight moods; it does not complete the game from power-on.
- [NeSLE extensions](https://github.com/kdcyberdude/NeSLE/tree/ghostrun): the published mapper, renderer and timing changes used by the GPU environment.

Model cards describe checkpoints, evaluation conditions and limitations. The repositories contain no game ROMs. See the [demo evidence guide](docs/DEMO.md) for recording and comparison requirements.

## Repository layout

```text
ghostrun/
├── plugin.yaml             # Hermes manifest
├── __init__.py             # Plugin entry point
├── core/                   # Pipeline tools and durable state
├── engine/                 # GPU trainer, rewards and emulator integration
├── skills/                 # Agent workflows
├── tests/                  # Unit and Hermes integration checks
├── docs/                   # Architecture, results and guides
└── .github/                # CI and PR template
```

The entry point and manifest stay at the root for Hermes discovery. Training outputs and rebuilt games live in separate configured folders.

## Learn more

Not sure where to look? Start with the [question index](docs/INDEX.md).

- [Architecture: how it works and why](docs/ARCHITECTURE.md)
- [Rewards: discovered from RAM, proven against the screen](docs/REWARDS.md)
- [Training: the policy, exploration and the bugs that mattered](docs/TRAINING.md)
- [Reliability: what guarantees what, and what isn't validated](docs/RELIABILITY.md)
- [Training watcher and self-repair](docs/TRAINING_WATCHER.md)
- [Running unattended: approvals, subagents and long runs](docs/UNATTENDED.md)
- [GPU environment](docs/GPU_ENGINE.md)
- [Lessons: what to do and what not to do](docs/LESSONS.md)
- [Results](docs/RESULTS.md)
- [What else this enables](docs/APPLICATIONS.md)
- [What this plugin does on your machine](CATALOG.md)
- [Contributing](CONTRIBUTING.md)
- [Publishing to GitHub and submitting the catalog PR](docs/PUBLISHING.md)
