# GhostRun

**Give Hermes a retro game. It works out how the game scores, trains a player on your GPU, then rebuilds the game in Three.js by watching that player, without ever seeing the game's code.**

<!-- DEMO VIDEO: paste the link or embed here (under 90 seconds) -->
> 🎬 **Demo video:** _coming soon_

Today's models can write a one-screen game. Multi-level games fall apart, because nothing tells the model how the real thing moves, scores or ends. GhostRun gives the agent that missing reference: a player that can reach every part of the game, and a black box it can ask "if I press this, what happens next?"

## What it does

| | Stage | What happens |
|---|---|---|
| 🧠 | **Understand** | The agent reads the game's RAM while it plays and writes a reward function, then has to prove it against what's on screen. |
| 🎮 | **Learn to play** | A pixel-only policy trains on thousands of NES consoles running on one GPU. |
| 🩺 | **Self-correct** | A watcher checks training in the background. If the reward is wrong, the agent debugs it, fixes it, proves the fix and resumes. |
| 🔒 | **Black box** | The trained player goes behind a socket. Actions in, frames out. |
| 🏗️ | **Rebuild** | A separate builder agent, with no route to the game, recreates its mechanics from observation. |
| ✅ | **Prove it** | Per-frame traces and a regression gate that can't be fooled by editing the evidence. |
| ✨ | **Upgrade** | The result runs at any resolution, in 2D or 3D, and it's real code you can extend. |

The 2D rebuild stays independently playable. An optional 2.5D or 3D version lives alongside it with separate renderer code, assets, build outputs and launch commands. Both may share gameplay simulation code; adding 3D must preserve the 2D version.

## Why it's useful

- **Preserve and remaster.** Old games become readable code, checked frame by frame, that runs at 4K or in 3D.
- **Test games automatically.** A player that reaches every level, plus a gate that fails any build that got worse.
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

Install from [kdcyberdude/ghostrun](https://github.com/kdcyberdude/ghostrun), or follow [Contributing](CONTRIBUTING.md#local-checks) for a local source checkout.:

```bash
hermes plugins install kdcyberdude/ghostrun
hermes plugins enable ghostrun
```

The short catalog command, `hermes plugins install ghostrun`, becomes available after the Hermes catalog entry is accepted.

Training needs an NVIDIA GPU with CUDA and a Python with [`requirements-runtime.txt`](requirements-runtime.txt) installed. Point the plugin at it with the `python` setting.

## Use it

Give Hermes a game ROM and ask:

> Use the ghostrun pipeline on `/path/to/game.nes`.

Check progress at any time with `/ghostrun <game>`.

## Test it

```bash
uv run --no-project --with-requirements requirements-dev.txt python -m pytest tests --ignore=tests/integration -q
```

The CPU unit suite runs without Hermes or a GPU. See [Contributing](CONTRIBUTING.md) for setup.

The end-to-end check runs all 28 tools through a real Hermes install. Its docstring has the instructions: [`tests/integration/hermes_itest.py`](tests/integration/hermes_itest.py).

## Status

Early preview, developed from single-game research and a focused set of training and integration checks. Broad validation across a large game library is ongoing.

GhostRun builds on earlier single-game player and reconstruction work. This plugin brings reward discovery, GPU training, a training watcher, a black-box oracle and trace comparison into Hermes. The current training work extends that foundation across games and genres. See [Results](docs/RESULTS.md) for the single-game results, infrastructure measurements and ongoing experiments.

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
- [GPU environment](docs/GPU_ENGINE.md)
- [Lessons: what to do and what not to do](docs/LESSONS.md)
- [Results](docs/RESULTS.md)
- [What else this enables](docs/APPLICATIONS.md)
- [What this plugin does on your machine](CATALOG.md)
- [Contributing](CONTRIBUTING.md)
- [Publishing to GitHub and submitting the catalog PR](docs/PUBLISHING.md)

<!-- MORE VIDEOS: training montage, watcher catching a bug, 2D vs 3D side by side -->
