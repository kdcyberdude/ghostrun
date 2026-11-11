# What else this enables

## Bring old games to modern screens

Retro games run at 256×240. A rebuild is real code, so it can render at 2K, 4K or in 3D, and it runs anywhere a browser does. This works for games you have the rights to, and for new games that capture how the classics felt.

## Build on top, instead of starting over

Once a game's logic is code, you can change it: new levels, new mechanics, new modes. Mechanics mode is built for this, letting you study what makes a game feel good and then make your own.

## Studios recovering their own lost games

The strongest commercial use. Source code for old games is often lost. [Nightdive](https://store.epicgames.com/news/system-shock-2-25th-anniversary-remaster-interview-stephen-kick) has rebuilt titles from retail discs, [Mega Cat remastered Backyard Baseball](https://techcrunch.com/2024/10/13/the-original-source-code-for-backyard-baseball-is-long-gone-mega-cat-studios-remastered-the-game-anyway) without its source, and fans spent about two years decompiling LEGO Island by hand. A studio that owns its catalogue can use this pipeline with no rights problem.

## Automated game testing

A policy that reaches every level is a tireless tester, and replay comparison is a regression oracle. [EA](https://www.ea.com/seed/news/automated-game-testing-deep-reinforcement-learning) and Ubisoft have used RL for testing at AAA scale. The same harness can check a new build against an old one.

## Data for game-playing agents and world models

Every run yields exact actions, frames and ground-truth state. Datasets like NitroGen have to infer actions from video. Here they're known exactly. Only use games you may use.

## A reward-design benchmark for agents

Can an agent work out what a game rewards just from memory and the screen? It's checkable, spans many genres, and has clear failure modes. Related work like [Eureka](https://arxiv.org/abs/2310.12931) shows LLM-written rewards can beat human ones. We didn't find prior work where an agent discovers rewards from raw NES RAM.

## Teaching agents to act

Fast feedback, real-time control and long horizons make games good training for decision-making, with lessons that carry over to robotics-style control.

## Preservation and accessibility

Documenting how a game behaves is a form of preservation. [87% of pre-2010 US games are out of print](https://gamehistory.org/study-explainer). A learned map of game state could also feed narration for blind players, though this is an idea we haven't built.