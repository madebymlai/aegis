# Handoff: Deepen a Research-Vault Article via Exa (Broad → Narrow)

A generic, reusable methodology for raising the knowledge depth and intellectual
level of one existing article in the Obsidian research vault at
`aegis-rd/research/vault/`. A fresh agent can execute it on any article with no
prior context.

## Inputs

- One article path under `research/vault/research/*.md`. Read it IN FULL first.
- The vault's standing docs: `.claude/skills/research-fin/RESEARCHING_TOPICS.md`
  (three-lane sweep, source grading, two-source rule) and `WRITING_ARTICLES.md`
  (prose rules, footnotes, hypothesis checkboxes). This methodology assumes both.

## Phase 0 - Gap analysis (before any search)

Read the article and score it against this checklist. Each hit becomes one search
lane. Do NOT search without a named gap; do not keep sources that serve no gap.

1. **Edge-existence economics missing?** If the article claims a persistent payoff
   but never answers "who is on the other side and why do they keep paying", that
   is the highest-value gap. Look for structurally price-insensitive counterparties
   (mandate-driven flows, hedgers, mechanical rebalancers) and for behavioral
   barriers that keep the edge from crowding away.
2. **Load-bearing claims single-sourced?** Two-source rule: any claim the argument
   leans on needs 2+ independent sources (two posts citing one paper = one source).
3. **No counter-source for the article's own cure/thesis?** Every prescription needs
   its best opposing source named; if the article proposes a fix, search for the
   fix's known limitations and proven boundaries.
4. **Evidence-scope gaps?** The claim is tested in one regime, asset class, or crisis
   type while the argument implicitly needs more (e.g. crisis evidence that covers
   only one kind of crisis).
5. **Provisional citations with possible peer-reviewed antecedents or updates?**
   Working papers may since have published versions, replications, failed
   replications, or retractions - search for each load-bearing working paper's fate.
6. **Missing intellectual lineage or theorem-grade anchor?** A practitioner claim
   may have a peer-reviewed, no-COI theoretical backbone; finding it upgrades the
   claim and often sharpens it into a diagnostic.
7. **COI concentration?** If every load-bearing source is a fund marketing its own
   product, hunt specifically for academic/no-COI corroboration.

## Phase 1 - Broad sweep

- Load tools if deferred: `ToolSearch("select:mcp__exa__web_search_exa,mcp__exa__web_fetch_exa")`.
- Fire 2-4 `web_search_exa` queries IN PARALLEL (one tool block), one per gap.
- Query style: describe the ideal page semantically, not keywords.
  Good: "critique or limitation of <the article's cure> - estimation error,
  parameter sensitivity, can it itself be gamed". Bad: "<cure> critique".
- Cover the three lanes across the queries: origin (the primary paper), current
  (replications, live performance), counter ("X doesn't work", failed replication).

## Phase 2 - Cheap triage

- Search results can be huge; oversized outputs get persisted to files. Do NOT read
  them fully in context: grep the saved file for `Title:` / `URL:` lines, or parse
  with a short python snippet, then decide what to fetch.
- Discard: sources repeating an already-kept one, blog posts wrapping a paper you
  can cite directly, anything serving no Phase-0 gap.

## Phase 3 - Narrow

- Batch-fetch the 3-5 most promising PRIMARY sources with `web_fetch_exa`
  (`maxCharacters` ~6000; multiple URLs per call).
- Chase citation chains to the primary paper and cite that (an SSRN/DOI/arXiv link,
  not the blog that mentioned it). If a fetch 404s, search for the paper's SSRN or
  author-hosted PDF instead.
- Capture exact figures WITH conditions (universe, period, gross/net) - vague
  claims cannot survive the vault's quality bar.

## Phase 4 - Saturation check

Stop when new sources stop adding claims (typically after 1-2 narrow rounds).
Grade every keeper: peer-reviewed > working paper > practitioner-with-methodology >
blog; flag COI and staleness. A no-COI peer-reviewed anchor is worth more than
three fund whitepapers saying the same thing.

## Phase 5 - Fold in (targeted edits, never a rewrite)

- New `##` section ONLY for a structural gap (e.g. missing economics); everything
  else strengthens existing sections in place.
- Each addition: 1-4 sentences of synthesized prose + footnote(s). Match the
  article's voice and argument flow; each section must still advance the argument.
- **Limitations**: add honest entries for every new leg - single-study status, COI,
  assumptions of a theorem, and explicitly flag any composite inference that is
  "our own synthesis, untested".
- **Hypotheses**: if the new evidence exposes a testable lever, add an unchecked,
  pre-registered hypothesis (generic phrasing; expected direction stated).
- **Abstract** last: extend the `> [!abstract]` callout only with what genuinely
  changed the article's one-line takeaway.
- **Sources**: full footnote definitions with author, venue, year, one-line
  contribution, COI note, URL.

## Phase 6 - Curate the site index

`research/vault/site-index.md`: grep for the domain/ID first (no duplicates), then
add each kept source under the right `##` category as
`- [Name](url) - one line on why it's useful` (include the COI note).

## Phase 7 - Verify (run before finishing)

Hard vault conventions: no em dashes (use "-"); article BODY carries no
`[[runs/...]]` links or campaign talk (project detail lives ONLY in hypothesis
outcomes as verdict + diary link); wikilinks must resolve; footnote used-set ==
defined-set; no default-AI vocabulary (delve/tapestry/pivotal/crucial/...).

```python
import re
f = "research/<article>.md"  # cwd: research/vault
text = open(f).read()
defined = set(re.findall(r'^\[\^([a-zA-Z0-9_-]+)\]:', text, re.M))
used = set(re.findall(r'\[\^([a-zA-Z0-9_-]+)\](?!:)', text))
print("undefined:", sorted(used - defined) or "none")
print("unused:", sorted(defined - used) or "none")
print("em-dash:", "FOUND" if "—" in text else "none")
m = re.search(r'^## Strategy hypotheses.*$', text, re.M)
body = text[:m.start()] if m else text
print("body run-mentions:",
      re.findall(r'\[\[runs/[^\]]*\]\]|this campaign|the campaign', body) or "none")
for w in ["delve","tapestry","landscape","pivotal","crucial","multifaceted",
          "nuanced","holistic","cutting-edge"]:
    if re.search(rf'\b{w}\b', text, re.I): print("AI-vocab:", w)
```

Then offer the user a single vault-only commit.

## Suggested skills

- `research-fin` - invoke FIRST; owns the vault conventions, diary/article/site-index
  rules this methodology builds on.
- `obsidian-markdown` - before writing, for wikilink/callout/footnote syntax.

## Anti-goals

- Do not rewrite the article or change its thesis; deepen it.
- Do not add sources that repeat kept ones or serve no named gap.
- Do not put project/run specifics in the article body (vault rule).
- Do not present a fund whitepaper's claim as settled without a COI flag.
