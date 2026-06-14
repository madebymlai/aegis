"""Put the fixture component modules on the import path.

``ExecutionBundle.compute_weights`` loads strategy/indicator components by module
name via ``importlib.import_module``. The runtime is deliberately decoupled from
the research component catalog, so tests ship their own minimal components under
``_components/`` and expose them here.
"""

import pathlib
import sys

_COMPONENTS = pathlib.Path(__file__).parent / "_components"
if str(_COMPONENTS) not in sys.path:
    sys.path.insert(0, str(_COMPONENTS))
