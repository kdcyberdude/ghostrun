# Reward discovery must test learning, not just decoding

The supplied NES Pac-Man reader measures pellets eaten, level changes, score, death and game over. Its event audit and Python/CUDA parity pass. That proves event consistency, not a useful learning objective.

## What failed in this run

- The Hermes transcript contains no `ghostrun_watch_start` call and only one `ghostrun_train_check`: the repair loop was never started.
- The installed watcher calls the saved 15-iteration/five-evaluation run `healthy`. Its long-window learning checks do not produce an action for this early failure. The candidate watcher calls the same saved run `act`, naming three failed level-zero evaluations and penalty-dominated reward.
- No-progress cost is charged whenever pellet progress stays unchanged, including movement through an already-cleared corridor. The same cost applies while stationary. In a captured random-play episode audited every eight frames: 132 travel-without-pickup updates totalled -0.264; 56 stationary-without-pickup updates totalled -0.112. Each costs -0.002. Progress updates totalled +0.43958; deaths -0.3. Positions are screen-correlated observations, not proof that every travel step was useful. This audit cadence differs from the PPO engine's four frames per decision.
- Score shaping stops paying after the shared 0.2 per-level budget. With SCORE_UNIT=10 and the shared 0.02 coefficient, ten ordinary pellets exhaust it. The remaining pellets still pay task progress; they do not pay that score bonus.

These observations identify hypotheses, not a demonstrated winning reward. Blindly reducing idle cost can make avoiding death by waiting attractive again. A larger reward total under modified weights is not proof the player improved.

## Required loop

1. Verify the reader against independent screen events, score and end conditions. Check repeated deaths, new rounds, resets and numeric wrap. Keep unverified ending claims explicit.
2. Compare the reward of useful trajectories, necessary travel/backtracking, standing at a wall, loops and losing a life. Holding NOOP is not inherently stationary in an auto-moving game. Use captured motion/inputs to label behaviour.
3. Run `core/reward_diagnose.py GAME RAM.npy --stride 4` with the configured game Python and REWARD10_GAMES_ROOT for the bundled PPO engine (`kFramesPerDecision=4`). Check the actual environment's cadence instead of copying the eight-frame search/audit action duration. This reports actual rewards by observed progress/motion category; do not treat screenshots or total reward alone as a learning test.
4. Start monitored training. Successful plugin `train-start`/`fix-apply` now starts a one-minute watcher automatically. After repeated failed evaluations across several minutes, a penalty-dominated first-level policy wakes the training doctor. An undelivered wake is retried. A warning means diagnose; it does not authorize an unsupported reward change.
5. Inspect applied controls, movement, original score/pellets, visits, collisions, greedy versus sampled play, and reward components. Test one supported hypothesis. For a proven reader/calibration problem, use the existing bounded fix loop, changing the Python reader and CUDA port, then audit/balance/parity before restart. IDLE_SCALE is an existing per-game calibration knob; any candidate must still pass anti-waiting tests. Do not change PROGRESS_UNIT or SCORE_UNIT merely to inflate reward, and do not patch the reward shared by other games to fit one run.
6. For an input/trainer/exploration problem, repair that cause with its regression check rather than falsifying reward. Preserve the checkpoint, old evaluations and exact configuration. Bound experiments by the user's time/compute budget.
7. Evaluate frozen policies on held-out starts/seeds using raw task metrics. Same level reached after a reward change is now `inconclusive`, not evidence the fix worked. Keep training/diagnosis until actual requested-scope play is demonstrated; otherwise report incomplete. Provisional recreation may use authenticated losing policy trajectories in parallel with learning. Final acceptance still requires successful learned-policy coverage and recreation fidelity.

## Research grounding and limits

[Farama's Ms. Pac-Man documentation](https://ale.farama.org/environments/ms_pacman/) identifies collecting pellets while avoiding ghosts as the task. It describes Atari Ms. Pac-Man, not this NES ROM; its addresses, timing and action space must not be copied.

[Hybrid Reward Architecture](https://arxiv.org/abs/1706.04208) demonstrates reward decomposition on Atari Ms. Pac-Man. It supports testing component rewards, not a claim that a particular set of weights will solve every game.

[Ng, Harada and Russell](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf) show conditions for shaping to preserve optimal policies. Distance-to-goal shaping is a candidate only when the goal observations and potential are verified, loops/resets are handled, and Python/CUDA implementations agree. This patch does not introduce an untested shaping framework or claim a learned Pac-Man policy.
