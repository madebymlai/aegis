# Strategy Research

Strategy Research turns market hypotheses into comparable evidence and reproducible strategy candidates.

## Language

### Research Work

**Research Hypothesis**:
A falsifiable claim about market behavior that can be expressed as a Strategy and evaluated with defined evidence.
_Avoid_: idea, thesis, hunch

**Run Config**:
The complete declaration of one research question, including its market data, Components, candidate space, portfolio assumptions, and ranking criteria.
_Avoid_: recipe, template, job file

**Run**:
One reproducible evaluation of a Research Hypothesis under a Run Config.
_Avoid_: experiment session, backtest file, research loop

**Development Period**:
The scored market interval shared by every Candidate in a Run.
_Avoid_: training set, validation set, fold

**Warmup**:
The market history required to establish every selected Component before scoring begins.
_Avoid_: training period, burn-in setting

**Observation Block**:
A labeled interval used to compare Candidate metrics across different market conditions while preserving one continuous portfolio history.
_Avoid_: fold, execution window, validation portfolio

### Strategy Definition

**Component**:
A registered unit of strategy logic with declared inputs, parameters, and outputs. Components belong to the Indicator or Strategy family.
_Avoid_: plugin, script, notebook

**Indicator**:
A Component that derives named numeric observations from Market Arrays for use by a Strategy.
_Avoid_: feature, alpha, filter

**Strategy**:
A Component that converts Market Arrays and Indicator outputs into signed Target Weights.
_Avoid_: model, system, algorithm

**Market Array**:
A named time series supplied to Components, such as Open, Close, Volume, or a distribution series.
_Avoid_: feature, column, field

### Evidence and Selection

**Candidate**:
A complete Strategy parameterization evaluated by a Run and accompanied by its metrics, rank, and Provenance.
_Avoid_: trial, result row, parameter set

**Metric**:
A named measurement with defined semantics and units that describes Candidate behavior or supports ranking.
_Avoid_: KPI, stat, output number

**Candidate Set**:
The best, median, and worst representative Candidates committed together for one Run.
_Avoid_: leaderboard, result batch, shortlist

**Representative Role**:
The best, median, or worst position assigned to a Candidate within a Candidate Set.
_Avoid_: label, tier, bucket

**Candidate Store**:
The durable collection of Candidate Sets and their Provenance across Runs.
_Avoid_: results folder, cache, leaderboard database

**Lock**:
A durable reference to one Candidate selected for exact reuse or export.
_Avoid_: promotion, snapshot, pinned config

**Provenance**:
The evidence lineage that connects a Candidate to its Run Config, market data, Components, and parameters.
_Avoid_: history, audit notes, metadata bag
