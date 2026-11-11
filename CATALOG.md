# What this plugin does on your machine

Disclosure for the Hermes plugin catalog (rule 13).

**Surfaces:** 28 tools, one `pre_tool_call` hook, one `/ghostrun` command, six skills. No middleware, no credentials, no telemetry.

**Network:** one call, only when you run `ghostrun_engine_setup`: `git clone https://github.com/hbofz/NeSLE.git`, checked out at pinned commit `0b04d8b9`, into the plugin's data folder. The plugin never replaces its own files.

**Shell commands:** `git`, `nvcc`, `c++`, `nvidia-smi` and your configured Python, all to set up, build and run training.

**Long-running background work, all started only by explicit tool calls:**
- GPU training process (`ghostrun_train_start`)
- Oracle process (`ghostrun_oracle_start`)
- Watcher thread (`ghostrun_watch_start`), which can queue a message to the agent when training needs attention

**Autonomous changes:** when the watcher wakes the agent, the agent may edit that game's reward reader and restart that game's training. Limited to 3 fixes per game, and only for training the plugin itself started.

**Reads outside plugin data:** the ROM path you give it, and the builder folder you configure.

**Binaries:** none in the repository. The emulator's CPU and CUDA libraries are compiled from source on your machine, inside the plugin's data folder.

**Requirements:** Linux and an NVIDIA GPU with CUDA for training. No ROMs or model weights are bundled.
