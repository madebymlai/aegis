#!/usr/bin/env python3
"""Aegis RD look-ahead / data-leak / bias audit.

Wraps the `aerd run` pipeline in a battery of offline, deterministic checks that
attack the three classic backtest failure modes:

  * FORWARD-LOOK (look-ahead): does any decision at bar t depend on data after t?
  * DATA LEAK: does the held-out (out-of-sample) set influence selection/ranking?
  * BIAS: is the selected candidate overfit to the selection window?

The audit is built around two complementary tactics:

  1. Structural checks  -- parse the run's own evidence (strategy_run.json) and
     assert the invariants the framework claims (split policy, set disjointness,
     temporal ordering, ranking-on-selection-only, index integrity, next-open
     execution masking).

  2. Behavioural checks -- run the *real* pipeline on a synthetic CSV, then re-run
     it on a copy whose data is identical up to the last selection bar but
     scrambled afterwards. Because indicators are precomputed on the FULL series
     and only then sliced per window, any non-causal indicator (full-sample
     z-score, future ffill, centred window, ...) would let the scrambled tail
     change a selection-window metric. If selection metrics are invariant -> no
     look-ahead leaked into scoring. A potency check proves the scramble actually
     reached the engine, so the invariance is meaningful and not vacuous.

Everything is offline (synthetic/CSV data, no network) and seed-deterministic.

Usage:
    scripts/leak_audit.sh [--repo PATH] [--keep] [--quick] [--self-test]
    # or directly:
    <repo>/.venv/bin/python <repo>/scripts/leak_audit.py [--repo PATH] ...

Exit code 0 = all hard checks passed, 1 = at least one hard check failed.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Universe / config knobs. The vanguard strategy hard-codes these symbol names
# (SPY/TLT canary, IWM/EEM/... offensive, TLT/GLD/UUP defensive), so the synthetic
# data must use the exact same names for the strategy to trade.
# --------------------------------------------------------------------------- #
SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
FEATURES = ["Open", "High", "Low", "Close", "Volume"]
N_ROWS = 1400
DATA_SEED = 11
OPT_SEED = 11
RANDOM_SUBSET = 16
SCRATCH_REL = "runs/.leak_audit"   # relative to repo root; runs/* is gitignored
FLOAT_TOL = 1e-9

CONFIG_TEMPLATE = """\
schema_version: 6
name: {name}
output_dir: {output_dir}
data:
  source: csv
  path: {csv_path}
  symbols: [{symbols}]
  timeframe: 1D
  arrays: [OHLCV]
portfolio:
  target_exposure_cap: 0.8
  fees: 0.0005
  slippage: 0.0005
strategy:
  id: vanguard.momentumRotator
indicators:
  - id: vanguard.momentum_score
  - id: vanguard.realized_vol
ranking:
  metric: sharpe_ratio
optimization:
  search: random
  random_subset: {subset}
  seed: {seed}
  split:
    method: from_rolling
    params: {{length: 504, offset: 0, split: 0.5}}
    max_splits: 6
    max_estimated_output_cells: 80000000
    max_public_artifact_bytes: 20000000
"""


# --------------------------------------------------------------------------- #
# Result bookkeeping
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    cid: str
    name: str
    severity: str            # "hard" | "soft"
    status: str = "skipped"  # "pass" | "fail" | "warn" | "skipped"
    detail: str = ""


@dataclass
class Audit:
    checks: list[Check] = field(default_factory=list)

    def add(self, cid, name, severity, status, detail=""):
        self.checks.append(Check(cid, name, severity, status, detail))
        icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "skipped": "SKIP"}[status]
        print(f"  [{icon}] {cid:<24} {name}")
        if detail:
            for line in textwrap.wrap(detail, 96):
                print(f"         {line}")

    @property
    def failed(self):
        return [c for c in self.checks if c.severity == "hard" and c.status == "fail"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def close_eq(a, b, tol=FLOAT_TOL):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def metrics_eq(m1, m2, tol=FLOAT_TOL):
    """Compare two per-split metric dicts ({'0': {...}, ...})."""
    if set(m1) != set(m2):
        return False, f"split labels differ: {sorted(m1)} vs {sorted(m2)}"
    for s in m1:
        if set(m1[s]) != set(m2[s]):
            return False, f"metric keys differ on split {s}"
        for k in m1[s]:
            if not close_eq(m1[s][k], m2[s][k], tol):
                return False, f"split {s} metric {k}: {m1[s][k]} != {m2[s][k]}"
    return True, ""


def min_aware_score(values, min_weight):
    valid = [v for v in values if v is not None]
    if not valid:
        return float("nan")
    mean = sum(valid) / len(valid)
    return (1.0 - min_weight) * mean + min_weight * min(valid)


def run_aerd(aerd, repo, config_path):
    proc = subprocess.run(
        [str(aerd), "run", str(config_path)],
        cwd=str(repo), capture_output=True, text=True, timeout=900,
    )
    out = proc.stdout + proc.stderr
    run_dir = None
    status = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Run:"):
            run_dir = line.split("Run:", 1)[1].strip()
        elif line.startswith("Status:"):
            status = line.split("Status:", 1)[1].strip()
    return proc.returncode, run_dir, status, out


def load_run(repo, run_dir):
    p = repo / run_dir / "strategy_run.json"
    return json.loads(p.read_text())


def candidate_projection(sr):
    """Selection-relevant projection of a run, keyed by candidate role.

    Excludes held_out_metrics and the aggregate 'metrics' (which fold in held-out
    windows) -- only the parts that drive selection/ranking.
    """
    proj = {}
    for c in sr["candidates"]:
        proj[c["role"]] = {
            "params": c["params"],
            "selection_metrics": c["selection_metrics"],
            "score": c["score"],
            "rank": c["rank"],
        }
    return proj


def projection_eq(p1, p2):
    if set(p1) != set(p2):
        return False, f"candidate roles differ: {sorted(p1)} vs {sorted(p2)}"
    for role in p1:
        a, b = p1[role], p2[role]
        if a["params"] != b["params"]:
            return False, f"{role}: chosen params differ"
        if not close_eq(a["score"], b["score"]):
            return False, f"{role}: score {a['score']} != {b['score']}"
        if a["rank"] != b["rank"]:
            return False, f"{role}: rank differs"
        ok, why = metrics_eq(a["selection_metrics"], b["selection_metrics"])
        if not ok:
            return False, f"{role}: {why}"
    return True, ""


# --------------------------------------------------------------------------- #
# Data generation
# --------------------------------------------------------------------------- #
def gen_base_panel(np):
    """Deterministic GBM OHLCV, mirroring the framework's synthetic generator."""
    rng = np.random.default_rng(DATA_SEED)
    panel = {}
    for i, s in enumerate(SYMBOLS):
        drift = 0.00015 + i * 0.00003
        vol = 0.015 + i * 0.002
        ret = rng.normal(drift, vol, N_ROWS)
        close = 100 * np.cumprod(1 + ret)
        spread = np.abs(rng.normal(0.002, 0.001, N_ROWS))
        op = close * (1 + rng.normal(0, 0.001, N_ROWS))
        panel[s] = {
            "Open": op,
            "Close": close,
            "High": np.maximum(op, close) * (1 + spread),
            "Low": np.minimum(op, close) * (1 - spread),
            "Volume": rng.lognormal(12, 0.25, N_ROWS),
        }
    return panel


def perturb_tail(np, panel, cut):
    """Return a copy whose rows < cut are untouched and rows >= cut are replaced
    with a wildly different regime (steep decline + high vol). This shifts the
    full-sample mean/std/min/max, so any non-causal indicator computed over the
    full series would change at bars < cut and trip the invariance check."""
    rng = np.random.default_rng(987654321)
    out = {}
    n_tail = N_ROWS - cut
    for s in SYMBOLS:
        base = panel[s]
        close = base["Close"].copy()
        op = base["Open"].copy()
        high = base["High"].copy()
        low = base["Low"].copy()
        vol = base["Volume"].copy()
        anchor = close[cut - 1]
        tail_ret = rng.normal(-0.01, 0.05, n_tail)   # crash regime
        tail_close = anchor * np.cumprod(1 + tail_ret)
        tail_open = tail_close * (1 + rng.normal(0, 0.01, n_tail))
        tail_spread = np.abs(rng.normal(0.01, 0.005, n_tail))
        close[cut:] = tail_close
        op[cut:] = tail_open
        high[cut:] = np.maximum(tail_open, tail_close) * (1 + tail_spread)
        low[cut:] = np.minimum(tail_open, tail_close) * (1 - tail_spread)
        vol[cut:] = rng.lognormal(13, 0.5, n_tail)
        out[s] = {"Open": op, "High": high, "Low": low, "Close": close, "Volume": vol}
    return out


def write_csv(pd, panel, path):
    cols = pd.MultiIndex.from_tuples(
        [(s, f) for s in SYMBOLS for f in FEATURES], names=["symbol", "feature"]
    )
    idx = pd.date_range("2018-01-01", periods=N_ROWS, freq="D")
    data = {(s, f): panel[s][f] for s in SYMBOLS for f in FEATURES}
    df = pd.DataFrame({c: data[c] for c in cols}, index=idx, columns=cols)
    df.index.name = "Date"
    df.to_csv(path)


def write_config(scratch_rel, name, csv_rel, subset=RANDOM_SUBSET, seed=OPT_SEED):
    return CONFIG_TEMPLATE.format(
        name=name,
        output_dir=f"{scratch_rel}/{name}",
        csv_path=csv_rel,
        symbols=", ".join(SYMBOLS),
        subset=subset,
        seed=seed,
    )


# --------------------------------------------------------------------------- #
# Structural checks (consume one run's evidence)
# --------------------------------------------------------------------------- #
def selection_held_ranges(split):
    sel = split["sets"]["selection"]["membership"]
    held = split["sets"]["held_out"]["membership"]
    return (sel["start"], sel["stop"]), (held["start"], held["stop"])


def structural_checks(audit, sr):
    split = sr["split"]
    splits = split["splits"]

    # C1 -- split set policy: exactly two sets, selection first / held-out second.
    policy = split.get("set_usage_policy")
    roles = [s["role"] for s in split.get("sets", [])]
    ok = (policy == "exactly_two_sets_first_selection_second_held_out"
          and roles == ["selection", "held_out"])
    audit.add("C1.split_policy", "Exactly two ordered sets (selection, held_out)",
              "hard", "pass" if ok else "fail",
              f"policy={policy!r} roles={roles}")

    # C2 -- disjoint membership: a bar is never in both selection and held-out.
    bad = []
    for sp in splits:
        (s0, s1), (h0, h1) = selection_held_ranges(sp)
        if not (s1 <= h0 or h1 <= s0):   # overlap
            bad.append(sp["label"])
    audit.add("C2.disjoint_sets", "Selection and held-out index ranges are disjoint",
              "hard", "pass" if not bad else "fail",
              "no overlap in any split" if not bad else f"overlap in: {bad}")

    # C3 -- temporal order: held-out is strictly in the FUTURE of selection.
    bad = []
    for sp in splits:
        (s0, s1), (h0, h1) = selection_held_ranges(sp)
        sel_end = sp["sets"]["selection"]["end"]
        held_start = sp["sets"]["held_out"]["start"]
        if not (h0 >= s1 and held_start > sel_end):
            bad.append(sp["label"])
    audit.add("C3.temporal_order", "Held-out set is strictly after selection (no look-ahead)",
              "hard", "pass" if not bad else "fail",
              "held-out follows selection in every split" if not bad
              else f"held-out not strictly future in: {bad}")

    # C4 -- index integrity: monotone increasing, no duplicate timestamps.
    src = split.get("source_index", {})
    di = sr.get("candidates", [{}])[0].get("identity", {}).get("data_identity", {})
    ie = di.get("index_evidence", {})
    mono = ie.get("raw_index_monotonic_increasing")
    dup = ie.get("raw_index_has_duplicates")
    ok = mono is True and dup is False
    audit.add("C4.index_integrity", "Source index monotonic increasing, no duplicates",
              "hard", "pass" if ok else "fail",
              f"monotonic_increasing={mono} has_duplicates={dup} "
              f"(span {src.get('start')} .. {src.get('end')}, n={src.get('count')})")

    # C5 -- ranking uses SELECTION only: recompute the published min-aware score
    #       purely from each candidate's selection_metrics. A match proves the
    #       candidate ranking never consulted held-out data.
    mw = sr["ranking"].get("min_weight", 0.3)
    metric = sr["ranking"]["metric"]
    mism = []
    scores = {}
    for c in sr["candidates"]:
        vals = [c["selection_metrics"][s][metric] for s in c["selection_metrics"]]
        recomputed = min_aware_score(vals, mw)
        scores[c["role"]] = c["score"]
        if not close_eq(recomputed, c["score"]):
            mism.append(f"{c['role']}: pub={c['score']:.10g} recomputed={recomputed:.10g}")
    ordered = scores.get("best", -math.inf) >= scores.get("median", -math.inf) >= scores.get("worst", math.inf)
    ok = not mism and ordered
    detail = (f"min-aware score = (1-{mw})*mean + {mw}*min over selection {metric}; "
              f"best>=median>=worst={ordered}")
    if mism:
        detail += " | MISMATCH: " + "; ".join(mism)
    audit.add("C5.ranking_selection_only",
              "Ranking score reproducible from selection metrics only",
              "hard", "pass" if ok else "fail", detail)

    # C6 -- walk-forward continuity: rolling selection[i+1] reuses held_out[i]
    #       (same index hash) -> consistent splitter, no shuffled/overlapping leak.
    matches = 0
    checked = 0
    for i in range(len(splits) - 1):
        h_hash = splits[i]["sets"]["held_out"].get("hash")
        s_hash = splits[i + 1]["sets"]["selection"].get("hash")
        if h_hash and s_hash:
            checked += 1
            if h_hash == s_hash:
                matches += 1
    if checked == 0:
        audit.add("C6.walkforward_continuity", "Rolling split continuity (hash chain)",
                  "soft", "skipped", "no adjacent split hashes to compare")
    else:
        audit.add("C6.walkforward_continuity",
                  "Rolling split continuity: selection[i+1] hash == held_out[i] hash",
                  "soft", "pass" if matches == checked else "warn",
                  f"{matches}/{checked} adjacent boundaries chain consistently")


def masking_check(audit, repo):
    """C7 -- next-open execution guard: import the masking primitive and prove it
    (a) marks a post-gap bar non-executable and (b) liquidates the terminal bar."""
    sys.path.insert(0, str(repo))
    try:
        import pandas as pd

        from research.aegis_research.allocation_policy.masking import (
            apply_executable_mask_and_terminal_liquidation,
        )
        market = pd.date_range("2020-01-01", periods=6, freq="D")
        # allocations skip the 3rd market bar -> a gap the mask must catch.
        alloc_idx = market.delete(2)
        alloc = pd.DataFrame(1.0, index=alloc_idx, columns=["A", "B"])
        masked, diag = apply_executable_mask_and_terminal_liquidation(
            alloc, market_index=market)
        post_gap = masked.loc[alloc_idx[2]]          # bar right after the skipped one
        terminal = masked.iloc[-1]
        gap_masked = bool(post_gap.isna().all())
        terminal_zero = bool((terminal == 0.0).all())
        ok = gap_masked and terminal_zero and diag.get("terminal_liquidation") is True
        audit.add("C7.next_open_masking",
                  "Next-open executable mask + terminal liquidation enforced",
                  "hard", "pass" if ok else "fail",
                  f"post-gap row masked={gap_masked} terminal liquidated={terminal_zero} "
                  f"non_executable_rows={diag.get('non_executable_rows')}")
    except Exception as e:  # pragma: no cover - defensive
        audit.add("C7.next_open_masking", "Next-open executable mask",
                  "hard", "fail", f"masking import/behaviour check errored: {e!r}")
    finally:
        if str(repo) in sys.path:
            sys.path.remove(str(repo))


# --------------------------------------------------------------------------- #
# Bias reporting (soft)
# --------------------------------------------------------------------------- #
def overfit_report(audit, sr):
    metric = sr["ranking"]["metric"]
    rows = []
    flag = False
    for c in sr["candidates"]:
        sel = [c["selection_metrics"][s][metric] for s in c["selection_metrics"]]
        hel = [c["held_out_metrics"][s][metric] for s in c["held_out_metrics"]]
        sel = [v for v in sel if v is not None]
        hel = [v for v in hel if v is not None]
        ms = sum(sel) / len(sel) if sel else float("nan")
        mh = sum(hel) / len(hel) if hel else float("nan")
        rows.append(f"{c['role']}: selection {metric} {ms:+.3f} -> held-out {mh:+.3f} (gap {ms - mh:+.3f})")
        if c["role"] == "best" and ms > 0 and mh < 0:
            flag = True
    detail = " | ".join(rows)
    audit.add("W1.overfit_gap",
              "Selection vs held-out degradation (overfitting / selection bias)",
              "soft", "warn" if flag else "pass", detail)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Aegis RD look-ahead / leak / bias audit")
    ap.add_argument("--repo", default=None, help="path to aegis-rd repo root")
    ap.add_argument("--keep", action="store_true", help="keep scratch dir on exit")
    ap.add_argument("--quick", action="store_true", help="skip the determinism re-run")
    ap.add_argument("--self-test", action="store_true",
                    help="negative control: prove the look-ahead detector is live")
    args = ap.parse_args()

    repo = Path(args.repo).resolve() if args.repo else _autodetect_repo()
    if not (repo / "pyproject.toml").exists():
        sys.exit(f"not an aegis-rd repo (no pyproject.toml): {repo}")
    aerd = repo / ".venv" / "bin" / "aerd"
    if not aerd.exists():
        sys.exit(f"aerd not found at {aerd}; run from the repo venv")

    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        sys.exit("numpy/pandas required; run via scripts/leak_audit.sh "
                 "(or <repo>/.venv/bin/python scripts/leak_audit.py)")

    scratch = repo / SCRATCH_REL
    csv_dir = scratch / "_csv"
    cfg_dir = scratch / "_cfg"
    for d in (csv_dir, cfg_dir):
        d.mkdir(parents=True, exist_ok=True)

    audit = Audit()
    print(f"Aegis RD leak/bias audit  (repo={repo})")
    print("=" * 100)

    # ---- generate base data ------------------------------------------------ #
    panel = gen_base_panel(np)
    base_csv = csv_dir / "base.csv"
    write_csv(pd, panel, base_csv)
    base_cfg = cfg_dir / "base.yaml"
    base_cfg.write_text(write_config(SCRATCH_REL, "base", f"{SCRATCH_REL}/_csv/base.csv"))

    # ---- Phase 0: pipeline smoke ------------------------------------------ #
    print("\n[Phase 0] Pipeline smoke (it all works, offline)")
    rc, base_run, status, out = run_aerd(aerd, repo, base_cfg)
    ok = rc == 0 and status == "completed" and base_run
    audit.add("P0.pipeline_runs", "aerd run completes on synthetic CSV data",
              "hard", "pass" if ok else "fail",
              f"rc={rc} status={status} run={base_run}")
    if not ok:
        print("\nBASE RUN OUTPUT (tail):")
        print("\n".join(out.splitlines()[-15:]))
        _finish(audit, scratch, args.keep)
        return

    base_sr = load_run(repo, base_run)

    # ---- Phase 1: structural / evidence checks ----------------------------- #
    print("\n[Phase 1] Structural evidence checks")
    structural_checks(audit, base_sr)
    masking_check(audit, repo)

    # ---- Phase 2: look-ahead perturbation ---------------------------------- #
    print("\n[Phase 2] Future-data perturbation (look-ahead detector)")
    cut = max(sp["sets"]["selection"]["membership"]["stop"] for sp in base_sr["split"]["splits"])
    print(f"  cut index = {cut} (max selection stop); scrambling rows [{cut}, {N_ROWS})")
    pert_panel = perturb_tail(np, panel, cut)
    pert_csv = csv_dir / "perturbed.csv"
    write_csv(pd, pert_panel, pert_csv)
    pert_cfg = cfg_dir / "perturbed.yaml"
    pert_cfg.write_text(write_config(SCRATCH_REL, "perturbed", f"{SCRATCH_REL}/_csv/perturbed.csv"))
    rc, pert_run, status, out = run_aerd(aerd, repo, pert_cfg)
    if not (rc == 0 and status == "completed" and pert_run):
        audit.add("C8.selection_invariance", "Selection invariant to future-data scramble",
                  "hard", "fail", f"perturbed run failed rc={rc} status={status}")
    else:
        pert_sr = load_run(repo, pert_run)

        # C8 -- selection projection must be byte-identical despite scrambled tail.
        ok, why = projection_eq(candidate_projection(base_sr), candidate_projection(pert_sr))
        audit.add("C8.selection_invariance",
                  "Selection metrics/ranking invariant to scrambled future data",
                  "hard", "pass" if ok else "fail",
                  "selection identical => no future data leaked into scoring"
                  if ok else f"LOOK-AHEAD LEAK: {why}")

        # C9 -- potency: held-out metrics for splits overlapping the scrambled
        #       region MUST change, else C8 is vacuous (data never reached engine).
        metric = base_sr["ranking"]["metric"]
        changed = False
        details = []
        for cb, cp in zip(base_sr["candidates"], pert_sr["candidates"], strict=False):
            for s in cb["held_out_metrics"]:
                hb = cb["held_out_metrics"][s][metric]
                hp = cp["held_out_metrics"][s][metric]
                if not close_eq(hb, hp):
                    changed = True
                    details.append(f"{cb['role']} split {s}: {hb} -> {hp}")
        audit.add("C9.perturbation_potency",
                  "Scramble reaches the engine (held-out metrics move)",
                  "hard", "pass" if changed else "fail",
                  (f"held-out moved on {len(details)} (split,role) pairs, "
                   f"e.g. {details[0]}") if changed
                  else "held-out UNCHANGED -> C8 is vacuous; perturbation never reached the engine")

    # ---- Phase 2b: negative control (detector must not be a no-op) -------- #
    if args.self_test:
        print("\n[Phase 2b] Negative control: scramble INSIDE a selection window")
        # pick a row range that lands inside at least one selection window
        sel_lo = base_sr["split"]["splits"][-1]["sets"]["selection"]["membership"]["start"]
        lo, hi = sel_lo + 16, sel_lo + 116
        nc_panel = {s: {f: panel[s][f].copy() for f in FEATURES} for s in SYMBOLS}
        rng = np.random.default_rng(424242)
        for s in SYMBOLS:
            nc_panel[s]["Close"][lo:hi] *= (1 + rng.normal(0, 0.3, hi - lo))
        nc_csv = csv_dir / "negctrl.csv"
        write_csv(pd, nc_panel, nc_csv)
        nc_cfg = cfg_dir / "negctrl.yaml"
        nc_cfg.write_text(write_config(SCRATCH_REL, "negctrl", f"{SCRATCH_REL}/_csv/negctrl.csv"))
        rc, nc_run, status, out = run_aerd(aerd, repo, nc_cfg)
        if not (rc == 0 and status == "completed" and nc_run):
            audit.add("NC.detector_live", "Look-ahead detector flags in-selection changes",
                      "hard", "fail", f"negative-control run failed rc={rc} status={status}")
        else:
            nc_sr = load_run(repo, nc_run)
            same, _ = projection_eq(candidate_projection(base_sr), candidate_projection(nc_sr))
            audit.add("NC.detector_live",
                      "Detector is live: changing selection-window data DOES move selection",
                      "hard", "pass" if not same else "fail",
                      f"scrambled rows [{lo},{hi}) inside a selection window; "
                      + ("selection changed as required (C8 invariance is meaningful)"
                         if not same else "selection UNCHANGED -> detector is blind, C8 is vacuous"))

    # ---- Phase 3: determinism --------------------------------------------- #
    if args.quick:
        audit.add("C10.determinism", "Re-run reproduces identical candidates",
                  "hard", "skipped", "--quick set")
    else:
        print("\n[Phase 3] Determinism / reproducibility")
        rep_cfg = cfg_dir / "repeat.yaml"
        rep_cfg.write_text(write_config(SCRATCH_REL, "repeat", f"{SCRATCH_REL}/_csv/base.csv"))
        rc, rep_run, status, out = run_aerd(aerd, repo, rep_cfg)
        if not (rc == 0 and status == "completed" and rep_run):
            audit.add("C10.determinism", "Re-run reproduces identical candidates",
                      "hard", "fail", f"repeat run failed rc={rc} status={status}")
        else:
            rep_sr = load_run(repo, rep_run)
            ok, why = projection_eq(candidate_projection(base_sr), candidate_projection(rep_sr))
            # also compare held-out (same data -> must match exactly)
            if ok:
                for cb, cr in zip(base_sr["candidates"], rep_sr["candidates"], strict=False):
                    eq, w = metrics_eq(cb["held_out_metrics"], cr["held_out_metrics"])
                    if not eq:
                        ok, why = False, f"{cb['role']} held-out: {w}"
                        break
            audit.add("C10.determinism", "Identical seed+data -> identical candidates",
                      "hard", "pass" if ok else "fail",
                      "fully reproducible" if ok else f"NON-DETERMINISTIC: {why}")

    # ---- Phase 4: bias reporting ------------------------------------------ #
    print("\n[Phase 4] Bias reporting (informational)")
    overfit_report(audit, base_sr)

    _finish(audit, scratch, args.keep)


def _autodetect_repo():
    # This file lives at <repo>/scripts/leak_audit.py -> repo is its grandparent.
    for cand in (Path(__file__).resolve().parent.parent, Path.cwd()):
        if (cand / "pyproject.toml").exists() and (cand / "research").exists():
            return cand.resolve()
    return Path.cwd()


def _finish(audit, scratch, keep):
    print("\n" + "=" * 100)
    n = {s: sum(c.status == s for c in audit.checks) for s in ("pass", "fail", "warn", "skipped")}
    hard = [c for c in audit.checks if c.severity == "hard"]
    print(f"SUMMARY: {n['pass']} pass / {n['fail']} fail / {n['warn']} warn / {n['skipped']} skip "
          f"({len(hard)} hard checks)")
    report = scratch / "audit_report.json"
    report.write_text(json.dumps(
        [{"id": c.cid, "name": c.name, "severity": c.severity, "status": c.status,
          "detail": c.detail} for c in audit.checks], indent=2))
    print(f"report: {report}")
    if not keep:
        shutil.rmtree(scratch, ignore_errors=True)
        print(f"(scratch removed; pass --keep to retain {scratch})")
    if audit.failed:
        print("\nVERDICT: FAIL -- " + ", ".join(c.cid for c in audit.failed))
        sys.exit(1)
    print("\nVERDICT: PASS -- no forward-look / data-leak / determinism failures detected")
    sys.exit(0)


if __name__ == "__main__":
    main()
