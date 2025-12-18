#!/usr/bin/env python3
"""
MCP Server for CLAUDE.md Analyzer.
Provides tools for searching, analyzing, downloading, and merging CLAUDE.md files.
"""

import os
import json
import asyncio
import subprocess
import base64
from typing import Optional, List, Dict, Any
from datetime import datetime
from collections import Counter
import math
import re

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .storage import KuzuStorage, RepoNode


# Initialize server and storage
server = Server("claude-md-analyzer")
storage: Optional[KuzuStorage] = None

def get_storage() -> KuzuStorage:
    """Get or create storage instance."""
    global storage
    if storage is None:
        db_path = os.environ.get("CLAUDE_MD_DB_PATH", "./data/kuzu_db")
        storage = KuzuStorage(db_path)
    return storage


# ==================== HELPER FUNCTIONS ====================

def run_gh_command(args: List[str]) -> Optional[Any]:
    """Run gh CLI command and return JSON result."""
    try:
        result = subprocess.run(
            ['gh'] + args,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout else None
        return None
    except Exception:
        return None


def extract_keywords(content: str, max_keywords: int = 5) -> List[str]:
    """Extract keywords from content."""
    headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
    keywords = []
    for h in headers[:max_keywords]:
        cleaned = re.sub(r'[^\w\s]', '', h).strip().lower()
        if cleaned and len(cleaned) > 2:
            keywords.append(cleaned)
    return keywords[:max_keywords]


def generate_summary(content: str, max_length: int = 200) -> str:
    """Generate simple summary from content."""
    lines = content.strip().split('\n')
    summary_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            if summary_lines:
                break
            continue
        if line.startswith('#'):
            continue
        summary_lines.append(line)
        if len(' '.join(summary_lines)) > max_length:
            break

    summary = ' '.join(summary_lines)
    if len(summary) > max_length:
        summary = summary[:max_length] + "..."
    return summary


def calculate_tfidf_similarity(contents: List[str]) -> List[List[float]]:
    """Calculate TF-IDF based similarity matrix."""
    def tokenize(text):
        words = re.findall(r'\b[a-z]+\b', text.lower())
        return [w for w in words if len(w) > 2]

    docs = [tokenize(c) for c in contents]
    vocab = set()
    for doc in docs:
        vocab.update(doc)
    vocab = sorted(vocab)

    if not vocab:
        return [[0.0] * len(contents) for _ in range(len(contents))]

    word_to_idx = {w: i for i, w in enumerate(vocab)}
    n_docs = len(docs)
    df = Counter()
    for doc in docs:
        df.update(set(doc))

    vectors = []
    for doc in docs:
        tf = Counter(doc)
        vec = [0.0] * len(vocab)
        for word, count in tf.items():
            if word in word_to_idx:
                idx = word_to_idx[word]
                idf = math.log(n_docs / (df[word] + 1))
                vec[idx] = count * idf
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        vectors.append(vec)

    # Cosine similarity
    similarity = []
    for i in range(len(vectors)):
        row = []
        for j in range(len(vectors)):
            sim = sum(vectors[i][k] * vectors[j][k] for k in range(len(vocab)))
            row.append(sim)
        similarity.append(row)

    return similarity


# ==================== MCP TOOLS ====================

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="collect_claude_md",
            description="Collect CLAUDE.md files from GitHub and store in database",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of files to collect",
                        "default": 50
                    },
                    "calculate_similarity": {
                        "type": "boolean",
                        "description": "Calculate and store similarity relationships",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="search_claude_md",
            description="Search CLAUDE.md files in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (searches name, description)"
                    },
                    "min_stars": {
                        "type": "integer",
                        "description": "Minimum stars filter",
                        "default": 0
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language filter"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="open_file",
            description="Open and view a CLAUDE.md file content",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {
                        "type": "string",
                        "description": "Repository ID (full_name like 'owner/repo')"
                    }
                },
                "required": ["repo_id"]
            }
        ),
        Tool(
            name="analyze_file",
            description="Analyze a CLAUDE.md file and return structure/keywords",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {
                        "type": "string",
                        "description": "Repository ID (full_name like 'owner/repo')"
                    }
                },
                "required": ["repo_id"]
            }
        ),
        Tool(
            name="get_similar",
            description="Get similar repositories to a given one",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {
                        "type": "string",
                        "description": "Repository ID (full_name like 'owner/repo')"
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0-1)",
                        "default": 0.1
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 10
                    }
                },
                "required": ["repo_id"]
            }
        ),
        Tool(
            name="download_files",
            description="Download CLAUDE.md files to local directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of repository IDs to download"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory",
                        "default": "./downloads"
                    }
                },
                "required": ["repo_ids"]
            }
        ),
        Tool(
            name="merge_files",
            description="Merge multiple CLAUDE.md files into one",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of repository IDs to merge"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path",
                        "default": "./merged_claude.md"
                    }
                },
                "required": ["repo_ids"]
            }
        ),
        Tool(
            name="get_graph_data",
            description="Get graph data for visualization",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity for edges",
                        "default": 0.1
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional path to save JSON file"
                    }
                }
            }
        ),
        Tool(
            name="get_stats",
            description="Get database statistics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="export_json",
            description="Export database to JSON file",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_path": {
                        "type": "string",
                        "description": "Output file path",
                        "default": "./claude_md_data.json"
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    db = get_storage()

    if name == "collect_claude_md":
        return await collect_claude_md(
            db,
            arguments.get("max_results", 50),
            arguments.get("calculate_similarity", True)
        )

    elif name == "search_claude_md":
        return await search_claude_md(
            db,
            arguments.get("query"),
            arguments.get("min_stars", 0),
            arguments.get("language"),
            arguments.get("limit", 20)
        )

    elif name == "open_file":
        return await open_file(db, arguments["repo_id"])

    elif name == "analyze_file":
        return await analyze_file(db, arguments["repo_id"])

    elif name == "get_similar":
        return await get_similar(
            db,
            arguments["repo_id"],
            arguments.get("min_similarity", 0.1),
            arguments.get("limit", 10)
        )

    elif name == "download_files":
        return await download_files(
            db,
            arguments["repo_ids"],
            arguments.get("output_dir", "./downloads")
        )

    elif name == "merge_files":
        return await merge_files(
            db,
            arguments["repo_ids"],
            arguments.get("output_path", "./merged_claude.md")
        )

    elif name == "get_graph_data":
        return await get_graph_data(
            db,
            arguments.get("min_similarity", 0.1),
            arguments.get("output_path")
        )

    elif name == "get_stats":
        return await get_stats(db)

    elif name == "export_json":
        return await export_json(
            db,
            arguments.get("output_path", "./claude_md_data.json")
        )

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ==================== TOOL IMPLEMENTATIONS ====================

async def collect_claude_md(
    db: KuzuStorage,
    max_results: int,
    calculate_similarity: bool
) -> List[TextContent]:
    """Collect CLAUDE.md files from GitHub."""
    try:
        # Search for CLAUDE.md files using gh CLI
        results = run_gh_command([
            'search', 'code', 'filename:CLAUDE.md',
            '--limit', str(max_results),
            '--json', 'repository,path'
        ])

        if not results:
            return [TextContent(type="text", text="No files found or GitHub CLI error")]

        collected = []
        contents = []
        repo_ids = []

        for item in results:
            repo_name = item['repository']['nameWithOwner']

            # Get repo details
            repo_info = run_gh_command([
                'repo', 'view', repo_name,
                '--json', 'name,owner,stargazerCount,description,primaryLanguage,repositoryTopics,url'
            ])

            if not repo_info:
                continue

            # Get file content
            try:
                content_result = subprocess.run(
                    ['gh', 'api', f'/repos/{repo_name}/contents/{item["path"]}',
                     '--jq', '.content'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                content = ""
                if content_result.returncode == 0 and content_result.stdout:
                    try:
                        content = base64.b64decode(content_result.stdout.strip()).decode('utf-8')
                    except:
                        content = ""
            except:
                content = ""

            repo_topics = repo_info.get('repositoryTopics') or []
            topics = [t['name'] for t in repo_topics if t and 'name' in t][:5]
            language = repo_info.get('primaryLanguage') or {}
            language_name = language.get('name', 'Unknown') if language else 'Unknown'

            repo = RepoNode(
                repo_id=repo_name,
                name=repo_info.get('name', ''),
                full_name=repo_name,
                stars=repo_info.get('stargazerCount', 0),
                description=repo_info.get('description', '') or '',
                url=f"https://github.com/{repo_name}/blob/main/{item['path']}",
                repo_url=repo_info.get('url', f"https://github.com/{repo_name}"),
                language=language_name,
                topics=topics,
                keywords=extract_keywords(content),
                content=content,
                summary=generate_summary(content),
                size=len(content),
                collected_at=datetime.now().isoformat()
            )

            if db.add_repository(repo):
                collected.append(repo_name)
                contents.append(content)
                repo_ids.append(repo_name)

        # Calculate similarities if requested
        if calculate_similarity and len(contents) > 1:
            similarity_matrix = calculate_tfidf_similarity(contents)
            for i in range(len(repo_ids)):
                for j in range(i + 1, len(repo_ids)):
                    sim = similarity_matrix[i][j]
                    if sim >= 0.1:
                        db.add_similarity(repo_ids[i], repo_ids[j], sim)

        result = {
            "collected": len(collected),
            "repositories": collected[:10],
            "message": f"Successfully collected {len(collected)} CLAUDE.md files"
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error collecting files: {str(e)}")]


async def search_claude_md(
    db: KuzuStorage,
    query: Optional[str],
    min_stars: int,
    language: Optional[str],
    limit: int
) -> List[TextContent]:
    """Search CLAUDE.md files."""
    try:
        repos = db.search_repositories(query, min_stars, language, limit)
        result = {
            "count": len(repos),
            "repositories": [
                {
                    "name": r.get("full_name", r.get("name", "")),
                    "stars": r.get("stars", 0),
                    "language": r.get("language", "Unknown"),
                    "description": (r.get("description", "") or "")[:100]
                }
                for r in repos
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error searching: {str(e)}")]


async def open_file(db: KuzuStorage, repo_id: str) -> List[TextContent]:
    """Open and view file content."""
    try:
        repo = db.get_repository(repo_id)
        if not repo:
            return [TextContent(type="text", text=f"Repository not found: {repo_id}")]

        content = repo.get("content", "")
        result = {
            "repository": repo.get("full_name", repo_id),
            "stars": repo.get("stars", 0),
            "url": repo.get("url", ""),
            "content": content[:5000] if len(content) > 5000 else content,
            "truncated": len(content) > 5000
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error opening file: {str(e)}")]


async def analyze_file(db: KuzuStorage, repo_id: str) -> List[TextContent]:
    """Analyze file structure and keywords."""
    try:
        repo = db.get_repository(repo_id)
        if not repo:
            return [TextContent(type="text", text=f"Repository not found: {repo_id}")]

        content = repo.get("content", "")

        # Extract sections
        sections = re.findall(r'^(#+)\s+(.+)$', content, re.MULTILINE)
        section_list = [{"level": len(h), "title": t} for h, t in sections]

        # Count code blocks
        code_blocks = len(re.findall(r'```\w*\n', content))

        result = {
            "repository": repo.get("full_name", repo_id),
            "stars": repo.get("stars", 0),
            "language": repo.get("language", "Unknown"),
            "size": repo.get("size", len(content)),
            "sections": section_list[:20],
            "keywords": repo.get("keywords", []),
            "summary": repo.get("summary", ""),
            "code_blocks": code_blocks,
            "topics": repo.get("topics", [])
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error analyzing file: {str(e)}")]


async def get_similar(
    db: KuzuStorage,
    repo_id: str,
    min_similarity: float,
    limit: int
) -> List[TextContent]:
    """Get similar repositories."""
    try:
        similar = db.get_similar_repositories(repo_id, min_similarity, limit)
        result = {
            "repository": repo_id,
            "similar_count": len(similar),
            "similar": [
                {
                    "name": r.get("full_name", ""),
                    "stars": r.get("stars", 0),
                    "similarity": round(sim, 3),
                    "language": r.get("language", "Unknown")
                }
                for r, sim in similar
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting similar: {str(e)}")]


async def download_files(
    db: KuzuStorage,
    repo_ids: List[str],
    output_dir: str
) -> List[TextContent]:
    """Download files to local directory."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        downloaded = []

        for repo_id in repo_ids:
            repo = db.get_repository(repo_id)
            if not repo:
                continue

            content = repo.get("content", "")
            if not content:
                continue

            # Create directory structure
            safe_name = repo_id.replace("/", "_")
            file_path = os.path.join(output_dir, f"{safe_name}_CLAUDE.md")

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {repo.get('full_name', repo_id)}\n\n")
                f.write(f"Stars: {repo.get('stars', 0)} | ")
                f.write(f"Language: {repo.get('language', 'Unknown')}\n\n")
                f.write(f"---\n\n")
                f.write(content)

            downloaded.append(file_path)

        result = {
            "downloaded": len(downloaded),
            "files": downloaded,
            "output_dir": output_dir
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error downloading files: {str(e)}")]


async def merge_files(
    db: KuzuStorage,
    repo_ids: List[str],
    output_path: str
) -> List[TextContent]:
    """Merge multiple files into one."""
    try:
        merged_content = "# Merged CLAUDE.md Files\n\n"
        merged_content += f"Generated: {datetime.now().isoformat()}\n\n"
        merged_content += "---\n\n"

        merged_count = 0
        for repo_id in repo_ids:
            repo = db.get_repository(repo_id)
            if not repo:
                continue

            content = repo.get("content", "")
            if not content:
                continue

            merged_content += f"## {repo.get('full_name', repo_id)}\n\n"
            merged_content += f"**Stars:** {repo.get('stars', 0)} | "
            merged_content += f"**Language:** {repo.get('language', 'Unknown')}\n\n"
            merged_content += content
            merged_content += "\n\n---\n\n"
            merged_count += 1

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(merged_content)

        result = {
            "merged": merged_count,
            "output_path": output_path,
            "size": len(merged_content)
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error merging files: {str(e)}")]


async def get_graph_data(
    db: KuzuStorage,
    min_similarity: float,
    output_path: Optional[str]
) -> List[TextContent]:
    """Get graph data for visualization."""
    try:
        graph = db.get_graph_data(min_similarity)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(graph, f, indent=2, ensure_ascii=False)

        result = {
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
            "output_path": output_path if output_path else None,
            "preview": {
                "nodes": graph.get("nodes", [])[:5],
                "edges": graph.get("edges", [])[:5]
            }
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting graph data: {str(e)}")]


async def get_stats(db: KuzuStorage) -> List[TextContent]:
    """Get database statistics."""
    try:
        stats = db.get_stats()
        return [TextContent(type="text", text=json.dumps(stats, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting stats: {str(e)}")]


async def export_json(db: KuzuStorage, output_path: str) -> List[TextContent]:
    """Export database to JSON."""
    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        success = db.export_to_json(output_path)
        if success:
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "output_path": output_path
            }, indent=2))]
        else:
            return [TextContent(type="text", text="Export failed")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error exporting: {str(e)}")]


# ==================== MAIN ====================

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
