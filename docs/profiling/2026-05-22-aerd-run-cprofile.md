# Aegis RD cProfile Run Path Report

Date: 2026-05-22

## Artifact Locations

- Binary cProfile artifact: `/tmp/opencode/aegis-local-e2e.prof`
- Failed dry-run profile artifact: `/tmp/opencode/aegis-dry-run.prof`
- Successful CLI output capture: `/home/laimk/.local/share/opencode/tool-output/tool_e4fe65d450010wkPwceXlpR0vO`
- Profiled command path: `aerd run <config>` via `research.aegis_research.cli:main`

## Commands Run

Failed smaller bundled config, included because it established that this config no longer reaches execution:

```bash
uv run python -m cProfile -o "/tmp/opencode/aegis-dry-run.prof" -m research.aegis_research.cli --json run "research/configs/component_ma_cross_dry_run.yaml" --run-id "profile-20260522-dry-run"
```

Exact output read:

```json
{"command": "run", "error": {"category": "config_validation", "details": {}, "message": "Invalid run config: strategy.id: unknown strategie component id"}, "ok": false, "schema_version": 1, "status": "error"}
```

Successful run used for cProfile:

```bash
uv run python -m cProfile -o "/tmp/opencode/aegis-local-e2e.prof" -m research.aegis_research.cli --json run "research/configs/local_component_e2e.yaml" --run-id "profile-20260522-local-e2e"
```

PStats extraction command:

```bash
uv run python -c "import pstats; s=pstats.Stats('/tmp/opencode/aegis-local-e2e.prof'); s.strip_dirs(); print('TOP CUMULATIVE'); s.sort_stats('cumulative').print_stats(80); print('TOP TOTTIME'); s.sort_stats('tottime').print_stats(80);"
```

Project-only extraction command:

```bash
uv run python -c "import pstats; s=pstats.Stats('/tmp/opencode/aegis-local-e2e.prof'); print('PROJECT CUMULATIVE'); s.sort_stats('cumulative').print_stats('research/aegis_research|research/components', 120); print('PROJECT TOTTIME'); s.sort_stats('tottime').print_stats('research/aegis_research|research/components', 120);"
```

Hotspot caller/callee extraction command:

```bash
uv run python -c "import pstats; s=pstats.Stats('/tmp/opencode/aegis-local-e2e.prof'); print('CALLERS _central_metric_series'); s.print_callers('/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341'); print('CALLEES _central_metric_series'); s.print_callees('/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341'); print('CALLERS portfolio_metrics'); s.print_callers('/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38'); print('CALLEES portfolio_metrics'); s.print_callees('/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38');"
```

## Run Path Identified

- `pyproject.toml` defines `aerd = "research.aegis_research.cli:main"`.
- `research/aegis_research/cli.py:29` calls `_main`.
- `research/aegis_research/cli.py:79` registers `run` subcommand.
- `research/aegis_research/cli_commands/run.py:55` handles `aerd run`.
- `research/aegis_research/cli_commands/run.py:87` calls `run_strategy_sweep`.
- `research/aegis_research/strategy_runs.py:83` owns the run sweep.
- `research/aegis_research/strategy_runs.py:168` enters `_run_optimization_strategy_sweep`.
- `research/aegis_research/optimization/runner.py:82` enters `execute_optimization`.
- `research/aegis_research/optimization/runner.py:242` builds the VBT `cv_split` callable.
- `research/aegis_research/optimization/runner.py:290` evaluates each split/parameter candidate.

## Config Used

`research/configs/local_component_e2e.yaml` was the successful profile input.

Important observed settings:

```yaml
data:
  source: yf
  symbols: [XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE, XLC]
  start: '2020-01-01'
  end: '2025-01-01'
  timeframe: 1D
  arrays: [OHLCV]

optimization:
  search: random
  random_subset: 512
  seed: 11
  evidence:
    return_grid: 'off'
  split:
    method: from_rolling
    params:
      length: 252
      offset: 126
      split: 0.5
    max_splits: 10
```

## Successful CLI Output Read

Exact visible output read from `/home/laimk/.local/share/opencode/tool-output/tool_e4fe65d450010wkPwceXlpR0vO`:

```text
1: 
2:  27%|██▋       | 3/11 [00:02<00:05,  1.40it/s, symbol=XLV]
3:  36%|███▋      | 4/11 [00:02<00:03,  1.84it/s, symbol=XLI]
4:  45%|████▌     | 5/11 [00:02<00:02,  2.25it/s, symbol=XLY]
5:  55%|█████▍    | 6/11 [00:02<00:01,  2.65it/s, symbol=XLP]
6:  64%|██████▎   | 7/11 [00:03<00:01,  2.97it/s, symbol=XLU]
7:  73%|███████▎  | 8/11 [00:03<00:00,  3.40it/s, symbol=XLB]
8:  82%|████████▏ | 9/11 [00:03<00:00,  3.88it/s, symbol=XLRE]
9:  91%|█████████ | 10/11 [00:03<00:00,  4.30it/s, symbol=XLC]
10: 100%|██████████| 11/11 [00:03<00:00,  4.27it/s, symbol=XLC]
11: 100%|██████████| 11/11 [00:03<00:00,  2.88it/s, symbol=XLC]
12: 
13:  25%|██▌       | 1/4 [02:10<06:30, 130.05s/it, split=1]
14:  50%|█████     | 2/4 [04:20<04:20, 130.15s/it, split=2]
15:  75%|███████▌  | 3/4 [06:29<02:09, 129.85s/it, split=3]
16: 100%|██████████| 4/4 [08:40<00:00, 130.23s/it, split=3]
17: 100%|██████████| 4/4 [08:40<00:00, 130.14s/it, split=3]
18: {"artifacts": {"strategy_artifact_id": "strategy.run", "strategy_artifact_path": "runs/local_e2e/profile-20260522-local-e2e/strategy_run.json"}, "candidate_store": {"path": "runs/local_e2e/.candidate_store/candidates.sqlite3"}, "command": "run", "evidence_type": "optimization", "leaderboard": {"summary": {"attempted_splits": 4, "selected_splits": 4, "unique_winner_count": 4}, "top_rows": [{"candidate_key": "cand_cb523df7b2c32554e6950be507fb5563", "eligible_split_count": 4, "held_out_row_count": 126, "metrics": {"max_dd": 1.3092495437256377, "sharpe_ratio": 1.9298805994552393, "total_fees_paid": 108.4661799507336, "total_return": 5.904599562003241, "total_trades": 16.0, "win_rate": 62.5}, "oos_metric_max": 1.9298805994552393, "oos_metric_min": 1.9298805994552393, "oos_metric_values": [1.9298805994552393], "params": {"component__696e64696361746f7273__6c6f63616c2e6532652e6d6f6d656e74756d__6c6f63616c2e6532652e6d6f6d656e74756d__6c6f6f6b6261636b": 84, "component__696e64696361746f7273__6c6f63616c2e6532652e6d6f6d656e74756d__6c6f63616c2e6532652e6d6f6d656e74756d__736d6f6f74685f77696e646f77": 3, "component__696e64696361746f7273__6c6f63616c2e6532652e7472656e645f6d61__6c6f63616c2e6532652e7472656e645f6d61__666173745f77696e646f77": 20, "component__696e64696361746f7273__6c6f63616c2e6532652e7472656e645f6d61__6c6f63616c2e6532652e7472656e645f6d61__736c6f70655f77696e646f77": 10, "component__696e64696361746f7273__6c6f63616c2e6532652e7472656e645f6d61__6c6f63616c2e6532652e7472656e645f6d61__6c6f775f77696e646f77": 160, "component__696e64696361746f7273__6c6f63616c2e6532652e7472656e645f6d61__6c6f63616c2e6532652e7472656e645f6d61__7774797065": "exp", "component__696e64696361746f7273__6c6f63616c2e6532652e766f6c6174696c697479__6c6f63616c2e6532652e766f6c6174696c697479__726567696d655f77696e646f77": 126, "component__696e64696361746f7273__6c6f63616c2e6532652e766f6c6174696c697479__6c6f63616c2e6532652e766f6c6174696c697479__77696e646f77": 40, "component__73747261746567696573__6c6f63616c2e6532652e65746... (line truncated to 2000 chars)
```

## Hotspot Summary

- The profiled run made `1,008,067,173` function calls in `526.344` seconds under cProfile.
- `run_strategy_sweep` consumed `526.332` seconds cumulative.
- `execute_optimization` consumed `520.609` seconds cumulative.
- VBT `cv_split` called the Aegis CV callable `2,056` times.
- `_evaluate_cv_slice` consumed `519.205` seconds across those `2,056` calls, about `0.253s` per evaluation under cProfile.
- `_central_metric_series` consumed `365.753` seconds across those calls.
- `portfolio_metrics` consumed `364.224` seconds across those calls.
- `simulate_portfolio` consumed `103.095` seconds across those calls.
- Component pipeline work was smaller: trend indicator `22.979s`, volatility `14.393s`, strategy `8.004s`, momentum `4.522s` cumulative.
- The slowest visible structural issue is repeated per-candidate metric extraction and diagnostics, not market data loading or artifact writing.

## Exact cProfile Output: Top Cumulative

```text
TOP CUMULATIVE
Fri May 22 15:35:59 2026    /tmp/opencode/aegis-local-e2e.prof

         1008067173 function calls (976603124 primitive calls) in 526.344 seconds

   Ordered by: cumulative time
   List reduced from 19445 to 80 due to restriction <80>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   3869/1    0.058    0.000  526.384  526.384 {built-in method builtins.exec}
      2/1    0.000    0.000  526.384  526.384 <string>:1(<module>)
      2/1    0.000    0.000  526.382  526.382 <frozen runpy>:201(run_module)
      2/1    0.000    0.000  526.382  526.382 <frozen runpy>:65(_run_code)
      4/3    0.000    0.000  526.357  175.452 cli.py:1(<module>)
        1    0.000    0.000  526.353  526.353 cli.py:29(main)
        1    0.000    0.000  526.352  526.352 cli.py:34(_main)
        1    0.000    0.000  526.352  526.352 run.py:55(handle_run)
        1    0.000    0.000  526.352  526.352 run.py:62(_handle_strategy_run)
        1    0.002    0.002  526.332  526.332 strategy_runs.py:83(run_strategy_sweep)
   4126/2    0.037    0.000  524.384  262.192 execution.py:3185(execute)
   4126/2    0.062    0.000  524.383  262.192 execution.py:2610(run)
   4126/2    0.009    0.000  524.383  262.192 execution.py:2339(call_execute)
   4126/2    0.174    0.000  524.383  262.191 execution.py:319(execute)
        1    0.001    0.001  522.420  522.420 strategy_runs.py:168(_run_optimization_strategy_sweep)
        1    0.000    0.000  520.609  520.609 runner.py:82(execute_optimization)
        1    0.000    0.000  520.594  520.594 decorators.py:454(wrapper)
        1    0.000    0.000  520.594  520.594 decorators.py:168(wrapper)
        1    0.000    0.000  520.589  520.589 base.py:4245(apply)
        4    0.000    0.000  520.560  130.140 base.py:4737(_process_chunk_tasks)
        8    0.002    0.000  520.560   65.070 decorators.py:490(apply_wrapper)
       12    0.009    0.001  520.543   43.379 params.py:2611(wrapper)
       12    0.018    0.001  520.528   43.377 params.py:2094(run)
     2056    0.028    0.000  519.233    0.253 runner.py:261(cv_callable)
     2056    0.114    0.000  519.205    0.253 runner.py:290(_evaluate_cv_slice)
     2056    0.064    0.000  365.753    0.178 runner.py:341(_central_metric_series)
     2056    0.239    0.000  364.224    0.177 reports.py:38(portfolio_metrics)
    12336    0.091    0.000  361.990    0.029 reports.py:240(_capture_warnings)
1266714/487476    1.855    0.000  236.964    0.000 ca_registry.py:3278(run)
413280/125426    0.812    0.000  216.470    0.002 ca_registry.py:3201(run_func)
546896/41120    4.230    0.000  212.116    0.005 base.py:12586(resolve_shortcut_attr)
     4112    1.240    0.000  207.244    0.050 stats_builder.py:142(stats)
23107389/15103574    5.671    0.000  199.632    0.000 {built-in method builtins.getattr}
1112467/444267    0.665    0.000  197.407    0.000 decorators.py:303(__get__)
1186530/802044    3.425    0.000  167.055    0.000 ca_registry.py:3251(run_func_and_cache)
     8224    0.089    0.000  154.400    0.019 decorators.py:46(new_method)
100744/26728    0.623    0.000  141.492    0.005 decorators.py:152(new_prop)
     8224    0.156    0.000  131.830    0.016 base.py:12285(get_returns_acc)
    20560    0.047    0.000  111.364    0.005 attr_.py:689(deep_getattr)
74016/20560    0.345    0.000  111.317    0.005 attr_.py:421(deep_getattr)
    41120    0.179    0.000  110.578    0.003 stats_builder.py:569(_getattr_func)
     2056    0.043    0.000  108.114    0.053 reports.py:48(<lambda>)
     2056    0.139    0.000  103.095    0.050 portfolios.py:42(simulate_portfolio)
801889/594219    1.293    0.000  101.538    0.000 decorators.py:570(wrapper)
     2056    0.030    0.000   99.203    0.048 reports.py:45(<lambda>)
    16448    0.257    0.000   83.119    0.005 attr_.py:596(resolve_attr)
     2056    0.026    0.000   82.418    0.040 reports.py:319(_optional_diagnostics)
     4112    0.016    0.000   82.231    0.020 reports.py:334(<lambda>)
    12336    0.270    0.000   82.177    0.007 base.py:10673(get_value)
     8224    0.232    0.000   68.257    0.008 base.py:11409(get_returns)
   172759    1.115    0.000   62.316    0.000 config.py:938(copy)
     2056    0.329    0.000   60.244    0.029 base.py:4642(from_signals)
  1393862    1.016    0.000   59.561    0.000 inspect.py:3346(signature)
   263168    1.116    0.000   59.201    0.000 jit_registry.py:1315(resolve_option)
  1393862    1.391    0.000   58.545    0.000 inspect.py:3081(from_callable)
1873716/1410349    7.358    0.000   57.531    0.000 inspect.py:2501(_signature_from_callable)
   263168    5.655    0.000   56.413    0.000 jit_registry.py:1089(resolve)
  1186530    2.752    0.000   51.600    0.000 ca_registry.py:3215(get_args_hash)
6372548/1508056   21.385    0.000   51.437    0.000 config.py:206(copy_dict)
     2056    0.113    0.000   50.155    0.024 component_source.py:183(pipeline)
995736/403229    0.988    0.000   49.224    0.000 functools.py:982(__get__)
   758713    3.811    0.000   47.882    0.000 hashing.py:76(hash_args)
     2056    0.013    0.000   47.270    0.023 preparing.py:837(result)
117213/80205    0.832    0.000   43.906    0.001 config.py:2235(replace)
  1410341   13.995    0.000   42.841    0.000 inspect.py:2397(_signature_from_function)
   536208    3.676    0.000   41.457    0.000 config.py:2092(__init__)
     4112    0.058    0.000   39.884    0.010 base.py:8725(get_drawdowns)
   758726    6.845    0.000   39.117    0.000 parsing.py:241(annotate_args)
536818/536810    8.333    0.000   38.180    0.000 config.py:630(__init__)
    12336    0.422    0.000   37.186    0.003 base.py:10556(get_asset_value)
   106914    0.113    0.000   37.043    0.000 wrapping.py:1779(freq)
     2056    0.010    0.000   36.290    0.018 reports.py:56(<lambda>)
    16448    0.248    0.000   36.229    0.002 base.py:10390(get_init_value)
     2056    0.012    0.000   35.934    0.017 reports.py:54(<lambda>)
    22616    0.154    0.000   35.649    0.002 price_records.py:72(__init__)
     8224    0.051    0.000   35.611    0.004 base.py:12201(get_bm_returns)
```

## Exact cProfile Output: Project Cumulative

```text
PROJECT CUMULATIVE
Fri May 22 15:35:59 2026    /tmp/opencode/aegis-local-e2e.prof

         1008067173 function calls (976603124 primitive calls) in 526.344 seconds

   Ordered by: cumulative time
   List reduced from 20651 to 554 due to restriction <'research/aegis_research|research/components'>
   List reduced from 554 to 120 due to restriction <120>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      2/1    0.000    0.000  526.353  526.353 /home/laimk/git/aegis-rd/research/aegis_research/cli.py:1(<module>)
        1    0.000    0.000  526.353  526.353 /home/laimk/git/aegis-rd/research/aegis_research/cli.py:29(main)
        1    0.000    0.000  526.352  526.352 /home/laimk/git/aegis-rd/research/aegis_research/cli.py:34(_main)
        1    0.000    0.000  526.352  526.352 /home/laimk/git/aegis-rd/research/aegis_research/cli_commands/run.py:55(handle_run)
        1    0.000    0.000  526.352  526.352 /home/laimk/git/aegis-rd/research/aegis_research/cli_commands/run.py:62(_handle_strategy_run)
        1    0.002    0.002  526.332  526.332 /home/laimk/git/aegis-rd/research/aegis_research/strategy_runs.py:83(run_strategy_sweep)
        1    0.001    0.001  522.420  522.420 /home/laimk/git/aegis-rd/research/aegis_research/strategy_runs.py:168(_run_optimization_strategy_sweep)
        1    0.000    0.000  520.609  520.609 /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:82(execute_optimization)
     2056    0.028    0.000  519.233    0.253 /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:261(cv_callable)
     2056    0.114    0.000  519.205    0.253 /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:290(_evaluate_cv_slice)
     2056    0.064    0.000  365.753    0.178 /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341(_central_metric_series)
     2056    0.239    0.000  364.224    0.177 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:38(portfolio_metrics)
    12336    0.091    0.000  361.990    0.029 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:240(_capture_warnings)
     2056    0.043    0.000  108.114    0.053 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:48(<lambda>)
     2056    0.139    0.000  103.095    0.050 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:42(simulate_portfolio)
     2056    0.030    0.000   99.203    0.048 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:45(<lambda>)
     2056    0.026    0.000   82.418    0.040 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:319(_optional_diagnostics)
     4112    0.016    0.000   82.231    0.020 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:334(<lambda>)
     2056    0.113    0.000   50.155    0.024 /home/laimk/git/aegis-rd/research/aegis_research/optimization/component_source.py:183(pipeline)
     2056    0.010    0.000   36.290    0.018 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:56(<lambda>)
     2056    0.012    0.000   35.934    0.017 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:54(<lambda>)
     2056    0.044    0.000   26.737    0.013 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:281(_portfolio_diagnostics)
     2056    0.032    0.000   24.585    0.012 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:474(portfolio_record_counts)
     2056    0.051    0.000   22.979    0.011 /home/laimk/git/aegis-rd/research/components/indicators/local_trend_ma.py:39(run)
     2056    0.067    0.000   14.393    0.007 /home/laimk/git/aegis-rd/research/components/indicators/local_volatility.py:32(run)
     2056    0.042    0.000    9.879    0.005 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:344(_simulation_signals)
     2056    0.103    0.000    8.004    0.004 /home/laimk/git/aegis-rd/research/components/strategies/local_trend_filter.py:61(run)
     6168    0.107    0.000    4.821    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:527(_count_by_symbol)
        1    0.000    0.000    4.665    4.665 /home/laimk/git/aegis-rd/research/aegis_research/cli_commands/run.py:1(<module>)
        1    0.000    0.000    4.646    4.646 /home/laimk/git/aegis-rd/research/aegis_research/cli_support/output.py:1(<module>)
        1    0.000    0.000    4.642    4.642 /home/laimk/git/aegis-rd/research/aegis_research/config.py:1(<module>)
        1    0.000    0.000    4.642    4.642 /home/laimk/git/aegis-rd/research/aegis_research/configuration/resolution.py:1(<module>)
        1    0.000    0.000    4.611    4.611 /home/laimk/git/aegis-rd/research/aegis_research/configuration/validation.py:1(<module>)
     2056    0.024    0.000    4.522    0.002 /home/laimk/git/aegis-rd/research/components/indicators/local_momentum.py:32(run)
        1    0.000    0.000    4.263    4.263 /home/laimk/git/aegis-rd/research/aegis_research/market_data/sources.py:1(<module>)
        1    0.000    0.000    3.859    3.859 /home/laimk/git/aegis-rd/research/aegis_research/market_data/loading.py:52(load_market_data_result)
        1    0.000    0.000    3.826    3.826 /home/laimk/git/aegis-rd/research/aegis_research/market_data/loading.py:242(<lambda>)
        1    0.000    0.000    3.826    3.826 /home/laimk/git/aegis-rd/research/aegis_research/market_data/loading.py:304(_load_vbt_remote_source)
        1    0.000    0.000    3.825    3.825 /home/laimk/git/aegis-rd/research/aegis_research/market_data/loading.py:441(_pull_remote)
     2056    0.029    0.000    3.028    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:387(_entry_size_frame)
     4112    0.062    0.000    2.466    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:499(_assert_numeric_non_null)
     2056    0.018    0.000    2.069    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:252(_execution_timing_kwargs)
     2056    0.033    0.000    1.887    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:443(_next_open_executable_mask)
     2056    0.042    0.000    1.530    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:422(_sizing_summary)
   152144    0.697    0.000    1.227    0.000 /home/laimk/git/aegis-rd/research/aegis_research/reports.py:276(_metric_evidence)
       11    0.000    0.000    1.102    0.100 /home/laimk/git/aegis-rd/research/aegis_research/provenance/manifest.py:226(atomic_write_json)
     2056    0.010    0.000    1.064    0.001 /home/laimk/git/aegis-rd/research/aegis_research/portfolios.py:214(_validate_signal_frames)
        1    0.000    0.000    1.006    1.006 /home/laimk/git/aegis-rd/research/aegis_research/strategy_runs.py:631(_write_strategy_artifact)
```

## Exact Caller/Callee Output Read

```text
CALLERS _central_metric_series
   Random listing order was used
   List reduced from 20651 to 1 due to restriction <'/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341'>

Function                                                                                             was called by...
                                                                                                         ncalls  tottime  cumtime
/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341(_central_metric_series)  <-    2056    0.064  365.753  /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:290(_evaluate_cv_slice)


CALLEES _central_metric_series
   Random listing order was used
   List reduced from 20651 to 1 due to restriction <'/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341'>

Function                                                                                             called...
                                                                                                         ncalls  tottime  cumtime
/home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341(_central_metric_series)  ->       2    0.000    0.000  /home/laimk/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib/python3.12/threading.py:601(is_set)
                                                                                                              0    0.000    0.000  /home/laimk/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib/python3.12/threading.py:637(wait)
                                                                                                           2056    0.002    0.004  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/pandas/core/indexes/base.py:1693(name)
                                                                                                           2056    0.015    0.353  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/pandas/core/series.py:392(__init__)
                                                                                                              2    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/tqdm/_monitor.py:47(get_instances)
                                                                                                              1    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/tqdm/std.py:110(__enter__)
                                                                                                              1    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/tqdm/std.py:113(__exit__)
                                                                                                              1    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/tqdm/std.py:760(get_lock)
                                                                                                           2056    0.239  364.224  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:38(portfolio_metrics)
                                                                                                              1    0.000    0.000  {built-in method time.time}


CALLERS portfolio_metrics
   Random listing order was used
   List reduced from 20651 to 1 due to restriction <'/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38'>

Function                                                                           was called by...
                                                                                       ncalls  tottime  cumtime
/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38(portfolio_metrics)  <-    2056    0.239  364.224  /home/laimk/git/aegis-rd/research/aegis_research/optimization/runner.py:341(_central_metric_series)


CALLEES portfolio_metrics
   Random listing order was used
   List reduced from 20651 to 1 due to restriction <'/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38'>

Function                                                                           called...
                                                                                       ncalls  tottime  cumtime
/home/laimk/git/aegis-rd/research/aegis_research/reports.py:38(portfolio_metrics)  ->       1    0.000    0.000  /home/laimk/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib/python3.12/threading.py:302(__exit__)
                                                                                           18    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/vectorbtpro/registries/ca_registry.py:2620(<lambda>)
                                                                                           34    0.000    0.000  /home/laimk/git/aegis-rd/.venv/lib/python3.12/site-packages/vectorbtpro/registries/ca_registry.py:3044(<lambda>)
                                                                                         2056    0.002    0.002  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:219(portfolio_metric_assumptions)
                                                                                         2055    0.004    0.004  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:230(_metric_roles)
                                                                                         8224    0.058  279.681  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:240(_capture_warnings)
                                                                                        12334    0.019    0.028  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:254(_vbt_metric_config)
                                                                                        12334    0.005    0.005  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:267(_metric_source)
                                                                                    148004/110276    0.469    0.713  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:276(_metric_evidence)
                                                                                         2055    0.026   82.377  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:319(_optional_diagnostics)
                                                                                        10279    0.022    0.570  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:432(_raw_metric_map)
                                                                                        10279    0.009    0.207  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:496(_headline_raw_metric)
                                                                                         2055    0.001    0.006  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:503(_headline_raw_value)
                                                                                         2055    0.007    0.019  /home/laimk/git/aegis-rd/research/aegis_research/reports.py:513(_raw_value_map)
                                                                                        26723    0.005    0.005  {method 'items' of 'dict' objects}
```

## Source Details Read

Key source functions inspected:

- `research/aegis_research/optimization/runner.py:82` `execute_optimization`
- `research/aegis_research/optimization/runner.py:242` `_build_cv_callable`
- `research/aegis_research/optimization/runner.py:290` `_evaluate_cv_slice`
- `research/aegis_research/optimization/runner.py:341` `_central_metric_series`
- `research/aegis_research/reports.py:38` `portfolio_metrics`
- `research/aegis_research/reports.py:119` `portfolio_metrics_by_candidate_group`
- `research/aegis_research/portfolios.py:42` `simulate_portfolio`
- `research/aegis_research/portfolios.py:101` `simulate_portfolio_batch`
- `research/components/indicators/local_trend_ma.py:39` `run`
- `research/components/indicators/local_volatility.py:32` `run`
- `research/components/indicators/local_momentum.py:32` `run`
- `research/components/strategies/local_trend_filter.py:61` `run`

Important implementation facts observed:

- `_evaluate_cv_slice` currently runs the full component pipeline, simulates one VBT portfolio, and computes full portfolio metrics for each candidate/split evaluation.
- `portfolio_metrics` computes shared-cash stats, per-symbol stats, shared-cash Sharpe, per-symbol Sharpe, and optional diagnostics on every evaluation.
- The optimization path asks for only central metric values in `_central_metric_series`, but it currently builds the full report-quality metric payload to get those values.
- `simulate_portfolio_batch` and `portfolio_metrics_by_candidate_group` already exist and preserve candidate scope through `vbt.ExceptLevel("symbol")`, but the current `execute_optimization` path does not call them.
- Component calculations consume meaningful time but are smaller than repeated metric/report extraction.

## Questions For Reviewers

- Is there a VectorBT-native way to keep `cv_split` semantics while batching candidate portfolios per split?
- Can ranking use a lighter VectorBT metric path during optimization and defer full report-quality `portfolio_metrics` to selected winners only?
- Can `vbt.Portfolio.from_signals` be called once per split with candidate columns and `group_by=vbt.ExceptLevel("symbol")` while preserving the current shared-cash-per-candidate semantics?
- Can VectorBT parameterization produce full candidate `entries` and `exits` arrays before portfolio simulation, rather than invoking the pipeline and `pf.stats` once per candidate?
- Which hotspot is user-code optimizable versus expected VectorBT overhead from repeated object construction, stats builders, and cached accessor resolution?

## Reviewer Dispatch

Four parallel reviewers were launched against this report and the source tree:

- `ses_1b0143392ffeV35O4H2eetXApr`: performance lens focused on metric/report overhead.
- `ses_1b0143383ffeSwXLgjrUtF8QAh`: performance-oracle lens focused on VectorBT-native candidate batching.
- `ses_1b0143366ffe5fbOaSCwxGWc3R`: framework-docs lens focused on VectorBT PRO APIs and docs.
- `ses_1b014335affe4R5RBGeGqpzwXl`: adversarial performance lens focused on false leads and semantic traps.

## Reviewer Findings

### Finding 1: Full Report Metrics Are In The Optimization Hot Path

Consensus: this is the largest project-owned slowdown.

Evidence:

- `_central_metric_series` calls `portfolio_metrics` for every CV evaluation.
- `portfolio_metrics` consumed `364.224s` cumulative out of `520.609s` in `execute_optimization`.
- The run made `2,056` `_evaluate_cv_slice` calls.
- `portfolio_metrics` computes shared stats, per-symbol stats, shared Sharpe, per-symbol Sharpe, optional diagnostics, warning capture, metric evidence, metric roles, and per-symbol evidence even though optimization selection needs only central metric values.

Recommended minimal optimization:

- Add an optimization-only central metric function that returns exactly `PORTFOLIO_METRIC_VALUE_KEYS`.
- Use direct VBT portfolio methods/records for central metrics during selection.
- Keep `portfolio_metrics` for final report-quality evidence and selected winners.

VBT-native candidate APIs to verify in implementation:

- `vbt.Portfolio.get_sharpe_ratio`
- `vbt.Portfolio.get_total_return`
- `vbt.Portfolio.get_max_drawdown`
- `pf.trades.count()` or `pf.get_trades().count()`
- `pf.trades.win_rate` or direct trade win-rate accessor available in the installed VBT version
- `pf.orders.fees.sum()`

Semantic traps:

- `pf.get_total_return()` returns a fraction; existing `stats` title `Total Return [%]` is percent.
- `pf.get_max_drawdown()` usually returns a negative fraction; current `max_dd` is a positive loss magnitude percentage.
- Win rate may be a fraction while current report values are percent.
- Sharpe warnings and non-finite values must still produce the same rankability behavior as `_metric_evidence`.

### Finding 2: Optional Diagnostics Should Be Deferred

Consensus: optional diagnostics are report evidence, not ranking inputs.

Evidence:

- `_optional_diagnostics` consumed about `82.418s` cumulative across `2,055` calls.
- `probabilistic_sharpe_ratio` and `deflated_sharpe_ratio` are not part of `PORTFOLIO_METRIC_VALUE_KEYS`.

Recommended minimal optimization:

- Do not compute `_optional_diagnostics` in the optimization CV callable.
- Compute full diagnostics only for selected/promoted candidates where report evidence is written.

Semantic trap:

- If any public optimization artifact currently promises losing-candidate diagnostics, deferral is a schema/contract change. Review artifacts before removing them from any exposed grid output.

### Finding 3: Candidate Batching Is Feasible But Should Be Phase 2

Consensus: batching is likely valuable, but it changes the execution shape more than the metric-path fix.

Current batching primitives already exist:

- `research/aegis_research/portfolios.py:101` `simulate_portfolio_batch`
- `research/aegis_research/reports.py:119` `portfolio_metrics_by_candidate_group`

VBT-native batching model:

```python
pf = vbt.Portfolio.from_signals(
    close=expanded_close,
    entries=simulation_entries,
    exits=simulation_exits,
    cash_sharing=True,
    group_by=vbt.ExceptLevel("symbol"),
    call_seq="auto",
    ...
)
```

Required column shape:

```text
(candidate_or_param_levels..., symbol)
```

Example:

```text
[(0, "XLK"), (0, "XLF"), (1, "XLK"), (1, "XLF")]
```

Expected benefit:

- Replace one `Portfolio.from_signals` per candidate/split with one or a few batched calls per split/chunk.
- The profiled run spent `103.095s` cumulative in scalar `simulate_portfolio` and `60.244s` in `Portfolio.from_signals` under cProfile.

Semantic traps:

- `cash_sharing=True` must be scoped per candidate, not globally across candidates.
- `group_by=vbt.ExceptLevel("symbol")` requires monolithic/sorted groups and `symbol` as the excluded level.
- Candidate identity must match the sampled index from `vbt.combine_params` so candidate evidence remains stable.
- Batching trades CPU overhead for memory: `random_subset * symbol_count` columns per chunk.

### Finding 4: `cv_split` Is Not The Best Place To Hide Batching

The docs/code review found that `vbt.cv_split` combines splitting and parameterized execution. It stores training grid results and then evaluates selected candidates on test sets. Its decorated function is naturally parameterized one combination at a time.

Implication:

- Keep `cv_split` for the low-risk metric-path optimization.
- For full candidate batching, consider a separate runner path that uses VBT splitter semantics plus explicit `vbt.combine_params` sampling and Aegis-owned per-split batching.
- Do not silently batch inside the existing scalar CV callable unless tests prove result-index and winner-selection equivalence.

### Finding 5: Measurement Needs A Non-cProfile Baseline

Adversarial concern: cProfile is useful for call counts and relative hotspots, but the absolute `526.344s` runtime may be inflated by profiling Python-heavy VBT internals.

Recommended profiling follow-ups:

- Run the same config without cProfile under `/usr/bin/time` or explicit `perf_counter` spans.
- Add spans around data loading, split construction, pipeline execution, portfolio simulation, metric extraction, and artifact writing.
- Run a sampling profiler such as `py-spy` or `scalene` to validate percentages without deterministic profiler amplification.

## VectorBT MCP Verification

Reference resolution succeeded for the core APIs:

```text
OK vbt.cv_split vectorbtpro.generic.splitting.decorators.cv_split
OK vbt.Param vectorbtpro.utils.params.Param
OK vbt.combine_params vectorbtpro.utils.params.combine_params
OK vbt.Portfolio.from_signals vectorbtpro.portfolio.base.Portfolio.from_signals
OK vbt.ExceptLevel vectorbtpro.base.indexes.ExceptLevel
OK vbt.Portfolio.get_sharpe_ratio vectorbtpro.portfolio.base.Portfolio.get_sharpe_ratio
OK vbt.Portfolio.get_total_return vectorbtpro.portfolio.base.Portfolio.get_total_return
OK vbt.Portfolio.get_max_drawdown vectorbtpro.portfolio.base.Portfolio.get_max_drawdown
```

Relevant `cv_split` source documentation excerpt from VBT MCP:

```text
Decorator that integrates `split` and `vectorbtpro.utils.params.parameterized`
to facilitate cross-validation. For each split/set range, the decorated function is applied as follows:

* In the training set, the function is parameterized across the entire grid of parameters
    and its results are stored.
* For testing sets, the stored grid results are used to evaluate a selection
    that determines the best parameter combination, which is then executed.
* Optionally, grid results can be returned in addition to the selection,
    controlled by `return_grid`.

!!! warning
    Train and test sets within each split must execute in the same thread/process
    due to the way grid results are stored and accessed using `grid_results_map`.
```

Relevant support-context result from VBT MCP for `ExceptLevel("symbol")`:

```text
You can use `group_by=vbt.ExceptLevel("symbol")` and set `cash_sharing=True`, since "symbol" is the lowest level.

No, `ExceptLevel` means grouping by all levels except the symbol level. This results in one group for each unique parameter combination.

Note: "Unique" means your symbol level should be the lowest, with all higher levels having unique values. For example, columns like `[(0, "BTC"), (0, "ETH"), (1, "BTC"), (1, "ETH")]` form two groups: 0 and 1.
```

## Recommended Implementation Order

1. Add a non-profiled timing baseline for the current config.
2. Add a lightweight central metric function and switch `_central_metric_series` to it.
3. Add parity tests comparing the lightweight values against current `portfolio_metrics` for all `PORTFOLIO_METRIC_VALUE_KEYS`.
4. Re-run cProfile and sampling profiling to confirm `portfolio_metrics` leaves the hot path.
5. Prototype a separate batched per-split runner using `simulate_portfolio_batch`, chunked candidate columns, and grouped metrics.
6. Add scalar-versus-batched equivalence tests before replacing the scalar `cv_split` path.
