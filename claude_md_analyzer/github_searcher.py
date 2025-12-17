"""GitHub API integration for searching CLAUDE.md files."""

import os
import time
import base64
from typing import List, Optional, Generator
from datetime import datetime
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import Repository, ClaudeFile, SearchQuery

console = Console()


class GitHubSearcher:
    """Search GitHub for CLAUDE.md files."""

    SEARCH_API = "https://api.github.com/search/code"
    RATE_LIMIT_DELAY = 2  # seconds between requests to avoid rate limiting

    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub searcher.

        Args:
            token: GitHub personal access token (optional but recommended for higher rate limits)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Claude-MD-Analyzer/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def search(
        self,
        query: Optional[SearchQuery] = None,
        max_results: int = 100,
        progress_callback: Optional[callable] = None,
    ) -> List[ClaudeFile]:
        """
        Search for CLAUDE.md files on GitHub.

        Args:
            query: Search query parameters
            max_results: Maximum number of results to return
            progress_callback: Optional callback for progress updates

        Returns:
            List of ClaudeFile objects
        """
        if query is None:
            query = SearchQuery()

        files = []
        page = 1
        per_page = min(30, max_results)  # GitHub max is 30 for code search

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Searching GitHub...", total=None)

            while len(files) < max_results:
                # Search for both variations
                for filename in ["CLAUDE.md", "claude.md", "Claude.md"]:
                    if len(files) >= max_results:
                        break

                    search_query = query.to_github_query().replace(
                        f"filename:{query.filename}", f"filename:{filename}"
                    )

                    params = {
                        "q": search_query,
                        "per_page": per_page,
                        "page": page,
                        "sort": query.sort_by if query.sort_by != "stars" else None,
                    }

                    progress.update(
                        task,
                        description=f"Searching for {filename} (page {page})...",
                    )

                    try:
                        response = requests.get(
                            self.SEARCH_API, headers=self.headers, params=params
                        )
                        response.raise_for_status()
                        data = response.json()

                        items = data.get("items", [])
                        if not items:
                            break

                        for item in items:
                            if len(files) >= max_results:
                                break

                            claude_file = self._process_search_result(item, progress, task)
                            if claude_file:
                                # Check for duplicates
                                if not any(
                                    f.sha == claude_file.sha for f in files
                                ):
                                    files.append(claude_file)
                                    if progress_callback:
                                        progress_callback(len(files), claude_file)

                        # Rate limiting
                        time.sleep(self.RATE_LIMIT_DELAY)

                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 403:
                            console.print(
                                "[yellow]Rate limit reached. Waiting...[/yellow]"
                            )
                            time.sleep(60)  # Wait a minute
                            continue
                        else:
                            console.print(f"[red]Error: {e}[/red]")
                            break
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                        break

                page += 1
                if page > 10:  # GitHub limits to 1000 results (10 pages * 100)
                    break

        # Sort by stars
        files.sort(key=lambda x: x.stars, reverse=True)
        return files[:max_results]

    def _process_search_result(
        self, item: dict, progress: Progress, task
    ) -> Optional[ClaudeFile]:
        """Process a single search result item."""
        try:
            repo_data = item.get("repository", {})
            repo_full_name = repo_data.get("full_name", "")

            progress.update(task, description=f"Fetching {repo_full_name}...")

            # Get repository details for stars
            repo_info = self._get_repo_info(repo_full_name)
            if not repo_info:
                return None

            # Get file content
            content = self._get_file_content(item.get("url", ""))
            if not content:
                return None

            repository = Repository(
                name=repo_data.get("name", ""),
                full_name=repo_full_name,
                description=repo_info.get("description"),
                stars=repo_info.get("stargazers_count", 0),
                url=repo_data.get("html_url", ""),
                language=repo_info.get("language"),
                topics=repo_info.get("topics", []),
                updated_at=datetime.fromisoformat(
                    repo_info.get("updated_at", "").replace("Z", "+00:00")
                ) if repo_info.get("updated_at") else None,
            )

            return ClaudeFile(
                repository=repository,
                path=item.get("path", ""),
                content=content,
                raw_url=item.get("html_url", "").replace(
                    "github.com", "raw.githubusercontent.com"
                ).replace("/blob/", "/"),
                html_url=item.get("html_url", ""),
                size=len(content),
                sha=item.get("sha", ""),
            )

        except Exception as e:
            console.print(f"[yellow]Warning: Could not process {item.get('path', 'unknown')}: {e}[/yellow]")
            return None

    def _get_repo_info(self, full_name: str) -> Optional[dict]:
        """Get repository information."""
        try:
            url = f"https://api.github.com/repos/{full_name}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _get_file_content(self, api_url: str) -> Optional[str]:
        """Get file content from GitHub API."""
        try:
            response = requests.get(api_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            content = data.get("content", "")
            encoding = data.get("encoding", "")

            if encoding == "base64":
                return base64.b64decode(content).decode("utf-8")
            return content

        except Exception:
            return None

    def get_file_by_url(self, html_url: str) -> Optional[ClaudeFile]:
        """
        Get a specific CLAUDE.md file by its GitHub URL.

        Args:
            html_url: GitHub HTML URL of the file

        Returns:
            ClaudeFile object or None
        """
        try:
            # Parse URL to get repo and path
            # Format: https://github.com/owner/repo/blob/branch/path
            parts = html_url.replace("https://github.com/", "").split("/")
            if len(parts) < 4:
                return None

            owner = parts[0]
            repo = parts[1]
            full_name = f"{owner}/{repo}"
            path = "/".join(parts[4:])  # Skip blob/branch

            # Get repo info
            repo_info = self._get_repo_info(full_name)
            if not repo_info:
                return None

            # Get file content
            api_url = f"https://api.github.com/repos/{full_name}/contents/{path}"
            response = requests.get(api_url, headers=self.headers)
            response.raise_for_status()
            file_data = response.json()

            content = base64.b64decode(file_data.get("content", "")).decode("utf-8")

            repository = Repository(
                name=repo,
                full_name=full_name,
                description=repo_info.get("description"),
                stars=repo_info.get("stargazers_count", 0),
                url=f"https://github.com/{full_name}",
                language=repo_info.get("language"),
                topics=repo_info.get("topics", []),
                updated_at=datetime.fromisoformat(
                    repo_info.get("updated_at", "").replace("Z", "+00:00")
                ) if repo_info.get("updated_at") else None,
            )

            return ClaudeFile(
                repository=repository,
                path=path,
                content=content,
                raw_url=file_data.get("download_url", ""),
                html_url=html_url,
                size=file_data.get("size", len(content)),
                sha=file_data.get("sha", ""),
            )

        except Exception as e:
            console.print(f"[red]Error fetching file: {e}[/red]")
            return None

    def iter_search(
        self, query: Optional[SearchQuery] = None
    ) -> Generator[ClaudeFile, None, None]:
        """
        Iterator version of search for streaming results.

        Args:
            query: Search query parameters

        Yields:
            ClaudeFile objects as they are found
        """
        if query is None:
            query = SearchQuery()

        seen_shas = set()
        page = 1

        for filename in ["CLAUDE.md", "claude.md", "Claude.md"]:
            search_query = query.to_github_query().replace(
                f"filename:{query.filename}", f"filename:{filename}"
            )

            params = {
                "q": search_query,
                "per_page": 30,
                "page": page,
            }

            try:
                response = requests.get(
                    self.SEARCH_API, headers=self.headers, params=params
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("items", []):
                    claude_file = self._process_search_result(item, None, None)
                    if claude_file and claude_file.sha not in seen_shas:
                        seen_shas.add(claude_file.sha)
                        yield claude_file

                time.sleep(self.RATE_LIMIT_DELAY)

            except Exception:
                continue
