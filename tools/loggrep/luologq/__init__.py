"""qlog - Lightning-fast local log search and analysis."""

__version__ = "1.0.0"  # luologq enhanced

from .indexer import LogIndexer
from .search import LogSearcher
from .parser import LogParser

__all__ = ["LogIndexer", "LogSearcher", "LogParser"]
