# Training: how the player learns, and why

The rebuild needs a player that can reach every part of the game. This page covers how GhostRun trains one, which choices were tried and dropped, and the bugs that cost the most time.

All numbers come from local runs on one RTX 5090. The game used for most of them is a 32-level NES platformer.

## The policy

| Part | What it is | Why |
|---|---|---|
| Input | 4 consecutive full frames, 240×224, FCEUX palette colours | 8 of the 12 games flicker or animate on 2-frame cycles in 14 to 79% of moments. Merged or downscaled frames lost them |
| Stem | Learned 2×2, stride 2 | Cheap downsampling the network chooses itself |
| Encoder | Impoola CNN: IMPALA ResNet (32/64/64 channels) with global average pooling | Proven on pixel RL, small, fast |
| Extra inputs | Previous move, controller dropout timeline, mood | The policy knows what it just pressed and which inputs were dropped |
| Body | 2 SimBa blocks (residual LayerNorm MLP, 512 wide) | Stable scaling of the dense layers |
| Memory | GRU of 512 | Memory comes from recurrence, not from stacking more frames |
| Action | Ordered masked heads: d-pad (9), then A (3), B (3), Start (2), Select (2) | Each part sees the parts already chosen. Masks block buttons a game doesn't allow, such as Start, which pauses |
| Value | HL-Gauss: 101 bins over [-10, 10] on per-game normalised returns | Classification-style value loss is more stable than regression when return scales differ |

Size: 6.33M parameters. File: `engine/rl/model.py`.

**No RAM, game id or reward reaches the actor.** RAM is read only to compute the reward. That stops the policy exploiting memory, and lets the same player later drive a rebuild that has no NES RAM.

## Recurrent PPO

Defaults from `engine/rl/train.py`:

| Setting | Default | Notes |
|---|---|---|
| Rollout length T | 128 decisions | Also the training sequence length for the GRU |
| Epochs, minibatch | 2, 16 envs × T | |
| Learning rate | 2.5e-4, Adam eps 1e-5 | |
| γ, λ, clip | 0.995, 0.95, 0.2 | The latest platformer run used γ 0.999 and λ 0.99 |
| Entropy, value, grad norm | 0.01, 0.5, 0.5 | |
| Advantage normalisation | per game, then per minibatch | Games' return scales differ about 60× |
| Return statistics | EMA, β 0.995, per game | |
| Precision | bf16 where supported | |

The horizon matters. With T 64 the GRU trained on 4.27 s of play and the reward half-life was 9.22 s. T 128 with γ 0.999 gives 8.53 s and 46.19 s, enough to plan across a long room.

Episodes that end by game over, win, level skip or stall are terminal. A rollout cut by the trainer is a truncation and is bootstrapped.

Resume is exact: environments, RNG, optimizer, GRU state and counters. See [Reliability](RELIABILITY.md#exact-resume).

Through the plugin, unchanged training arguments resume that state. Changed arguments fork a checkpointed run into a new version using its latest weights and fresh environment/optimizer state, preserving the previous run. Keep the model architecture compatible with those weights. This allows measured sampling changes without pretending they are reward fixes.

## Exploration

Three mechanisms, all off by default and switched on per run.

| Mechanism | File | How it works |
|---|---|---|
| Novelty (curiosity) | `engine/rl/novelty.py` | RND on the newest frame's luminance, pooled 4×4 to 56×60. Bonus = `int_coef` × the positive part of the per-game standardised prediction error |
| Diversity modes ("moods") | `engine/rl/diversity.py` | K random moods, one per episode, given to the policy as input. A judge (MLP, 128 hidden) guesses the mood from cumulative reward parts, time and game, never pixels or buttons. Bonus = `div_coef` × (log q(mood) + log K), DIAYN style |
| Quality gate | `engine/rl/diversity.py` | A mood only earns the bonus while its return is within 10% of the best mood's. Diversity can't be bought by playing badly |
| Failure-weighted level starts | `engine/rl/level_plan.py` | Each level's clear rate r = (clears + 0.5) / (visits + 1), decayed 0.98 per rollout. New episodes start at saved level entrances with probability proportional to 1 − r |

Level starts are saved by the environment itself when the reward fires a level event. Test plays always start from power-on.

## Old model and new model

There are two players. They answer different questions.

| | Old model | New model |
|---|---|---|
| Method | Demonstrations, then online PPO and supervised refinement | Recurrent PPO from scratch, no demonstrations |
| Input | 4 frames at 128×128, last 128 actions | 4 full frames, previous move, mood |
| Output | 10 independent button bits | Ordered masked heads |
| Memory | Action history | GRU 512 |
| Exploration | None beyond PPO sampling | Novelty, 8 moods, failure-weighted level starts |
| Training | 74.24M expert samples, 264,192 PPO samples, 149,042 updates | 436,862,976 decisions at iteration 2913 |
| Result | **All 32 levels in order, 3 of 3 fresh greedy games**, 10,626 decisions each | Clears recorded during training up to 8-3 from saved starts. 0 of 8 greedy clears from the 4-4 entrance at iteration 2913 |
| Weakness | Little diversity: deterministic starts, so repeats show consistency only. 0 of 3 wins with input noise, 0 of 3 on the recovery screen | Not fully trained. Mood judge accuracy 0.139 against 0.125 chance, so moods barely differ |

The old model is the proof that a pixel-only player can carry a complete route through a 32-level game. Its route drove the earlier rebuild. Its weakness is that one route shows one way to play.

The new model is built to show many ways to play from no demonstrations, on any game with a reward reader. That is what a rebuild needs for held-out coverage. It isn't there yet.

Sources: `docs/MARIO_REPRODUCIBILITY.md` and `reports/resume-20261031/standard-goal-closeout.json` for the old model; the run metrics and `reports/rl-44-trial-20261111/` for the new one, in the research repository.

## Speed

| Measurement | Value |
|---|---|
| Decisions per second, 8,192 envs | about 9,000 to 9,700 |
| After T 64 | about 8,100, 15 GB VRAM |
| Iteration 2913, T 128 | 7,457 decisions/s, MFU 22.3%, 397 W |
| Limit | The learner step caps the loop at about 14,400 decisions/s. Rollout and learning were both near 100% busy and the card was power-capped |

One GPU optimisation pass cached reset snapshots. Rollout time fell from 5.5 s to 4.4 s and throughput rose from 8.4–9.1k to 9.0–9.7k decisions/s.

## Alternatives considered and rejected

| Option | Why not |
|---|---|
| CPU emulators (stable-retro, FCEUmm) | 1.04k to 1.14k full RL steps/s per process. 32 processes reached 24.4k steps/s and left nothing for the learner. NeSLE on the GPU removes the host copy |
| PufferLib | Dropped. Model and PPO code come from the MIT-licensed Impoola repository instead |
| RAM as a policy input | The policy would learn memory shortcuts, and could never drive a rebuild |
| 2 merged max-frames at 128×120 | Loses flicker and 2-frame animation. Replaced with 4 exact frames at full size |
| A vision-language model as the player | An earlier line fine-tuned a VLM to play through FCEUX. Its final campaign recorded 0 verified wins. A compact pixel policy was then authorised and is what worked |
| Overlapping the next rollout with learning | +1% only. Left off |
| Splitting each game's envs into 2 streams | No measured gain |
| A maze-specific reward | Game knowledge that doesn't scale to other games |
| Go-Explore "places" (mid-level restarts from an archive) | Tried, then switched off. 98.3% of resets started mid-level, 1,759 of 2,048 archive slots belonged to levels outside the focus, and no greedy clear improved on 4-4, 7-4, 8-3 or 8-4. Not shipped in the plugin |

## Bugs that mattered

Each one looked like a learning problem. Most were reward or measurement bugs.

| Symptom | Cause | Fix |
|---|---|---|
| Fast, stable training, flat gameplay. Entropy rose from 3.68 to 4.16, at 85–97% of maximum | Return scales differed about 60× between games (std 0.004 to 0.24). Quiet games got tiny gradients against the same entropy bonus | Per-game advantage normalisation, now the default |
| Greedy player crouched all game. Stopped at 30.93M decisions | A death cost −1.0. Running right scored −6.14, crouching −0.55 | Death −0.1 and a −0.1 stall end. Running right then scored +0.50, crouching −0.09 |
| Every mood took the same pipe | Mood inputs started at zero weight, so moods played alike and the judge had nothing to reward. Judge accuracy 0.129–0.144 against 0.125 | One-time random kick to the mood weights, and a 10× larger diversity coefficient |
| 1-1 recorded 99.7% cleared while test plays cleared 0 of 16 | Clears were counted at game end, up to 80 minutes late | Count at the moment of the clear |
| Greedy stalled 8 of 8 in 1-1 while sampled play cleared 15 of 16 | Greedy and sampled play differ, and only sampled was being watched | Test both, separately |
| Long freezes in test plays | A held A button doesn't start a new jump. One freeze held A 98% of 54 s | A small waiting cost, −1.8 over a whole stall limit |
| Late collapse: explained variance fell from 0.98 to 0.2–0.8, clears fell from 413 to 122 of about 512 | A page counter read unsigned. A wrong turn in a maze castle took it from 3 to 255 and paid +21.5 levels in one step | Read it signed. Resume from the best measured weights with a fresh optimizer |

The last bug took two days to find by hand. The [training watcher](TRAINING_WATCHER.md) now flags its signature about 600 iterations earlier, and [reward lint](REWARDS.md#tools) catches the jump before training starts.

## What isn't proven

- Saved level starts improve final win rate.
- Moods produce different strategies. The judge is barely above chance.
- The new model completes the 32-level game from power-on.
- A policy trained on the original plays well on a rebuild.
