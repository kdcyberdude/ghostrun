# Publishing GhostRun

The repository is [kdcyberdude/ghostrun](https://github.com/kdcyberdude/ghostrun). It is private during preparation, with `main` as the default branch. The repository name matches `plugin.yaml`, the tool prefix and the `/ghostrun` command; the local checkout folder can have any name.

## Update the repository

Create a feature branch for subsequent changes, run the CPU checks from [Contributing](../CONTRIBUTING.md), and push the branch. Open a PR targeting `main` when the change is ready for review.

The private `launch/` notes, ROMs, weights, local configuration and generated build output are ignored.

## Prepare a public release

When the project is ready for public use:

1. Update [Results](RESULTS.md) with the latest measured training and evaluation results.
2. Run the CPU checks and `hermes plugins validate .` in your Hermes environment.
3. Make the repository public through its GitHub settings.

Users with repository access can install directly before catalog acceptance:

```bash
hermes plugins install kdcyberdude/ghostrun
hermes plugins enable ghostrun
```

## Submit the Hermes catalog PR

The plugin repository and the catalog entry are separate. Once the repository is public:

1. Fork and clone [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
2. Follow that checkout's current plugin catalog contribution instructions and create a branch for the GhostRun entry.
3. Point the entry at `https://github.com/kdcyberdude/ghostrun` and use the metadata in [plugin.yaml](../plugin.yaml) and disclosures in [CATALOG.md](../CATALOG.md).
4. Run the catalog's required validation against the published revision.
5. Open a PR describing the plugin, installation requirements and validation. Link [Results](RESULTS.md) for the earlier research results and current multi-game work.
