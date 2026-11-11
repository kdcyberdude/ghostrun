# Publishing GhostRun

The repository is [kdcyberdude/ghostrun](https://github.com/kdcyberdude/ghostrun). It is public, with `main` as the default branch. The repository name matches `plugin.yaml`, the tool prefix and the `/ghostrun` command; the local checkout folder can have any name.

## Update the repository

Create a feature branch for subsequent changes, run the CPU checks from [Contributing](../CONTRIBUTING.md), and push the branch. Open a PR targeting `main` when the change is ready for review.

The private `launch/` notes, ROMs, weights, local configuration and generated build output are ignored.

## Prepare a public release

When the project is ready for public use:

1. Update [Results](RESULTS.md) with the latest measured training and evaluation results.
2. Run the CPU checks and `hermes plugins validate .` in your Hermes environment.
3. Publish the checked revision and record its full commit SHA. This repository is already public.

Users with repository access can install directly before catalog acceptance:

```bash
hermes plugins install kdcyberdude/ghostrun
hermes plugins enable ghostrun
```

## Submit the Hermes catalog PR

The plugin repository and the catalog entry are separate. [The GhostRun catalog PR is already open](https://github.com/NousResearch/hermes-agent/pull/153520); update that PR instead of submitting a duplicate. Catalog acceptance is separate from publishing the plugin repository.

For a new catalog entry, or when preparing an update:

1. Fork and clone [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
2. Follow that checkout's current plugin catalog contribution instructions and create a branch for the GhostRun entry.
3. Point the entry at `https://github.com/kdcyberdude/ghostrun` and use the metadata in [plugin.yaml](../plugin.yaml) and disclosures in [CATALOG.md](../CATALOG.md).
4. Run the catalog's required validation against the published revision.
5. Open a PR describing the plugin, installation requirements and validation. Link [Results](RESULTS.md) for the earlier research results and current multi-game work.

The training lab, model weights and playable rebuilds belong in their separate repositories or hosting targets; the catalog PR contains the plugin's metadata and pins its reviewed source revision. Links to the published training code and players are in the [README](../README.md#code-and-trained-players).

For a demo, record the actual run and its limitations using [the evidence guide](DEMO.md). Replace the README's demo placeholder and the catalog PR's demo link only after the video is published.
