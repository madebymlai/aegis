---
title: Home
tags:
  - index
---

# Aegis RD Research Vault

Organizes the research campaign: useful sites, per-run diaries, and articles to study.

## Map

- [[site-index|Site Index]] - useful sites found, organized by category
- `runs/<strategy>/<date>.md` - one diary note per day per strategy, with a section per run: what was tested, how it went
- `research/<article-name>.md` - general knowledge: articles we synthesize in prose from studied sources, cited with footnotes, distilled into strategy hypotheses
- [[notes/readme|Notes]] - research scratchpad: provisional, article-shaped findings we do not want to lose, before they earn a full `research/` article
- [[graveyard|Graveyard]] - killed hypotheses, one line each, so dead ideas don't get re-researched

## Conventions

> [!tip] Creating new notes
> Use the templates in `templates/`: [[templates/run-diary|run-diary]] for a new run day, [[templates/article|article]] for a new article note. Enable the core **Templates** plugin and point it at the `templates` folder.

- Filenames use kebab-case, no spaces
- Run diary filenames are ISO dates: `runs/<strategy>/2026-06-10.md`; inside, each run gets a `### run_id` section (copy the run folder name from the repo's `runs/`) - the headings are the single source of truth, searchable and deep-linkable as `[[2026-06-10#run_id]]`
- Articles are named after what they synthesize: `research/volatility-targeting-in-practice.md`
- Articles are written in prose, with sources as footnotes (`[^1]`) at the bottom
- Link articles from run diaries when an idea you tested came from one
