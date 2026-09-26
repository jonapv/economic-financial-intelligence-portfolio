"""Macro Intelligence Brief — economic calculation layer.

Phase 1 scope: the deterministic transformations that turn published source
series into the statistics an economist would actually quote, plus the data
model that carries a derived result.

This package performs **no I/O of any kind**: no network access, no file
reading, no environment lookups, no clock reads. Every function is pure and
takes its inputs explicitly, including `retrieved_at`. That is what makes the
economic calculations reproducible and testable.
"""

__all__ = ["calculations", "errors", "indicators", "models"]
