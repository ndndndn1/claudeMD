"""
Claude MD Analyzer - GitHub CLAUDE.md file analyzer with embedding-based relationship visualization.

Features:
- Search GitHub for CLAUDE.md files (case-insensitive)
- Analyze repository metadata (name, stars, description)
- Summarize file contents
- Visualize relationships using embeddings
- Batch download and merge related files
- Agent-friendly API interface
- KùzuDB graph database storage
- MCP server for Claude Code integration
"""

__version__ = "1.1.0"

from .models import ClaudeFile, Repository, AnalysisResult
from .github_searcher import GitHubSearcher
from .analyzer import ContentAnalyzer
from .embeddings import EmbeddingGenerator
from .visualizer import RelationshipVisualizer
from .downloader import BatchDownloader
from .merger import FileMerger
from .agent_api import AgentAPI
from .storage import KuzuStorage, RepoNode

__all__ = [
    "ClaudeFile",
    "Repository",
    "AnalysisResult",
    "GitHubSearcher",
    "ContentAnalyzer",
    "EmbeddingGenerator",
    "RelationshipVisualizer",
    "BatchDownloader",
    "FileMerger",
    "AgentAPI",
    "KuzuStorage",
    "RepoNode",
]
