"""Batch downloader for CLAUDE.md files."""

import os
import asyncio
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
import aiohttp
import requests
from rich.console import Console
from rich.progress import Progress, TaskID, BarColumn, TextColumn

from .models import ClaudeFile

console = Console()


class BatchDownloader:
    """Download multiple CLAUDE.md files efficiently."""

    def __init__(self, output_dir: str = "./downloads"):
        """
        Initialize downloader.

        Args:
            output_dir: Directory to save downloaded files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download_single(
        self,
        file: ClaudeFile,
        preserve_structure: bool = True,
    ) -> str:
        """
        Download a single file.

        Args:
            file: ClaudeFile to download
            preserve_structure: If True, preserve repository directory structure

        Returns:
            Path to downloaded file
        """
        if preserve_structure:
            # Create directory structure: owner/repo/path
            file_dir = self.output_dir / file.repository.full_name / os.path.dirname(file.path)
        else:
            # Flat structure with unique names
            file_dir = self.output_dir

        file_dir.mkdir(parents=True, exist_ok=True)

        if preserve_structure:
            output_path = self.output_dir / file.repository.full_name / file.path
        else:
            # Use repo name as prefix for flat structure
            safe_name = file.repository.full_name.replace("/", "_")
            output_path = file_dir / f"{safe_name}_CLAUDE.md"

        # Write content
        with open(output_path, 'w', encoding='utf-8') as f:
            # Add metadata header
            f.write(f"<!-- Source: {file.html_url} -->\n")
            f.write(f"<!-- Repository: {file.repository.full_name} -->\n")
            f.write(f"<!-- Stars: {file.repository.stars} -->\n")
            f.write(f"<!-- Downloaded by Claude MD Analyzer -->\n\n")
            f.write(file.content)

        return str(output_path)

    def download_batch(
        self,
        files: List[ClaudeFile],
        preserve_structure: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, str]:
        """
        Download multiple files synchronously.

        Args:
            files: List of ClaudeFile objects
            preserve_structure: If True, preserve repository directory structure
            progress_callback: Optional callback(current, total)

        Returns:
            Dictionary mapping repository names to downloaded file paths
        """
        downloaded = {}

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading files...", total=len(files))

            for i, file in enumerate(files):
                try:
                    path = self.download_single(file, preserve_structure)
                    downloaded[file.repository.full_name] = path
                except Exception as e:
                    console.print(f"[yellow]Failed to download {file.repository.full_name}: {e}[/yellow]")

                progress.update(task, advance=1)
                if progress_callback:
                    progress_callback(i + 1, len(files))

        return downloaded

    async def download_batch_async(
        self,
        files: List[ClaudeFile],
        preserve_structure: bool = True,
        max_concurrent: int = 10,
    ) -> Dict[str, str]:
        """
        Download multiple files asynchronously.

        Args:
            files: List of ClaudeFile objects
            preserve_structure: If True, preserve repository directory structure
            max_concurrent: Maximum concurrent downloads

        Returns:
            Dictionary mapping repository names to downloaded file paths
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        downloaded = {}

        async def download_one(file: ClaudeFile):
            async with semaphore:
                try:
                    # Since we have content, just write it
                    path = self.download_single(file, preserve_structure)
                    return file.repository.full_name, path
                except Exception as e:
                    console.print(f"[yellow]Failed: {file.repository.full_name}: {e}[/yellow]")
                    return file.repository.full_name, None

        tasks = [download_one(f) for f in files]
        results = await asyncio.gather(*tasks)

        for repo_name, path in results:
            if path:
                downloaded[repo_name] = path

        return downloaded

    def download_related(
        self,
        files: List[ClaudeFile],
        similarity_threshold: float = 0.5,
    ) -> Dict[str, List[str]]:
        """
        Download files grouped by similarity clusters.

        Args:
            files: List of ClaudeFile objects
            similarity_threshold: Minimum similarity for grouping

        Returns:
            Dictionary mapping cluster names to list of downloaded paths
        """
        from .embeddings import EmbeddingGenerator

        embedding_gen = EmbeddingGenerator()

        # Ensure embeddings
        files_with_embeddings = [f for f in files if f.embedding]
        if len(files_with_embeddings) != len(files):
            files = embedding_gen.generate_embeddings(files)

        # Cluster files
        clusters = embedding_gen.cluster_files(files)

        result = {}
        for i, cluster_indices in enumerate(clusters):
            cluster_name = f"cluster_{i}"
            cluster_dir = self.output_dir / cluster_name
            cluster_dir.mkdir(parents=True, exist_ok=True)

            paths = []
            for idx in cluster_indices:
                file = files[idx]
                output_path = cluster_dir / f"{file.repository.name}_CLAUDE.md"

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"<!-- Source: {file.html_url} -->\n")
                    f.write(f"<!-- Repository: {file.repository.full_name} -->\n")
                    f.write(f"<!-- Stars: {file.repository.stars} -->\n\n")
                    f.write(file.content)

                paths.append(str(output_path))

            result[cluster_name] = paths

        return result

    def create_index(self, downloaded: Dict[str, str]) -> str:
        """
        Create an index file for downloaded files.

        Args:
            downloaded: Dictionary mapping repo names to file paths

        Returns:
            Path to index file
        """
        index_path = self.output_dir / "INDEX.md"

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write("# Downloaded CLAUDE.md Files Index\n\n")
            f.write(f"Total files: {len(downloaded)}\n\n")
            f.write("## Files\n\n")

            for repo_name, path in sorted(downloaded.items()):
                rel_path = os.path.relpath(path, self.output_dir)
                f.write(f"- [{repo_name}]({rel_path})\n")

        return str(index_path)

    def export_metadata(
        self,
        files: List[ClaudeFile],
        format: str = "json",
    ) -> str:
        """
        Export file metadata to JSON or CSV.

        Args:
            files: List of ClaudeFile objects
            format: Output format ('json' or 'csv')

        Returns:
            Path to exported file
        """
        import json
        import csv

        if format == "json":
            output_path = self.output_dir / "metadata.json"
            data = [
                {
                    "repository": f.repository.full_name,
                    "description": f.repository.description,
                    "stars": f.repository.stars,
                    "url": f.repository.url,
                    "file_path": f.path,
                    "file_url": f.html_url,
                    "size": f.size,
                    "summary": f.summary,
                }
                for f in files
            ]
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        elif format == "csv":
            output_path = self.output_dir / "metadata.csv"
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Repository", "Description", "Stars", "URL",
                    "File Path", "File URL", "Size", "Summary"
                ])
                for file in files:
                    writer.writerow([
                        file.repository.full_name,
                        file.repository.description or "",
                        file.repository.stars,
                        file.repository.url,
                        file.path,
                        file.html_url,
                        file.size,
                        file.summary or "",
                    ])

        else:
            raise ValueError(f"Unknown format: {format}")

        return str(output_path)
