"""Marks ``tests`` as a regular package so it owns the top-level ``tests`` name.

Without this file ``tests`` is a PEP 420 namespace package, and during import
resolution a namespace portion loses to any *regular* ``tests`` package that
appears later on ``sys.path`` — e.g. one a dependency mis-packages into
site-packages (eventkit ships its own top-level ``tests``). That shadowing makes
``from tests.support... import`` fail for the whole suite. As a regular package
found at the repo root (which precedes site-packages on ``sys.path``), this repo's
``tests`` wins. The subdirectories stay namespace packages, so per-file test
collection is unchanged.
"""
