# What else this enables

GhostRun produces three things that didn't exist before: a reward that explains what a game values, a player that can reach every part of it, and a rebuild that is real, readable code. Each one is useful on its own.

| Use | Built on | Ready today? |
|---|---|---|
| Preservation | Rebuild, traces | Shown on one game |
| Remasters at 4K or in 3D | Rebuild, visual-upgrade skill | 2.5D shown, 60 fps at 4K |
| Accessibility and difficulty | Rebuild | Idea |
| Level editors and mods | Rebuild | Idea |
| Speedrun and QA tooling | Player, trace compare, gate | Tools exist |
| Teaching RL and emulation | Rewards, GPU environment | Code and docs exist |
| Reverse-engineering beyond games | Oracle, trace compare, isolation | Idea |
| Data for world models | Player, environment | Tools exist |
| Game-design research | Rewards, player, moods | Partly measured |

## Preserve games as behaviour, not just bytes

Source code for old games is often lost, and [87% of pre-2010 US games are out of print](https://gamehistory.org/study-explainer). An emulator keeps a game runnable. It doesn't explain it.

A rebuild does. Each mechanic is readable code, checked frame by frame against the original. The traces, the reward reader's address notes and the player's routes form a record of how the game actually behaves, which outlives any one emulator.

## Remasters at 4K and in 3D, with the original sound

Retro games run at 256×240. A rebuild is real code, so it can render at 2K, 4K or in 3D, and it runs anywhere a browser does.

The `visual-upgrade` skill adds a 2.5D or 3D renderer next to the 2D one. They share the same simulation, so the game plays the same. On the research rebuild, a 2.5D renderer matched the 2D game over 2,600 frames, including when each sound fires, and held 60 fps up to 4K. Music and effects stay on the frames they always played on.

## Studios recovering their own lost games

The strongest commercial use. [Nightdive](https://store.epicgames.com/news/system-shock-2-25th-anniversary-remaster-interview-stephen-kick) has rebuilt titles from retail discs, [Mega Cat remastered Backyard Baseball](https://techcrunch.com/2024/10/13/the-original-source-code-for-backyard-baseball-is-long-gone-mega-cat-studios-remastered-the-game-anyway) without its source, and fans spent about two years decompiling LEGO Island by hand.

GhostRun turns part of that work into a loop an agent can run: the oracle answers "what happens next?", and the gate says whether the rebuild got closer.

## Accessibility and difficulty remixing

Once timing and physics are code, they're settings. A rebuild could offer slower game speed, longer jump windows, more hit points or fewer enemies, without patching a ROM.

The reward reader already knows where the player is, how far through the level, and when a death is coming. That could drive narration or audio cues for blind and low-vision players. This is an idea we haven't built.

## Level editors and mods on real code

ROM hacking means editing bytes in place. A rebuild has level data as files and mechanics as functions. That makes a level editor a normal web feature, and a mod a normal pull request.

The trained player is a free playtester for new levels: if it can't finish one, something is probably wrong.

## Speedrun and QA tooling

A policy that reaches every level is a tireless tester, and replay comparison is a regression oracle. [EA](https://www.ea.com/seed/news/automated-game-testing-deep-reinforcement-learning) and Ubisoft have used RL for testing at AAA scale.

GhostRun already has the parts:

- **Coverage.** The player plays thousands of consoles at once, from failure-weighted level starts.
- **Regression.** `ghostrun_compare` finds the first frame where two builds differ, and `ghostrun_gate` fails a build that got worse.
- **Exploits.** Reward bugs found during training are often real game exploits: a counter that wraps, a pause that dodges a death.
- **Speedruns.** Exact action logs replay frame-perfect, and the player's pad files replay in FCEUX.

## Teaching RL and emulation

GhostRun is a complete, small, working example of things usually taught separately: reading a machine's memory, writing a reward, porting it to CUDA with exact parity, recurrent PPO from pixels, exploration, and self-repair when the reward is wrong. [Training](TRAINING.md) and [Rewards](REWARDS.md) list the bugs that were actually hit, which is often the most useful part for a student.

## A reward-design benchmark for agents

Can an agent work out what a game rewards just from memory and the screen? It's checkable, spans many genres, and has clear failure modes. Related work like [Eureka](https://arxiv.org/abs/2310.12931) shows LLM-written rewards can beat human ones. We didn't find prior work where an agent discovers rewards from raw NES RAM.

## Reverse-engineering legacy software from behaviour

Nothing in the oracle is specific to games. It takes inputs and returns observations, and refuses everything else. The same pattern fits any system whose source is lost but which still runs:

- **Legacy business UIs.** Record what a green-screen or desktop app shows after each keystroke, and rebuild it as a web app that's checked against the original screen by screen.
- **Embedded firmware.** Drive a device or its emulator with inputs, trace outputs, and rebuild the control logic, with the gate catching any behaviour change.
- **Clean-room work.** The isolation hook and folder split keep the builder away from the original, which is the shape a clean-room rewrite needs. The hook is a guard rail, not a legal boundary.

## Data for game-playing agents and world models

Every run yields exact actions, frames and ground-truth state. Datasets like NitroGen have to infer actions from video. Here they're known exactly.

The GPU environment produces about 9,000 decisions per second on one card, and moods are meant to vary how the game is played. Labelled, varied, action-conditioned video is what world models need.

## Game-design research

The reward reader turns a game into numbers: where progress stalls, where deaths cluster, which levels a learning player fails most. Failure-weighted level starts are, in effect, a difficulty map measured by a learner. The score budget showed how much of a game's score comes from progress and how much from farming.

## Teaching agents to act

Fast feedback, real-time control and long horizons make games good training for decision-making, with lessons that carry over to robotics-style control.
