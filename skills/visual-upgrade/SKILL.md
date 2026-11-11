---
name: visual-upgrade
description: Add a high-resolution 2.5D or 3D renderer to a finished rebuild without changing gameplay. Use after the gate passes.
---

# Visual upgrade

Graphics are a separate layer that reads the simulation. They never change it.

- Preserve the finished 2D version as an independently runnable target. Create the 2.5D or 3D version alongside it; never convert or overwrite the 2D renderer, assets or build output.
- Keep separate source directories, asset directories, build outputs and launch commands for the 2D and 3D versions. Document how to build and play each independently. The 2D target must not import or load 3D code or assets.
- Share the gameplay simulation where practical, with both renderers reading it. A visual upgrade must not change simulation behaviour. Keep renderer-specific changes within their own version.
- Write a contract first: 1 unit = 1 tile, gameplay on plane z=0, no root motion, fixed clip and material names, triangle budgets.
- Create the mesh kit from procedural Three.js geometry by default. If external or generated models were requested, check that the asset source or generator is available before this stage; record any unavailable asset and continue with the procedural kit.
- Map tiles to semantic classes, then to instanced kit pieces, every frame from live state. Report any unmapped tile.
- Animation clip and time are pure functions of simulation counters.
- Background scenery can sit behind the plane, placed along the camera ray so its screen position holds.
- Record the source of each asset in a manifest and retain any accompanying notices.
- Image-to-3D models give fused meshes with baked poses. They suit rigid props and references, not animated characters.

**Prove it:** build and launch both versions independently, and verify that the 2D version still works with the 3D assets and build output absent. Run the same inputs headless, in 2D and in 3D, and require identical simulation hashes and audio events. Then measure frame time at the target resolution.

For the default recreate workflow, create both complete-playthrough videos and the delivery manifest from docs/RECREATION.md. Pass the `visual3d` stage only after target launch checks, per-frame simulation/audio parity and visual inspection; missing requested assets or videos means incomplete.
