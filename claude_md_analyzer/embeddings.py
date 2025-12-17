"""Embedding generation for CLAUDE.md file summaries."""

import os
from typing import List, Optional, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .models import ClaudeFile


class EmbeddingGenerator:
    """Generate embeddings for file summaries and content."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding generator.

        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for embeddings. "
                    "Install it with: pip install sentence-transformers"
                )
        return self._model

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def generate_embeddings(
        self, files: List[ClaudeFile], use_content: bool = False
    ) -> List[ClaudeFile]:
        """
        Generate embeddings for multiple files.

        Args:
            files: List of ClaudeFile objects
            use_content: If True, use full content; otherwise use summary

        Returns:
            Files with embeddings added
        """
        texts = []
        for f in files:
            if use_content:
                # Use first 5000 chars of content
                text = f.content[:5000]
            else:
                # Use summary + keywords + section titles
                parts = [f.summary or ""]
                if f.structure:
                    parts.extend(f.structure.get("keywords", [])[:10])
                    parts.extend(
                        s["title"] for s in f.structure.get("sections", [])[:5]
                    )
                text = " ".join(filter(None, parts))
            texts.append(text)

        # Generate embeddings in batch
        embeddings = self.model.encode(texts, convert_to_numpy=True)

        # Add to files
        for file, embedding in zip(files, embeddings):
            file.embedding = embedding.tolist()

        return files

    def calculate_similarity_matrix(
        self, files: List[ClaudeFile]
    ) -> np.ndarray:
        """
        Calculate pairwise similarity matrix for files.

        Args:
            files: List of ClaudeFile objects with embeddings

        Returns:
            Numpy array of cosine similarities
        """
        embeddings = [f.embedding for f in files if f.embedding]
        if not embeddings:
            return np.array([])

        embeddings_array = np.array(embeddings)
        return cosine_similarity(embeddings_array)

    def find_similar_files(
        self,
        target_file: ClaudeFile,
        all_files: List[ClaudeFile],
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Tuple[ClaudeFile, float]]:
        """
        Find files most similar to a target file.

        Args:
            target_file: File to find similar files for
            all_files: List of all files to search
            top_k: Number of top similar files to return
            threshold: Minimum similarity threshold

        Returns:
            List of (file, similarity_score) tuples
        """
        if not target_file.embedding:
            target_file = self.generate_embeddings([target_file])[0]

        target_embedding = np.array(target_file.embedding).reshape(1, -1)

        similar_files = []
        for f in all_files:
            if f.sha == target_file.sha:
                continue
            if not f.embedding:
                continue

            file_embedding = np.array(f.embedding).reshape(1, -1)
            similarity = cosine_similarity(target_embedding, file_embedding)[0][0]

            if similarity >= threshold:
                similar_files.append((f, float(similarity)))

        # Sort by similarity
        similar_files.sort(key=lambda x: x[1], reverse=True)
        return similar_files[:top_k]

    def cluster_files(
        self,
        files: List[ClaudeFile],
        n_clusters: Optional[int] = None,
        method: str = "kmeans",
    ) -> List[List[int]]:
        """
        Cluster files based on their embeddings.

        Args:
            files: List of ClaudeFile objects with embeddings
            n_clusters: Number of clusters (auto-determined if None)
            method: Clustering method ('kmeans', 'agglomerative', 'dbscan')

        Returns:
            List of lists containing file indices for each cluster
        """
        embeddings = [f.embedding for f in files if f.embedding]
        if not embeddings or len(embeddings) < 2:
            return [[i] for i in range(len(files))]

        embeddings_array = np.array(embeddings)

        # Auto-determine number of clusters
        if n_clusters is None:
            n_clusters = max(2, min(10, len(files) // 3))

        if method == "kmeans":
            from sklearn.cluster import KMeans
            clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        elif method == "agglomerative":
            from sklearn.cluster import AgglomerativeClustering
            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
        elif method == "dbscan":
            from sklearn.cluster import DBSCAN
            clusterer = DBSCAN(eps=0.5, min_samples=2)
        else:
            raise ValueError(f"Unknown clustering method: {method}")

        labels = clusterer.fit_predict(embeddings_array)

        # Group indices by cluster
        clusters = {}
        for i, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(i)

        return list(clusters.values())

    def reduce_dimensions(
        self,
        files: List[ClaudeFile],
        n_components: int = 2,
        method: str = "umap",
    ) -> np.ndarray:
        """
        Reduce embedding dimensions for visualization.

        Args:
            files: List of ClaudeFile objects with embeddings
            n_components: Target number of dimensions
            method: Reduction method ('umap', 'tsne', 'pca')

        Returns:
            Numpy array of reduced coordinates
        """
        embeddings = [f.embedding for f in files if f.embedding]
        if not embeddings:
            return np.array([])

        embeddings_array = np.array(embeddings)

        if method == "umap":
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=n_components,
                    random_state=42,
                    n_neighbors=min(15, len(embeddings) - 1),
                    min_dist=0.1,
                )
            except ImportError:
                # Fallback to PCA
                method = "pca"

        if method == "tsne":
            from sklearn.manifold import TSNE
            reducer = TSNE(
                n_components=n_components,
                random_state=42,
                perplexity=min(30, len(embeddings) - 1),
            )
        elif method == "pca":
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=n_components, random_state=42)

        if method in ["umap"]:
            reduced = reducer.fit_transform(embeddings_array)
        else:
            reduced = reducer.fit_transform(embeddings_array)

        return reduced

    def get_embedding_stats(self, files: List[ClaudeFile]) -> dict:
        """Get statistics about embeddings."""
        embeddings = [f.embedding for f in files if f.embedding]
        if not embeddings:
            return {"error": "No embeddings found"}

        embeddings_array = np.array(embeddings)
        similarity_matrix = cosine_similarity(embeddings_array)

        # Get upper triangle (excluding diagonal)
        upper_tri = similarity_matrix[np.triu_indices(len(similarity_matrix), k=1)]

        return {
            "total_files": len(embeddings),
            "embedding_dim": len(embeddings[0]),
            "mean_similarity": float(np.mean(upper_tri)),
            "std_similarity": float(np.std(upper_tri)),
            "min_similarity": float(np.min(upper_tri)),
            "max_similarity": float(np.max(upper_tri)),
            "highly_similar_pairs": int(np.sum(upper_tri > 0.8)),
        }
