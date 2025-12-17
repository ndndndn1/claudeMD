"""Command-line interface for Claude MD Analyzer."""

import os
import sys
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import SearchQuery
from .github_searcher import GitHubSearcher
from .analyzer import ContentAnalyzer
from .embeddings import EmbeddingGenerator
from .visualizer import RelationshipVisualizer
from .downloader import BatchDownloader
from .merger import FileMerger
from .agent_api import AgentAPI

app = typer.Typer(
    name="claude-md",
    help="GitHub CLAUDE.md file analyzer with embedding-based relationship visualization",
    add_completion=False,
)

console = Console()


@app.command()
def search(
    max_results: int = typer.Option(50, "--max", "-m", help="Maximum number of results"),
    min_stars: int = typer.Option(0, "--min-stars", "-s", help="Minimum repository stars"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Filter by language"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output JSON file"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub token"),
):
    """Search GitHub for CLAUDE.md files."""
    console.print(Panel("🔍 Searching for CLAUDE.md files on GitHub...", style="blue"))

    searcher = GitHubSearcher(token)
    query = SearchQuery(min_stars=min_stars, max_results=max_results, language=language)

    files = searcher.search(query, max_results)

    # Display results
    table = Table(title=f"Found {len(files)} CLAUDE.md files")
    table.add_column("Repository", style="cyan")
    table.add_column("Stars", style="yellow", justify="right")
    table.add_column("Description", style="dim")
    table.add_column("URL", style="blue")

    for f in files[:20]:  # Show top 20
        table.add_row(
            f.repository.full_name,
            str(f.repository.stars),
            (f.repository.description or "N/A")[:50],
            f.html_url,
        )

    console.print(table)

    if len(files) > 20:
        console.print(f"[dim]... and {len(files) - 20} more[/dim]")

    if output:
        import json
        with open(output, 'w') as f:
            json.dump([file.to_dict() for file in files], f, indent=2, default=str)
        console.print(f"[green]Results saved to {output}[/green]")


@app.command()
def analyze(
    url: Optional[str] = typer.Option(None, "--url", "-u", help="GitHub file URL to analyze"),
    input_file: Optional[str] = typer.Option(None, "--input", "-i", help="Input JSON from search"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output JSON file"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub token"),
):
    """Analyze CLAUDE.md file(s) and extract structure."""
    analyzer = ContentAnalyzer()
    searcher = GitHubSearcher(token)

    files = []
    if url:
        console.print(f"[blue]Fetching {url}...[/blue]")
        file = searcher.get_file_by_url(url)
        if file:
            files = [file]
        else:
            console.print("[red]Could not fetch file[/red]")
            return

    elif input_file:
        import json
        with open(input_file) as f:
            data = json.load(f)
        # Reconstruct files from JSON
        from .models import Repository, ClaudeFile
        from datetime import datetime
        for item in data:
            repo_data = item.get("repository", {})
            repo = Repository(
                name=repo_data.get("name", ""),
                full_name=repo_data.get("full_name", ""),
                description=repo_data.get("description"),
                stars=repo_data.get("stars", 0),
                url=repo_data.get("url", ""),
                language=repo_data.get("language"),
                topics=repo_data.get("topics", []),
            )
            files.append(ClaudeFile(
                repository=repo,
                path=item.get("path", ""),
                content=item.get("content", ""),
                raw_url=item.get("raw_url", ""),
                html_url=item.get("html_url", ""),
                size=item.get("size", 0),
                sha=item.get("sha", ""),
            ))

    if not files:
        console.print("[red]No files to analyze[/red]")
        return

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing files...", total=len(files))
        for file in files:
            analyzer.analyze(file)
            progress.advance(task)

    # Display analysis
    for file in files:
        console.print(Panel(f"[bold]{file.repository.full_name}[/bold]", style="cyan"))
        console.print(f"[yellow]Summary:[/yellow] {file.summary}")

        if file.structure:
            console.print(f"\n[yellow]Sections:[/yellow]")
            for section in file.structure.get("sections", [])[:10]:
                console.print(f"  • {section['title']} ({section['line_count']} lines)")

            console.print(f"\n[yellow]Keywords:[/yellow] {', '.join(file.structure.get('keywords', [])[:10])}")

            stats = file.structure.get("stats", {})
            console.print(f"\n[yellow]Stats:[/yellow] {stats.get('total_lines', 0)} lines, {stats.get('total_words', 0)} words, {stats.get('code_blocks_count', 0)} code blocks")

    if output:
        import json
        with open(output, 'w') as f:
            json.dump([file.to_dict() for file in files], f, indent=2, default=str)
        console.print(f"[green]Analysis saved to {output}[/green]")


@app.command()
def visualize(
    input_file: str = typer.Option(..., "--input", "-i", help="Input JSON from analyze"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    types: Optional[str] = typer.Option(None, "--types", help="Visualization types (comma-separated)"),
):
    """Generate relationship visualizations."""
    import json
    from .models import Repository, ClaudeFile, AnalysisResult

    console.print("[blue]Loading files...[/blue]")

    with open(input_file) as f:
        data = json.load(f)

    # Reconstruct files
    files = []
    for item in data:
        repo_data = item.get("repository", {})
        repo = Repository(
            name=repo_data.get("name", ""),
            full_name=repo_data.get("full_name", ""),
            description=repo_data.get("description"),
            stars=repo_data.get("stars", 0),
            url=repo_data.get("url", ""),
            language=repo_data.get("language"),
            topics=repo_data.get("topics", []),
        )
        files.append(ClaudeFile(
            repository=repo,
            path=item.get("path", ""),
            content=item.get("content", ""),
            raw_url=item.get("raw_url", ""),
            html_url=item.get("html_url", ""),
            size=item.get("size", 0),
            sha=item.get("sha", ""),
            summary=item.get("summary"),
            structure=item.get("structure"),
            embedding=item.get("embedding"),
        ))

    console.print(f"[blue]Loaded {len(files)} files[/blue]")

    # Generate embeddings if needed
    if not any(f.embedding for f in files):
        console.print("[blue]Generating embeddings...[/blue]")
        embedding_gen = EmbeddingGenerator()
        files = embedding_gen.generate_embeddings(files)

    # Create visualizations
    visualizer = RelationshipVisualizer(output_dir)
    result = AnalysisResult(files=files)

    console.print("[blue]Creating visualizations...[/blue]")
    paths = visualizer.visualize_all(result)

    console.print(Panel("Visualizations created:", style="green"))
    for viz_type, path in paths.items():
        console.print(f"  [cyan]{viz_type}:[/cyan] {path}")


@app.command()
def download(
    input_file: str = typer.Option(..., "--input", "-i", help="Input JSON from search/analyze"),
    output_dir: str = typer.Option("./downloads", "--output", "-o", help="Output directory"),
    flat: bool = typer.Option(False, "--flat", "-f", help="Use flat directory structure"),
):
    """Download CLAUDE.md files."""
    import json
    from .models import Repository, ClaudeFile

    console.print("[blue]Loading files...[/blue]")

    with open(input_file) as f:
        data = json.load(f)

    # Reconstruct files
    files = []
    for item in data:
        repo_data = item.get("repository", {})
        repo = Repository(
            name=repo_data.get("name", ""),
            full_name=repo_data.get("full_name", ""),
            description=repo_data.get("description"),
            stars=repo_data.get("stars", 0),
            url=repo_data.get("url", ""),
            language=repo_data.get("language"),
            topics=repo_data.get("topics", []),
        )
        files.append(ClaudeFile(
            repository=repo,
            path=item.get("path", ""),
            content=item.get("content", ""),
            raw_url=item.get("raw_url", ""),
            html_url=item.get("html_url", ""),
            size=item.get("size", 0),
            sha=item.get("sha", ""),
        ))

    console.print(f"[blue]Downloading {len(files)} files...[/blue]")

    downloader = BatchDownloader(output_dir)
    downloaded = downloader.download_batch(files, preserve_structure=not flat)
    index_path = downloader.create_index(downloaded)

    console.print(Panel(f"Downloaded {len(downloaded)} files to {output_dir}", style="green"))
    console.print(f"  Index file: {index_path}")


@app.command()
def merge(
    input_file: str = typer.Option(..., "--input", "-i", help="Input JSON from search/analyze"),
    output: str = typer.Option("MERGED_CLAUDE.md", "--output", "-o", help="Output filename"),
    output_dir: str = typer.Option("./merged", "--dir", "-d", help="Output directory"),
):
    """Merge multiple CLAUDE.md files into one."""
    import json
    from .models import Repository, ClaudeFile

    console.print("[blue]Loading files...[/blue]")

    with open(input_file) as f:
        data = json.load(f)

    # Reconstruct files
    files = []
    for item in data:
        repo_data = item.get("repository", {})
        repo = Repository(
            name=repo_data.get("name", ""),
            full_name=repo_data.get("full_name", ""),
            description=repo_data.get("description"),
            stars=repo_data.get("stars", 0),
            url=repo_data.get("url", ""),
            language=repo_data.get("language"),
            topics=repo_data.get("topics", []),
        )
        files.append(ClaudeFile(
            repository=repo,
            path=item.get("path", ""),
            content=item.get("content", ""),
            raw_url=item.get("raw_url", ""),
            html_url=item.get("html_url", ""),
            size=item.get("size", 0),
            sha=item.get("sha", ""),
            summary=item.get("summary"),
            structure=item.get("structure"),
        ))

    console.print(f"[blue]Merging {len(files)} files...[/blue]")

    merger = FileMerger(output_dir)
    merged_path = merger.merge(files, output)

    console.print(Panel(f"Merged {len(files)} files into {merged_path}", style="green"))


@app.command()
def full(
    max_results: int = typer.Option(30, "--max", "-m", help="Maximum number of results"),
    min_stars: int = typer.Option(0, "--min-stars", "-s", help="Minimum repository stars"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub token"),
):
    """Run full analysis pipeline: search, analyze, embed, visualize."""
    console.print(Panel("🚀 Running full CLAUDE.md analysis pipeline", style="bold blue"))

    api = AgentAPI(github_token=token, output_dir=output_dir)

    # Search
    console.print("\n[bold cyan]Step 1: Searching GitHub...[/bold cyan]")
    result = api.search(max_results=max_results, min_stars=min_stars)
    if not result.success:
        console.print(f"[red]Search failed: {result.error}[/red]")
        return
    console.print(f"[green]Found {result.data['total_found']} files[/green]")

    # Analyze
    console.print("\n[bold cyan]Step 2: Analyzing content...[/bold cyan]")
    result = api.analyze()
    if not result.success:
        console.print(f"[red]Analysis failed: {result.error}[/red]")
        return
    console.print(f"[green]Analyzed {result.data['analyzed_count']} files[/green]")

    # Embeddings
    console.print("\n[bold cyan]Step 3: Generating embeddings...[/bold cyan]")
    result = api.generate_embeddings()
    if not result.success:
        console.print(f"[red]Embedding generation failed: {result.error}[/red]")
        return
    console.print(f"[green]Mean similarity: {result.data['mean_similarity']:.3f}[/green]")

    # Cluster
    console.print("\n[bold cyan]Step 4: Clustering files...[/bold cyan]")
    result = api.cluster_files()
    if result.success:
        console.print(f"[green]Created {result.data['num_clusters']} clusters[/green]")

    # Visualize
    console.print("\n[bold cyan]Step 5: Creating visualizations...[/bold cyan]")
    result = api.visualize()
    if result.success:
        console.print("[green]Visualizations created:[/green]")
        for name, path in result.data['visualization_paths'].items():
            console.print(f"  • {name}: {path}")

    # Summary
    console.print("\n[bold cyan]Step 6: Creating summary...[/bold cyan]")
    result = api.create_summary()
    if result.success:
        console.print(f"[green]Summary saved to: {result.data['summary_path']}[/green]")

    # Export metadata
    console.print("\n[bold cyan]Step 7: Exporting metadata...[/bold cyan]")
    result = api.export_metadata(format="json")
    if result.success:
        console.print(f"[green]Metadata exported to: {result.data['export_path']}[/green]")

    console.print(Panel("✅ Full analysis complete!", style="bold green"))


@app.command()
def open_file(
    url: str = typer.Argument(..., help="GitHub URL of the file"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub token"),
):
    """Open and display a specific CLAUDE.md file."""
    searcher = GitHubSearcher(token)

    console.print(f"[blue]Fetching {url}...[/blue]")
    file = searcher.get_file_by_url(url)

    if file:
        console.print(Panel(f"[bold]{file.repository.full_name}[/bold]", style="cyan"))
        console.print(f"⭐ Stars: {file.repository.stars}")
        console.print(f"📝 Description: {file.repository.description or 'N/A'}")
        console.print(f"📁 Path: {file.path}")
        console.print(f"📏 Size: {file.size} bytes\n")
        console.print(Panel(file.content[:5000] + ("..." if len(file.content) > 5000 else ""), title="Content"))
    else:
        console.print("[red]Could not fetch file[/red]")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
