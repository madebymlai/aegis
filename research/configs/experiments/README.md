# Experiment Configs

Tracked runnable baseline YAMLs are intentionally absent from this directory. Use the scaffold walkthrough notebook for the public, runnable learning path:

- `docs/examples/scaffold_experiment_walkthrough.ipynb`

Local experiment YAMLs in this directory are ignored by git so you can keep private research drafts without committing them.

Ignored files are not a secret-management mechanism. Do not put API keys, provider tokens, or credentials directly in experiment YAMLs or notebooks. Use environment-backed secret references, and do not force-add local experiment configs unless they are intentionally reviewed as tracked artifacts.

The walkthrough is scaffold evidence only. It is not validated trading methodology, empirical edge, or investment advice.

## Data Sources

Experiment configs set `data.source` to an Aegis local source or to a VectorBT PRO data class discovered at runtime. Local sources are:

- `synthetic` - generated OHLCV scaffold data.
- `csv` - local CSV OHLCV data.

VectorBT source IDs are derived from installed `vbt.*Data` class names by removing the `Data` suffix and lowercasing the result. For example, `YFData` becomes `yf` and `CCXTData` becomes `ccxt`. The currently installed VectorBT provider registry exposes:

| `data.source` | `VectorBT class`                                     |
| ------------- | ---------------------------------------------------- |
| `alpaca`      | `vectorbtpro.data.custom.alpaca.AlpacaData`          |
| `arcticdb`    | `vectorbtpro.data.custom.arcticdb.ArcticDBData`      |
| `av`          | `vectorbtpro.data.custom.av.AVData`                  |
| `bento`       | `vectorbtpro.data.custom.bento.BentoData`            |
| `binance`     | `vectorbtpro.data.custom.binance.BinanceData`        |
| `ccxt`        | `vectorbtpro.data.custom.ccxt.CCXTData`              |
| `custom`      | `vectorbtpro.data.custom.custom.CustomData`          |
| `db`          | `vectorbtpro.data.custom.db.DBData`                  |
| `duckdb`      | `vectorbtpro.data.custom.duckdb.DuckDBData`          |
| `feather`     | `vectorbtpro.data.custom.feather.FeatherData`        |
| `file`        | `vectorbtpro.data.custom.file.FileData`              |
| `finpy`       | `vectorbtpro.data.custom.finpy.FinPyData`            |
| `gbm`         | `vectorbtpro.data.custom.gbm.GBMData`                |
| `gbmohlc`     | `vectorbtpro.data.custom.gbm_ohlc.GBMOHLCData`       |
| `hdf`         | `vectorbtpro.data.custom.hdf.HDFData`                |
| `local`       | `vectorbtpro.data.custom.local.LocalData`            |
| `ndl`         | `vectorbtpro.data.custom.ndl.NDLData`                |
| `parquet`     | `vectorbtpro.data.custom.parquet.ParquetData`        |
| `polygon`     | `vectorbtpro.data.custom.polygon.PolygonData`        |
| `random`      | `vectorbtpro.data.custom.random.RandomData`          |
| `randomohlc`  | `vectorbtpro.data.custom.random_ohlc.RandomOHLCData` |
| `remote`      | `vectorbtpro.data.custom.remote.RemoteData`          |
| `sql`         | `vectorbtpro.data.custom.sql.SQLData`                |
| `tv`          | `vectorbtpro.data.custom.tv.TVData`                  |
| `yf`          | `vectorbtpro.data.custom.yf.YFData`                  |

This list is runtime-derived, so it can change when VectorBT PRO adds, removes, or renames `*Data` classes. Provider-specific arguments belong in `data.provider_kwargs`, `data.wrapper_kwargs`, or `data.execution_kwargs`; never put API keys or tokens inline.
