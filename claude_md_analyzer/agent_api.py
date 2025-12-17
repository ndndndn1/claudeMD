"""Agent-friendly API for Claude MD Analyzer.

This module provides a simple, structured API designed for use by AI agents
and programmatic access. All methods return structured data (dictionaries)
that are easy to parse and process.
"""

import os
import json
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass

from .models import ClaudeFile, Repository, AnalysisResult, SearchQuery
from .github_searcher import GitHubSearcher
from .analyzer import ContentAnalyzer
from .embeddings import EmbeddingGenerator
from .visualizer import RelationshipVisualizer
from .downloader import BatchDownloader
from .merger import FileMerger


@dataclass
class AgentResponse:
    """Standardized response for agent API calls."""
    success: bool
    data: Any
    message: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


class AgentAPI:
    """
    Agent-friendly API for CLAUDE.md file analysis.

    This class provides a simplified interface designed for AI agents to:
    - Search for CLAUDE.md files on GitHub
    - Analyze file contents and structure
    - Find relationships between files
    - Download and merge files
    - Generate visualizations

    All methods return AgentResponse objects with structured data.

    Example:
        >>> api = AgentAPI(github_token="your_token")
        >>> result = api.search(max_results=10)
        >>> print(result.to_json())
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        output_dir: str = "./output",
    ):
        """
        Initialize the Agent API.

        Args:
            github_token: GitHub personal access token (optional)
            output_dir: Directory for output files
        """
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.output_dir = output_dir
        self._searcher = None
        self._analyzer = None
        self._embedding_gen = None
        self._visualizer = None
        self._downloader = None
        self._merger = None
        self._files: List[ClaudeFile] = []

    @property
    def searcher(self) -> GitHubSearcher:
        if self._searcher is None:
            self._searcher = GitHubSearcher(self.github_token)
        return self._searcher

    @property
    def analyzer(self) -> ContentAnalyzer:
        if self._analyzer is None:
            self._analyzer = ContentAnalyzer()
        return self._analyzer

    @property
    def embedding_gen(self) -> EmbeddingGenerator:
        if self._embedding_gen is None:
            self._embedding_gen = EmbeddingGenerator()
        return self._embedding_gen

    @property
    def visualizer(self) -> RelationshipVisualizer:
        if self._visualizer is None:
            self._visualizer = RelationshipVisualizer(self.output_dir)
        return self._visualizer

    @property
    def downloader(self) -> BatchDownloader:
        if self._downloader is None:
            self._downloader = BatchDownloader(os.path.join(self.output_dir, "downloads"))
        return self._downloader

    @property
    def merger(self) -> FileMerger:
        if self._merger is None:
            self._merger = FileMerger(os.path.join(self.output_dir, "merged"))
        return self._merger

    # ==================== SEARCH OPERATIONS ====================

    def search(
        self,
        max_results: int = 50,
        min_stars: int = 0,
        language: Optional[str] = None,
    ) -> AgentResponse:
        """
        Search GitHub for CLAUDE.md files.

        Args:
            max_results: Maximum number of files to return
            min_stars: Minimum repository stars
            language: Filter by programming language

        Returns:
            AgentResponse with list of file summaries
        """
        try:
            query = SearchQuery(
                min_stars=min_stars,
                max_results=max_results,
                language=language,
            )
            self._files = self.searcher.search(query, max_results)

            data = {
                "total_found": len(self._files),
                "files": [
                    {
                        "repo": f.repository.full_name,
                        "stars": f.repository.stars,
                        "description": f.repository.description,
                        "url": f.html_url,
                        "size": f.size,
                    }
                    for f in self._files
                ],
            }

            return AgentResponse(
                success=True,
                data=data,
                message=f"Found {len(self._files)} CLAUDE.md files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Search failed",
                error=str(e),
            )

    def get_file(self, url: str) -> AgentResponse:
        """
        Get a specific CLAUDE.md file by URL.

        Args:
            url: GitHub URL of the file

        Returns:
            AgentResponse with file content and metadata
        """
        try:
            file = self.searcher.get_file_by_url(url)
            if file:
                self._files.append(file)
                return AgentResponse(
                    success=True,
                    data={
                        "repo": file.repository.full_name,
                        "stars": file.repository.stars,
                        "content": file.content,
                        "url": file.html_url,
                    },
                    message="File retrieved successfully",
                )
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="File not found",
                    error="Could not retrieve file from URL",
                )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Failed to get file",
                error=str(e),
            )

    # ==================== ANALYSIS OPERATIONS ====================

    def analyze(self, file_index: Optional[int] = None) -> AgentResponse:
        """
        Analyze CLAUDE.md files.

        Args:
            file_index: Index of specific file to analyze (None for all)

        Returns:
            AgentResponse with analysis results
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first to load files",
                )

            if file_index is not None:
                files_to_analyze = [self._files[file_index]]
            else:
                files_to_analyze = self._files

            analyzed = self.analyzer.analyze_batch(files_to_analyze)

            # Update internal state
            if file_index is not None:
                self._files[file_index] = analyzed[0]
            else:
                self._files = analyzed

            data = {
                "analyzed_count": len(analyzed),
                "results": [
                    {
                        "repo": f.repository.full_name,
                        "summary": f.summary,
                        "sections": [s["title"] for s in (f.structure or {}).get("sections", [])],
                        "keywords": (f.structure or {}).get("keywords", [])[:10],
                        "stats": (f.structure or {}).get("stats", {}),
                    }
                    for f in analyzed
                ],
            }

            return AgentResponse(
                success=True,
                data=data,
                message=f"Analyzed {len(analyzed)} files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Analysis failed",
                error=str(e),
            )

    def get_summary_table(self) -> AgentResponse:
        """
        Get a summary table of all loaded files.

        Returns:
            AgentResponse with summary table data
        """
        if not self._files:
            return AgentResponse(
                success=False,
                data=None,
                message="No files loaded",
                error="Run search() first",
            )

        table_data = [
            {
                "repo": f.repository.full_name,
                "stars": f.repository.stars,
                "description": f.repository.description or "N/A",
                "url": f.html_url,
                "size": f.size,
                "summary": f.summary or "Not analyzed",
            }
            for f in sorted(self._files, key=lambda x: x.repository.stars, reverse=True)
        ]

        return AgentResponse(
            success=True,
            data={"table": table_data},
            message=f"Summary of {len(self._files)} files",
        )

    # ==================== EMBEDDING OPERATIONS ====================

    def generate_embeddings(self) -> AgentResponse:
        """
        Generate embeddings for all loaded files.

        Returns:
            AgentResponse with embedding stats
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() and analyze() first",
                )

            self._files = self.embedding_gen.generate_embeddings(self._files)
            stats = self.embedding_gen.get_embedding_stats(self._files)

            return AgentResponse(
                success=True,
                data=stats,
                message=f"Generated embeddings for {len(self._files)} files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Embedding generation failed",
                error=str(e),
            )

    def find_similar(
        self,
        file_index: int,
        top_k: int = 5,
    ) -> AgentResponse:
        """
        Find files similar to a specific file.

        Args:
            file_index: Index of the target file
            top_k: Number of similar files to return

        Returns:
            AgentResponse with similar files
        """
        try:
            if file_index >= len(self._files):
                return AgentResponse(
                    success=False,
                    data=None,
                    message="Invalid file index",
                    error=f"Index {file_index} out of range",
                )

            target = self._files[file_index]
            similar = self.embedding_gen.find_similar_files(
                target, self._files, top_k=top_k
            )

            data = {
                "target": target.repository.full_name,
                "similar_files": [
                    {
                        "repo": f.repository.full_name,
                        "similarity": round(score, 3),
                        "url": f.html_url,
                    }
                    for f, score in similar
                ],
            }

            return AgentResponse(
                success=True,
                data=data,
                message=f"Found {len(similar)} similar files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Similarity search failed",
                error=str(e),
            )

    def cluster_files(self, n_clusters: Optional[int] = None) -> AgentResponse:
        """
        Cluster files based on embeddings.

        Args:
            n_clusters: Number of clusters (auto if None)

        Returns:
            AgentResponse with cluster assignments
        """
        try:
            clusters = self.embedding_gen.cluster_files(self._files, n_clusters)

            data = {
                "num_clusters": len(clusters),
                "clusters": [
                    {
                        "cluster_id": i,
                        "files": [self._files[idx].repository.full_name for idx in indices],
                    }
                    for i, indices in enumerate(clusters)
                ],
            }

            return AgentResponse(
                success=True,
                data=data,
                message=f"Created {len(clusters)} clusters",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Clustering failed",
                error=str(e),
            )

    # ==================== VISUALIZATION OPERATIONS ====================

    def visualize(
        self,
        types: Optional[List[str]] = None,
    ) -> AgentResponse:
        """
        Generate visualizations.

        Args:
            types: List of visualization types ('scatter', 'heatmap', 'network', 'table')
                   If None, generates all types.

        Returns:
            AgentResponse with paths to generated files
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first",
                )

            # Ensure embeddings exist
            if not any(f.embedding for f in self._files):
                self._files = self.embedding_gen.generate_embeddings(self._files)

            result = AnalysisResult(files=self._files)
            paths = self.visualizer.visualize_all(result)

            # Filter by requested types
            if types:
                paths = {k: v for k, v in paths.items() if k in types}

            return AgentResponse(
                success=True,
                data={"visualization_paths": paths},
                message=f"Generated {len(paths)} visualizations",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Visualization failed",
                error=str(e),
            )

    # ==================== DOWNLOAD OPERATIONS ====================

    def download(
        self,
        file_indices: Optional[List[int]] = None,
        preserve_structure: bool = True,
    ) -> AgentResponse:
        """
        Download CLAUDE.md files.

        Args:
            file_indices: Indices of files to download (None for all)
            preserve_structure: Preserve directory structure

        Returns:
            AgentResponse with download paths
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first",
                )

            files_to_download = (
                [self._files[i] for i in file_indices]
                if file_indices
                else self._files
            )

            downloaded = self.downloader.download_batch(
                files_to_download, preserve_structure
            )
            index_path = self.downloader.create_index(downloaded)

            return AgentResponse(
                success=True,
                data={
                    "downloaded_count": len(downloaded),
                    "paths": downloaded,
                    "index_file": index_path,
                },
                message=f"Downloaded {len(downloaded)} files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Download failed",
                error=str(e),
            )

    def download_related(
        self,
        file_index: int,
        similarity_threshold: float = 0.5,
    ) -> AgentResponse:
        """
        Download files related to a specific file.

        Args:
            file_index: Index of the target file
            similarity_threshold: Minimum similarity for related files

        Returns:
            AgentResponse with download paths
        """
        try:
            target = self._files[file_index]
            similar = self.embedding_gen.find_similar_files(
                target, self._files, top_k=20, threshold=similarity_threshold
            )

            files_to_download = [target] + [f for f, _ in similar]
            downloaded = self.downloader.download_batch(files_to_download)

            return AgentResponse(
                success=True,
                data={
                    "target": target.repository.full_name,
                    "downloaded_count": len(downloaded),
                    "paths": downloaded,
                },
                message=f"Downloaded {len(downloaded)} related files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Download failed",
                error=str(e),
            )

    # ==================== MERGE OPERATIONS ====================

    def merge(
        self,
        file_indices: Optional[List[int]] = None,
        output_name: str = "MERGED_CLAUDE.md",
    ) -> AgentResponse:
        """
        Merge CLAUDE.md files into one.

        Args:
            file_indices: Indices of files to merge (None for all)
            output_name: Name of output file

        Returns:
            AgentResponse with merged file path
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first",
                )

            files_to_merge = (
                [self._files[i] for i in file_indices]
                if file_indices
                else self._files
            )

            merged_path = self.merger.merge(files_to_merge, output_name)

            return AgentResponse(
                success=True,
                data={
                    "merged_count": len(files_to_merge),
                    "output_path": merged_path,
                },
                message=f"Merged {len(files_to_merge)} files",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Merge failed",
                error=str(e),
            )

    def create_summary(self) -> AgentResponse:
        """
        Create a summary document of all files.

        Returns:
            AgentResponse with summary file path
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first",
                )

            summary_path = self.merger.create_summary_doc(self._files)

            return AgentResponse(
                success=True,
                data={"summary_path": summary_path},
                message="Created summary document",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Summary creation failed",
                error=str(e),
            )

    # ==================== EXPORT OPERATIONS ====================

    def export_metadata(self, format: str = "json") -> AgentResponse:
        """
        Export file metadata to JSON or CSV.

        Args:
            format: Output format ('json' or 'csv')

        Returns:
            AgentResponse with export file path
        """
        try:
            if not self._files:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="No files loaded",
                    error="Run search() first",
                )

            export_path = self.downloader.export_metadata(self._files, format)

            return AgentResponse(
                success=True,
                data={"export_path": export_path},
                message=f"Exported metadata to {format.upper()}",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Export failed",
                error=str(e),
            )

    # ==================== UTILITY OPERATIONS ====================

    def list_files(self) -> AgentResponse:
        """
        List all loaded files with their indices.

        Returns:
            AgentResponse with file list
        """
        if not self._files:
            return AgentResponse(
                success=False,
                data=None,
                message="No files loaded",
                error="Run search() first",
            )

        data = {
            "count": len(self._files),
            "files": [
                {
                    "index": i,
                    "repo": f.repository.full_name,
                    "stars": f.repository.stars,
                    "url": f.html_url,
                }
                for i, f in enumerate(self._files)
            ],
        }

        return AgentResponse(
            success=True,
            data=data,
            message=f"Loaded {len(self._files)} files",
        )

    def get_file_content(self, file_index: int) -> AgentResponse:
        """
        Get the content of a specific file.

        Args:
            file_index: Index of the file

        Returns:
            AgentResponse with file content
        """
        try:
            if file_index >= len(self._files):
                return AgentResponse(
                    success=False,
                    data=None,
                    message="Invalid file index",
                    error=f"Index {file_index} out of range",
                )

            f = self._files[file_index]
            return AgentResponse(
                success=True,
                data={
                    "repo": f.repository.full_name,
                    "path": f.path,
                    "content": f.content,
                    "size": f.size,
                    "url": f.html_url,
                },
                message="File content retrieved",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Failed to get file content",
                error=str(e),
            )

    def run_full_analysis(
        self,
        max_results: int = 50,
        min_stars: int = 0,
    ) -> AgentResponse:
        """
        Run a full analysis pipeline: search, analyze, embed, visualize.

        Args:
            max_results: Maximum number of files
            min_stars: Minimum repository stars

        Returns:
            AgentResponse with complete analysis results
        """
        try:
            # Search
            search_result = self.search(max_results=max_results, min_stars=min_stars)
            if not search_result.success:
                return search_result

            # Analyze
            analyze_result = self.analyze()
            if not analyze_result.success:
                return analyze_result

            # Embeddings
            embed_result = self.generate_embeddings()
            if not embed_result.success:
                return embed_result

            # Cluster
            cluster_result = self.cluster_files()

            # Visualize
            viz_result = self.visualize()

            # Create summary
            summary_result = self.create_summary()

            return AgentResponse(
                success=True,
                data={
                    "search": search_result.data,
                    "analysis": analyze_result.data,
                    "embeddings": embed_result.data,
                    "clusters": cluster_result.data if cluster_result.success else None,
                    "visualizations": viz_result.data if viz_result.success else None,
                    "summary": summary_result.data if summary_result.success else None,
                },
                message="Full analysis completed",
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                message="Full analysis failed",
                error=str(e),
            )
