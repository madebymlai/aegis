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
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.returns', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['returns']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute fixed one-bar Close returns with the initial value filled."""\n'
        "    return data.feature('Close').pct_change().fillna(0.0)\n"
    )


def write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture component used by integration tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'signal_outputs': ['entries', 'exits']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(inputs):\n"
        '    """Emit a deterministic long-only signal for fixture runs."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    entries = close.gt(close.shift(1)).fillna(False)\n"
        "    exits = close.lt(close.shift(1)).fillna(False)\n"
        "    return {'entries': entries, 'exits': exits}\n"
    )
