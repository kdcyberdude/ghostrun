# Running GhostRun unattended

A full GhostRun pipeline runs for hours: GPU training, oracle probing, a builder subagent, and a 3D upgrade. Hermes's approval system decides whether the agent ever has to stop and ask you something. GhostRun never changes those settings itself (catalog rule 12). They're yours to set.

## Why GhostRun rarely needs approval
GhostRun's heavy and long-running work goes through **plugin tools**, not shell commands. That covers GPU training, the watcher, the oracle, trace comparison, the gate and isolation checks. Hermes's dangerous-command approval applies to `terminal` commands, not to plugin tools. So most of the pipeline never meets an approval prompt, whatever your settings are.

## What can still stop a run

| Setting | Default | Effect on a GhostRun run |
|---|---|---|
| `approvals.mode` | `smart` | A guardian model rules on each risky terminal command. Most builder commands (`npm`, `node`, `python`, `ffmpeg`) go through automatically. Only real escalations reach you. |
| `approvals.single_query_mode` | `deny` | `hermes -q`/`-z` one-shot runs **silently refuse** every dangerous command. Prefer an interactive `hermes chat --query-file …` session for pipeline runs. |
| `approvals.unattended_mode` | `deny` | The same refusal for webhook and API-server sessions. |
| `delegation.subagent_auto_approve` | `false` | A subagent such as the GhostRun builder **auto-denies** an escalated command instead of asking you. |

## Recommended profiles

**Supervised (default).** Smart approvals, with the guardian told what GhostRun normally does:
```bash
hermes config set approvals.smart_policy "GhostRun runs: approve builds, tests, node/npm/npx, python, nvcc, ffmpeg and headless browsers inside the configured reference and builder folders."
hermes config set delegation.subagent_auto_approve true
```

**Fully unattended (a dedicated GPU box you can throw away).** No prompts at all, like an auto-approve agent session:
```bash
hermes config set approvals.mode off
hermes config set delegation.subagent_auto_approve true
hermes config set approvals.deny '["rm -rf /*", "mkfs*", "git push --force*"]'
hermes chat --yolo --query-file pipeline-prompt.txt
```
The `approvals.deny` globs still block under `--yolo`, so keep a short list of commands you never want run. Edits to instruction files (AGENTS.md, SOUL.md) still ask, even under `--yolo`.

## 3D assets
The `visual-upgrade` skill doesn't need downloads to work. Its kit pieces can be procedural Three.js geometry. Image-to-3D models suit rigid props only, not animated characters. If you want generated props, install your image-to-3D tool before the run and name it in the prompt. The agent records each asset's source in the asset manifest.
