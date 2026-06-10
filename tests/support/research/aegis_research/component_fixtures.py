from __future__ import annotations

from pathlib import Path


def write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture component used by integration tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.returns', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['returns'], "
        "}\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute fixed one-bar Close returns with the initial value filled."""\n'
        "    return data.feature('Close').pct_change().fillna(0.0)\n"
        "\n# %% wide compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        '    """Return wide indicator output."""\n'
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    arr = close.pct_change().fillna(0.0).values\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i in range(n_candidates):\n"
        "        result[:, i * S:(i + 1) * S] = arr\n"
        "    return {'returns': result}\n"
    )


def write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture component used by integration tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'output_name': 'active', 'owns_portfolio': False, "
        "}\n"
        "\n# %% main compute\n"
        "def run(inputs):\n"
        '    """Emit a deterministic active allocation frame for fixture runs."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    selected = close.gt(close.shift(1)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide strategy output."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    close_arr = close.values\n"
        "    prev = np.roll(close_arr, 1, axis=0)\n"
        "    prev[0] = np.nan\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        selected = close_arr > prev\n"
        "        n_sel = np.nansum(selected, axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )
