"""
KùzuDB-based storage for CLAUDE.md files.
Provides graph database storage with nodes (repositories) and edges (similarity relationships).
"""

import os
import json
import shutil
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

import kuzu


@dataclass
class RepoNode:
    """Repository node data."""
    repo_id: str
    name: str
    full_name: str
    stars: int
    description: str
    url: str
    repo_url: str
    language: str
    topics: List[str]
    keywords: List[str]
    content: str
    summary: str
    size: int
    collected_at: str


@dataclass
class SimilarityEdge:
    """Similarity relationship between repositories."""
    source_id: str
    target_id: str
    similarity: float


class KuzuStorage:
    """KùzuDB storage manager for CLAUDE.md data."""

    def __init__(self, db_path: str = "./data/kuzu_db"):
        """
        Initialize KùzuDB storage.

        Args:
            db_path: Path to the database directory
        """
        self.db_path = db_path
        self._db = None
        self._conn = None
        self._ensure_db()

    def _ensure_db(self):
        """Ensure database exists and has proper schema."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._db = kuzu.Database(self.db_path)
        self._conn = kuzu.Connection(self._db)

        # Create schema if not exists
        self._create_schema()

    def _create_schema(self):
        """Create database schema for repositories and relationships."""
        # Create Repository node table
        try:
            self._conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS Repository (
                    repo_id STRING PRIMARY KEY,
                    name STRING,
                    full_name STRING,
                    stars INT64,
                    description STRING,
                    url STRING,
                    repo_url STRING,
                    language STRING,
                    topics STRING[],
                    keywords STRING[],
                    content STRING,
                    summary STRING,
                    size INT64,
                    collected_at STRING
                )
            """)
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

        # Create Similarity relationship table
        try:
            self._conn.execute("""
                CREATE REL TABLE IF NOT EXISTS SIMILAR_TO (
                    FROM Repository TO Repository,
                    similarity DOUBLE
                )
            """)
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise

    def add_repository(self, repo: RepoNode) -> bool:
        """
        Add a repository to the database.

        Args:
            repo: Repository node data

        Returns:
            True if successful
        """
        try:
            # Check if exists
            result = self._conn.execute(
                "MATCH (r:Repository {repo_id: $id}) RETURN r.repo_id",
                {"id": repo.repo_id}
            )

            if result.has_next():
                # Update existing
                self._conn.execute("""
                    MATCH (r:Repository {repo_id: $repo_id})
                    SET r.name = $name,
                        r.full_name = $full_name,
                        r.stars = $stars,
                        r.description = $description,
                        r.url = $url,
                        r.repo_url = $repo_url,
                        r.language = $language,
                        r.topics = $topics,
                        r.keywords = $keywords,
                        r.content = $content,
                        r.summary = $summary,
                        r.size = $size,
                        r.collected_at = $collected_at
                """, {
                    "repo_id": repo.repo_id,
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "stars": repo.stars,
                    "description": repo.description,
                    "url": repo.url,
                    "repo_url": repo.repo_url,
                    "language": repo.language,
                    "topics": repo.topics,
                    "keywords": repo.keywords,
                    "content": repo.content,
                    "summary": repo.summary,
                    "size": repo.size,
                    "collected_at": repo.collected_at
                })
            else:
                # Insert new
                self._conn.execute("""
                    CREATE (r:Repository {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name,
                        stars: $stars,
                        description: $description,
                        url: $url,
                        repo_url: $repo_url,
                        language: $language,
                        topics: $topics,
                        keywords: $keywords,
                        content: $content,
                        summary: $summary,
                        size: $size,
                        collected_at: $collected_at
                    })
                """, {
                    "repo_id": repo.repo_id,
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "stars": repo.stars,
                    "description": repo.description,
                    "url": repo.url,
                    "repo_url": repo.repo_url,
                    "language": repo.language,
                    "topics": repo.topics,
                    "keywords": repo.keywords,
                    "content": repo.content,
                    "summary": repo.summary,
                    "size": repo.size,
                    "collected_at": repo.collected_at
                })
            return True
        except Exception as e:
            print(f"Error adding repository: {e}")
            return False

    def add_similarity(self, source_id: str, target_id: str, similarity: float) -> bool:
        """
        Add a similarity relationship between repositories.

        Args:
            source_id: Source repository ID
            target_id: Target repository ID
            similarity: Similarity score (0-1)

        Returns:
            True if successful
        """
        try:
            # Check if relationship already exists
            result = self._conn.execute("""
                MATCH (a:Repository {repo_id: $source})-[r:SIMILAR_TO]->(b:Repository {repo_id: $target})
                RETURN r.similarity
            """, {"source": source_id, "target": target_id})

            if result.has_next():
                # Update existing (by creating new - KùzuDB will handle)
                return True

            # Create new relationship
            self._conn.execute("""
                MATCH (a:Repository {repo_id: $source}), (b:Repository {repo_id: $target})
                CREATE (a)-[:SIMILAR_TO {similarity: $similarity}]->(b)
            """, {"source": source_id, "target": target_id, "similarity": similarity})
            return True
        except Exception as e:
            print(f"Error adding similarity: {e}")
            return False

    def get_repository(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Get a repository by ID."""
        try:
            result = self._conn.execute("""
                MATCH (r:Repository {repo_id: $id})
                RETURN r.*
            """, {"id": repo_id})

            if result.has_next():
                row = result.get_next()
                return self._row_to_dict(row, result.get_column_names())
            return None
        except Exception as e:
            print(f"Error getting repository: {e}")
            return None

    def search_repositories(
        self,
        query: Optional[str] = None,
        min_stars: int = 0,
        language: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search repositories with filters.

        Args:
            query: Search query (searches name, description, content)
            min_stars: Minimum stars filter
            language: Language filter
            limit: Maximum results

        Returns:
            List of matching repositories
        """
        try:
            conditions = ["r.stars >= $min_stars"]
            params = {"min_stars": min_stars, "limit": limit}

            if language:
                conditions.append("r.language = $language")
                params["language"] = language

            if query:
                conditions.append(
                    "(r.name CONTAINS $query OR r.description CONTAINS $query OR r.full_name CONTAINS $query)"
                )
                params["query"] = query.lower()

            where_clause = " AND ".join(conditions)

            result = self._conn.execute(f"""
                MATCH (r:Repository)
                WHERE {where_clause}
                RETURN r.*
                ORDER BY r.stars DESC
                LIMIT $limit
            """, params)

            repos = []
            while result.has_next():
                row = result.get_next()
                repos.append(self._row_to_dict(row, result.get_column_names()))
            return repos
        except Exception as e:
            print(f"Error searching repositories: {e}")
            return []

    def get_similar_repositories(
        self,
        repo_id: str,
        min_similarity: float = 0.1,
        limit: int = 10
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Get similar repositories.

        Args:
            repo_id: Repository ID
            min_similarity: Minimum similarity threshold
            limit: Maximum results

        Returns:
            List of (repository, similarity) tuples
        """
        try:
            result = self._conn.execute("""
                MATCH (a:Repository {repo_id: $id})-[r:SIMILAR_TO]-(b:Repository)
                WHERE r.similarity >= $min_sim
                RETURN b.*, r.similarity AS similarity
                ORDER BY r.similarity DESC
                LIMIT $limit
            """, {"id": repo_id, "min_sim": min_similarity, "limit": limit})

            repos = []
            while result.has_next():
                row = result.get_next()
                cols = result.get_column_names()
                sim_idx = cols.index("similarity")
                similarity = row[sim_idx]
                repo_dict = self._row_to_dict(row[:-1], cols[:-1])
                repos.append((repo_dict, similarity))
            return repos
        except Exception as e:
            print(f"Error getting similar repositories: {e}")
            return []

    def get_all_repositories(self) -> List[Dict[str, Any]]:
        """Get all repositories."""
        return self.search_repositories(limit=1000)

    def get_graph_data(self, min_similarity: float = 0.1) -> Dict[str, Any]:
        """
        Get graph data for visualization.

        Args:
            min_similarity: Minimum similarity for edges

        Returns:
            Graph data with nodes and edges
        """
        try:
            # Get all nodes
            nodes_result = self._conn.execute("""
                MATCH (r:Repository)
                RETURN r.*
                ORDER BY r.stars DESC
            """)

            nodes = []
            node_ids = {}
            idx = 0
            while nodes_result.has_next():
                row = nodes_result.get_next()
                repo = self._row_to_dict(row, nodes_result.get_column_names())
                node_ids[repo.get("repo_id", repo.get("r.repo_id"))] = f"node_{idx}"
                nodes.append({
                    "id": f"node_{idx}",
                    "label": repo.get("name", repo.get("r.name", "")),
                    "full_name": repo.get("full_name", repo.get("r.full_name", "")),
                    "stars": repo.get("stars", repo.get("r.stars", 0)),
                    "description": repo.get("description", repo.get("r.description", "")),
                    "url": repo.get("url", repo.get("r.url", "")),
                    "repo_url": repo.get("repo_url", repo.get("r.repo_url", "")),
                    "language": repo.get("language", repo.get("r.language", "Unknown")),
                    "topics": repo.get("topics", repo.get("r.topics", [])),
                    "keywords": repo.get("keywords", repo.get("r.keywords", [])),
                    "size": repo.get("size", repo.get("r.size", 0)),
                    "summary": repo.get("summary", repo.get("r.summary", "")),
                })
                idx += 1

            # Get all edges
            edges_result = self._conn.execute("""
                MATCH (a:Repository)-[r:SIMILAR_TO]->(b:Repository)
                WHERE r.similarity >= $min_sim
                RETURN a.repo_id, b.repo_id, r.similarity
            """, {"min_sim": min_similarity})

            edges = []
            while edges_result.has_next():
                row = edges_result.get_next()
                source_id, target_id, similarity = row
                if source_id in node_ids and target_id in node_ids:
                    edges.append({
                        "source": node_ids[source_id],
                        "target": node_ids[target_id],
                        "similarity": round(similarity, 3)
                    })

            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            print(f"Error getting graph data: {e}")
            return {"nodes": [], "edges": []}

    def export_to_json(self, output_path: str) -> bool:
        """Export database to JSON file."""
        try:
            graph_data = self.get_graph_data()
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting to JSON: {e}")
            return False

    def import_from_json(self, input_path: str) -> bool:
        """Import data from JSON file."""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Import nodes
            for node in data.get("nodes", []):
                repo = RepoNode(
                    repo_id=node.get("full_name", node.get("id", "")),
                    name=node.get("label", ""),
                    full_name=node.get("full_name", ""),
                    stars=node.get("stars", 0),
                    description=node.get("description", ""),
                    url=node.get("url", ""),
                    repo_url=node.get("repo_url", ""),
                    language=node.get("language", "Unknown"),
                    topics=node.get("topics", []),
                    keywords=node.get("keywords", []),
                    content="",
                    summary=node.get("summary", ""),
                    size=node.get("size", 0),
                    collected_at=datetime.now().isoformat()
                )
                self.add_repository(repo)

            return True
        except Exception as e:
            print(f"Error importing from JSON: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            repo_count = self._conn.execute(
                "MATCH (r:Repository) RETURN count(r) AS count"
            )
            total_repos = repo_count.get_next()[0] if repo_count.has_next() else 0

            edge_count = self._conn.execute(
                "MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) AS count"
            )
            total_edges = edge_count.get_next()[0] if edge_count.has_next() else 0

            stars_result = self._conn.execute(
                "MATCH (r:Repository) RETURN sum(r.stars) AS total, avg(r.stars) AS avg"
            )
            stars_row = stars_result.get_next() if stars_result.has_next() else [0, 0]

            return {
                "total_repositories": total_repos,
                "total_relationships": total_edges,
                "total_stars": stars_row[0] or 0,
                "avg_stars": round(stars_row[1] or 0, 2),
                "db_path": self.db_path
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}

    def clear_database(self):
        """Clear all data from the database."""
        try:
            self._conn.execute("MATCH (r:Repository) DETACH DELETE r")
        except Exception as e:
            print(f"Error clearing database: {e}")

    def _row_to_dict(self, row, columns) -> Dict[str, Any]:
        """Convert query result row to dictionary."""
        result = {}
        for i, col in enumerate(columns):
            key = col.replace("r.", "")
            result[key] = row[i]
        return result

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn = None
        if self._db:
            self._db = None
