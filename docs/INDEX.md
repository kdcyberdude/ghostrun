# Index: find the answer

Questions, and where the answer lives. Docs first, then skills and code.

## Start here

| Question | Answer |
|---|---|
| What is GhostRun, in one page? | [README](../README.md) |
| How do the stages fit together? | [Architecture](ARCHITECTURE.md#stages) |
| Why does it work at all? | [Architecture](ARCHITECTURE.md#why-it-works) |
| What has actually been achieved? | [Results](RESULTS.md) |
| What is it good for beyond rebuilding one game? | [Applications](APPLICATIONS.md) |
| What does it do on my machine? | [Catalog disclosure](../CATALOG.md) |
| How do I run the checks? | [Contributing](../CONTRIBUTING.md#local-checks) |
| How does the agent run the whole pipeline? | [`skills/pipeline/SKILL.md`](../skills/pipeline/SKILL.md) |

## Rewards

| Question | Answer |
|---|---|
| What does the reward pay for? | [Rewards](REWARDS.md#the-contract) |
| Why is the reward the same for every game? | [Rewards](REWARDS.md#one-reward-many-games) |
| How does the agent find the right RAM bytes? | [Rewards](REWARDS.md#how-a-reader-is-discovered), [`skills/reward-discovery/SKILL.md`](../skills/reward-discovery/SKILL.md) |
| How is the reward checked against the screen? | [Rewards](REWARDS.md#how-its-proven) |
| Why can't score farming win? | [Rewards](REWARDS.md#the-score-budget) |
| Which games have readers, and how verified are they? | [Rewards](REWARDS.md#the-12-games), `engine/scripts/reward10/reward_spec.json` |
| How do I know the GPU reward equals the Python one? | [Rewards](REWARDS.md#python-is-the-truth-cuda-must-match-exactly), [Reliability](RELIABILITY.md#reward-parity) |
| What do lint, audit and balance catch? | [Rewards](REWARDS.md#tools) |
| Where is a game's reader? | `engine/scripts/reward10/games/<slug>.py` |
| Where is the shared reward? | `engine/scripts/reward10/reward.py`, contract in `contract.py` |

## Training

| Question | Answer |
|---|---|
| What does the policy see and output? | [Training](TRAINING.md#the-policy), `engine/rl/model.py` |
| Which PPO settings, and why? | [Training](TRAINING.md#recurrent-ppo), `Config` in `engine/rl/train.py` |
| How does it explore? | [Training](TRAINING.md#exploration), `engine/rl/novelty.py`, `diversity.py`, `level_plan.py` |
| How do the old and new players differ? | [Training](TRAINING.md#old-model-and-new-model) |
| What was tried and dropped? | [Training](TRAINING.md#alternatives-considered-and-rejected) |
| Which bugs cost the most? | [Training](TRAINING.md#bugs-that-mattered), [Lessons](LESSONS.md#training) |
| How fast is it? | [Training](TRAINING.md#speed), [GPU environment](GPU_ENGINE.md#measured-speed) |
| How do the NES consoles run on the GPU? | [GPU environment](GPU_ENGINE.md#whats-in-it), `engine/rl/csrc/` |
| How do I add a game to the GPU environment? | [GPU environment](GPU_ENGINE.md#adding-a-game), [`skills/gpu-env-port/SKILL.md`](../skills/gpu-env-port/SKILL.md) |
| How is the emulator fetched and patched? | [GPU environment](GPU_ENGINE.md#distribution-and-setup), `engine/third_party/nesle-extensions.patch` |
| How is the trained player exported? | `engine/rl/player/` |

## Watching and repairing training

| Question | Answer |
|---|---|
| How does the watcher decide something is wrong? | [Training watcher](TRAINING_WATCHER.md#what-it-detects), `core/watch.py` |
| Would it have caught a real bug? | [Training watcher](TRAINING_WATCHER.md#tested-on-real-history) |
| How does a reward fix get applied? | [Training watcher](TRAINING_WATCHER.md#the-repair-loop), `core/train_ctl.py` |
| How many fixes can it make on its own? | [Training watcher](TRAINING_WATCHER.md#guardrails): 3 per game, `MAX_FIXES` |
| How does the agent diagnose a stall or collapse? | [`skills/training-doctor/SKILL.md`](../skills/training-doctor/SKILL.md) |

## Oracle, isolation and rebuilding

| Question | Answer |
|---|---|
| What can the builder ask the oracle? | [Reliability](RELIABILITY.md#isolation), `core/oracle.py` |
| How is the builder kept away from the game? | [Architecture](ARCHITECTURE.md#how-isolation-is-enforced-and-its-limits), `core/isolation.py`, `pre_tool_call` in `__init__.py` |
| Is isolation a security boundary? | No. [Reliability](RELIABILITY.md#isolation) |
| How does the builder work? | [`skills/rebuild-from-oracle/SKILL.md`](../skills/rebuild-from-oracle/SKILL.md) |
| How are two games compared frame by frame? | [Reliability](RELIABILITY.md#trace-compare), `core/compare.py` |
| What stops the gate being fooled? | [Reliability](RELIABILITY.md#the-regression-gate), `core/gate.py` |
| How faithful was the rebuild? | [Reliability](RELIABILITY.md#rebuild-fidelity), [Results](RESULTS.md#single-game-foundation) |
| How are original assets brought in? | `ghostrun_assets_import`, faithful mode only, `cmd_import_assets` in `core/cli.py` |
| How is a 2.5D or 3D version added? | [`skills/visual-upgrade/SKILL.md`](../skills/visual-upgrade/SKILL.md) |
| What went wrong while rebuilding? | [Lessons](LESSONS.md#rebuilding) |

## State, trust and limits

| Question | Answer |
|---|---|
| Where is pipeline state kept? | [Architecture](ARCHITECTURE.md#durable-state), `core/ledger.py` |
| What does each guarantee rest on? | [Reliability](RELIABILITY.md#at-a-glance) |
| Can training resume exactly? | [Reliability](RELIABILITY.md#exact-resume) |
| What is tested, and how? | [Reliability](RELIABILITY.md#tests), `tests/`, `engine/rl/tests/` |
| What hasn't been validated? | [Reliability](RELIABILITY.md#not-validated), [Lessons](LESSONS.md#not-proven) |
| What should I avoid doing? | [Lessons](LESSONS.md) |
| Where are the tools registered? | `__init__.py`, one CLI command per stage in `core/cli.py` |
| How is it published? | [Publishing](PUBLISHING.md) |
