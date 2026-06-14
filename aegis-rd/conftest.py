"""Pin the test session's working directory to the aegis-rd package root.

Both the suite (fixtures referenced as ``tests/fixtures/...``) and the product
under test (``aerd`` discovers components from ``research/components`` relative to
the current directory) resolve paths against the package root. pytest sets its
rootdir from ``pyproject.toml`` but does not change the process CWD, so running
the suite from the monorepo root (or an IDE/CI launched elsewhere) left those
relative paths unresolved. Anchoring CWD here makes the suite pass regardless of
where pytest is invoked; when already run from aegis-rd/ this is a no-op.
"""

import os
from pathlib import Path

os.chdir(Path(__file__).parent)
