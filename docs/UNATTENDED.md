# Running GhostRun unattended

A full GhostRun pipeline runs for hours: GPU training, oracle probing, a builder subagent, and a 3D upgrade. Hermes's approval system decides whether the agent ever has to stop and ask you something. GhostRun never changes those settings itself (catalog rule 12). They're yours to set.

## Why GhostRun rarely needs approval
GhostRun's heavy and long-running work goes through **plugin tools**, not shell commands. That covers GPU training, the watcher, the oracle, trace comparison, the gate and isolation checks. Hermes's dangerous-command approval applies to `terminal` commands, not to plugin tools. So most of the pipeline never meets an approval prompt, whatever your settings are.

## What can still stop a run

| Setting | Default | Effect on a GhostRun run |
|---|---|---|
| `approvals.mode` | `smart` | A guardian model rules on each risky terminal command. Most builder commands (`npm`, `node`, `python`, `ffmpeg`) go through automatically. Only real escalations reach you. |
| `approvals.single_query_mode` | `deny` | One-shot `hermes -q`/`-z` runs refuse dangerous commands unless YOLO is active. Prefer a resumable `hermes chat` session for pipeline runs. |
| `approvals.unattended_mode` | `deny` | The same refusal for webhook and API-server sessions. |
| `delegation.subagent_auto_approve` | `false` | A subagent such as the GhostRun builder **auto-denies** an escalated command instead of asking you. |

## Recommended profiles

**Supervised (default).** Smart approvals, with the guardian told what GhostRun normally does:
```bash
hermes config set approvals.smart_policy "GhostRun runs: approve builds, tests, node/npm/npx, python, nvcc, ffmpeg and headless browsers inside the configured reference and builder folders."
hermes config set delegation.subagent_auto_approve true
```

**Unattended pipeline on a dedicated GPU box.** Keep approval bypass scoped to this chat:
```bash
hermes config set delegation.subagent_auto_approve true
hermes chat --yolo --query-file pipeline-prompt.txt
```
`--yolo` bypasses command approvals for that chat, including one-shot command denials. If you want this for every chat on the box, set `approvals.mode off` instead. Neither setting bypasses Hermes's hardline blocks, user `approvals.deny` rules, protected instruction-file writes, or a declared MCP spend limit. Avoid editing `AGENTS.md`, `CLAUDE.md`, or `SOUL.md` during an unattended run; those writes still require a person. Do not route a denied command through a plugin tool to evade a guard.

## 3D assets
The `visual-upgrade` skill creates its default mesh kit with procedural Three.js geometry, so no model weights or downloaded meshes are needed. If you request external or generated props, provide the asset source or installed image-to-3D tool before that stage; the agent checks its availability and records each asset's source and license in the manifest. Image-to-3D models suit rigid props, not animated characters.

## Recreation continues until verified

The builder repeats observe, compare, diagnose, fix and full-route regression checks. The parent reviews `evidence/recreation-status.md` and resumes incomplete builder work across delegation/context limits. Local fixture passes do not authorize the 3D stage. Completion requires full requested-route coverage, fresh held-out runs, no known material deterministic mismatch, and separate evidence for uncontrolled randomness. A user time or spending limit still ends the run as incomplete when those requirements are unmet.
