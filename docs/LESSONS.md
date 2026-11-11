# Lessons: what to do and what not to do

Drawn from hundreds of real coding-agent sessions building this system. Each item below was observed. Ideas that were never proven are listed separately at the end.

## Rewards

**Do**
- Audit with random play and require detected deaths to equal lives lost. This caught pit deaths that a first version missed, and overheats wrongly counted as crashes.
- Test balance with scripted players before training. A death penalty equal to a whole level made crouching the best strategy. A scripted comparison showed it in minutes, after 21M decisions had been wasted.
- Treat every RAM byte as possibly signed or wrapping. One unsigned read paid about 20 levels in a single step and was found two days later, after a training collapse.
- Keep a verified, provisional or unverified status for each signal.
- Add a damage or phase term where scrolling stops, such as boss fights. Without it, progress freezes.

**Don't**
- Don't count events at the end of an episode for a curriculum. One clear rate was 80 minutes stale: it read 99.7% while the real rate was 0 of 16.
- Don't treat search reach as training evidence. Search can reach places a policy never learns to.

## Training

**Do**
- Normalise advantages per game in multi-game training. Quiet games were about 60 times smaller and got ignored.
- Test greedy and sampled play separately. One checkpoint scored 0 of 8 greedy and 15 of 16 sampled.
- Look at actual button streams. A held jump button explained freezes that entropy theories didn't.
- Keep frozen test-play snapshots. They exposed sudden collapses.

**Don't**
- Don't report throughput as progress. A run did 9,000 decisions per second for hours and learned nothing.
- Don't advance a curriculum on sample counts alone. It broke clean play.

## Rebuilding

**Do**
- Use numeric traces first. A "bug" reported from screenshots turned out to be the viewer's image join.
- Separate measurement artefacts from real differences. In one sweep, most of the reported differences were artefacts.
- Get the clock right first. Trainer steps and fixed-cycle steps look identical until a replay fails.
- Test on held-out play. Fixes tuned on one route often didn't help free play.
- Write a test that fails without the fix. One agent's first test passed either way.
- Time-box hypotheses to about 30 commands, and record negative results.

**Don't**
- Don't fit constants to one sample. A rule from one level broke others.
- Don't chase differences a player can't notice: under about 3 px, one frame, or animation phase.
- Don't take a gate PASS to mean the game is right. It means no regression against the last saved baseline.

## Running agents

**Do**
- Keep state in files. Agents die with their parent process, and context gets compacted.
- Check process liveness independently. A faulty watcher once reported two live jobs as dead.
- Bound parallel agents, and account for shared CPU between them.

**Don't**
- Don't merge branches that track worktree symlinks. A `git merge` once deleted real asset folders and lost data.
- Don't let tools sprawl. Most one-off scripts were used in a single session. Write parameterised tools and keep probes in scratch space.

## Not proven

- Saved level starts improve final win rate. Clear rates rose on some levels, with no full win yet.
- Varied "moods" produce different strategies. The judge is barely above chance.
- An idle cost fixes stalling in general. Early signs only.
- A policy trained on the original plays well on a rebuild.
