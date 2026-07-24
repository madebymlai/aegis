---
title: Research
tags:
  - index
---

# Research — skill-driven papers

A **paper folder** is `research/<slug>/` (kebab-case): one per paper, built by the
`academic-paper` skill. 

```
research/
  <slug>/
    phaseN_*/    # phase dirs — the skill creates these at runtime
```

**Start a paper:** make `research/<slug>/` and run `academic-paper` there.

**Finished output:** the final PDF goes to [[papers/README|papers/]].

## Behaviours, not strategies

We research **market behaviours** — the return-generating mechanism — not published or surviving
strategies. Hunting strategies is doubly biased by **survivorship + publication bias**: you see
only the winners, and a published edge is already being arbitraged away (McLean & Pontiff, 2016).
So every paper must carry an **ex-ante economic rationale** — a risk premium, or a persistent
behavioural/frictional mispricing bounded by limits to arbitrage — that fixes the effect's *sign*
from first principles before any backtest. A backtest **estimates** an effect we already expect;
it never **discovers** one. That is the guard against data snooping, the factor zoo, and backtest
overfitting.
