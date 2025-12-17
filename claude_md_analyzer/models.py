"""Data models for Claude MD Analyzer."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


@dataclass
class Repository:
    """Repository metadata."""
    name: str
    full_name: str
    description: Optional[str]
    stars: int
    url: str
    language: Optional[str]
    topics: List[str] = field(default_factory=list)
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "stars": self.stars,
            "url": self.url,
            "language": self.language,
            "topics": self.topics,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class ClaudeFile:
    """CLAUDE.md file with content and metadata."""
    repository: Repository
    path: str
    content: str
    raw_url: str
    html_url: str
    size: int
    sha: str
    summary: Optional[str] = None
    structure: Optional[Dict[str, Any]] = None
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repository": self.repository.to_dict(),
            "path": self.path,
            "content": self.content,
            "raw_url": self.raw_url,
            "html_url": self.html_url,
            "size": self.size,
            "sha": self.sha,
            "summary": self.summary,
            "structure": self.structure,
            "embedding": self.embedding,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @property
    def repo_name(self) -> str:
        return self.repository.full_name

    @property
    def stars(self) -> int:
        return self.repository.stars


@dataclass
class AnalysisResult:
    """Analysis result with all files and relationships."""
    files: List[ClaudeFile]
    relationships: Optional[Dict[str, Any]] = None
    clusters: Optional[List[List[int]]] = None
    visualization_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": len(self.files),
            "files": [f.to_dict() for f in self.files],
            "relationships": self.relationships,
            "clusters": self.clusters,
            "visualization_path": self.visualization_path,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def get_summary_table(self) -> List[Dict[str, Any]]:
        """Get a summary table of all files."""
        return [
            {
                "repo": f.repository.full_name,
                "stars": f.repository.stars,
                "description": f.repository.description or "N/A",
                "path": f.path,
                "size": f.size,
                "summary": f.summary or "N/A",
            }
            for f in sorted(self.files, key=lambda x: x.stars, reverse=True)
        ]


@dataclass
class SearchQuery:
    """Search query parameters."""
    filename: str = "CLAUDE.md"
    min_stars: int = 0
    max_results: int = 100
    language: Optional[str] = None
    sort_by: str = "stars"  # stars, updated, indexed

    def to_github_query(self) -> str:
        """Convert to GitHub search query string."""
        parts = [f"filename:{self.filename}"]
        if self.min_stars > 0:
            parts.append(f"stars:>={self.min_stars}")
        if self.language:
            parts.append(f"language:{self.language}")
        return " ".join(parts)
