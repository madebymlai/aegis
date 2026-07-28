"""Component authoring surface: the contracts as served to a component author.

Two kinds of artifact live here, one per component family:

- ``*_guide.py`` — render functions behind ``aerd show indicator-schema`` and
  ``aerd show strategy-schema`` (ADR-0019).
- ``*_example.py`` — the authorable reference components the guides embed.
  These are real component sources, round-tripped through the registry parser
  by the test suite; they are not illustrative prose.

Each guide module owns its own ``GUIDE_SCHEMA_VERSION``, so import from the
submodule rather than this package.
"""
