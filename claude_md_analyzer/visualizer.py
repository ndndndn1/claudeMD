"""Visualization for CLAUDE.md file relationships."""

import os
from typing import List, Optional, Dict, Any
import numpy as np

from .models import ClaudeFile, AnalysisResult
from .embeddings import EmbeddingGenerator


class RelationshipVisualizer:
    """Visualize relationships between CLAUDE.md files."""

    def __init__(self, output_dir: str = "./output"):
        """
        Initialize visualizer.

        Args:
            output_dir: Directory to save visualization files
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def create_scatter_plot(
        self,
        files: List[ClaudeFile],
        coordinates: np.ndarray,
        clusters: Optional[List[List[int]]] = None,
        filename: str = "relationship_scatter.html",
    ) -> str:
        """
        Create an interactive scatter plot of file relationships.

        Args:
            files: List of ClaudeFile objects
            coordinates: 2D coordinates from dimension reduction
            clusters: Optional cluster assignments
            filename: Output filename

        Returns:
            Path to the generated HTML file
        """
        import plotly.graph_objects as go
        import plotly.express as px

        # Prepare data
        x = coordinates[:, 0]
        y = coordinates[:, 1]

        # Create labels and hover text
        labels = [f.repository.full_name for f in files]
        hover_text = [
            f"<b>{f.repository.full_name}</b><br>"
            f"Stars: {f.repository.stars}<br>"
            f"Path: {f.path}<br>"
            f"Size: {f.size} bytes<br>"
            f"Summary: {(f.summary or 'N/A')[:100]}..."
            for f in files
        ]

        # Determine colors based on clusters or stars
        if clusters:
            # Assign cluster colors
            cluster_ids = [0] * len(files)
            for cluster_idx, file_indices in enumerate(clusters):
                for file_idx in file_indices:
                    cluster_ids[file_idx] = cluster_idx
            colors = cluster_ids
            color_label = "Cluster"
        else:
            # Color by stars
            colors = [f.repository.stars for f in files]
            color_label = "Stars"

        # Size by file size (normalized)
        sizes = np.array([f.size for f in files])
        sizes_normalized = 10 + 40 * (sizes - sizes.min()) / (sizes.max() - sizes.min() + 1)

        # Create figure
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='markers+text',
            marker=dict(
                size=sizes_normalized,
                color=colors,
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title=color_label),
                line=dict(width=1, color='white'),
            ),
            text=[f.repository.name for f in files],
            textposition="top center",
            textfont=dict(size=8),
            hovertext=hover_text,
            hoverinfo='text',
            customdata=[[f.html_url, f.repository.stars] for f in files],
        ))

        fig.update_layout(
            title=dict(
                text="CLAUDE.md Files Relationship Map",
                font=dict(size=24),
            ),
            xaxis=dict(
                title="Dimension 1",
                showgrid=True,
                gridcolor='lightgray',
            ),
            yaxis=dict(
                title="Dimension 2",
                showgrid=True,
                gridcolor='lightgray',
            ),
            hovermode='closest',
            plot_bgcolor='white',
            width=1200,
            height=800,
        )

        # Add click event to open GitHub URL
        fig.update_traces(
            marker=dict(
                symbol='circle',
            ),
        )

        output_path = os.path.join(self.output_dir, filename)
        fig.write_html(output_path)
        return output_path

    def create_similarity_heatmap(
        self,
        files: List[ClaudeFile],
        similarity_matrix: np.ndarray,
        filename: str = "similarity_heatmap.html",
    ) -> str:
        """
        Create a heatmap of file similarities.

        Args:
            files: List of ClaudeFile objects
            similarity_matrix: Pairwise similarity matrix
            filename: Output filename

        Returns:
            Path to the generated HTML file
        """
        import plotly.graph_objects as go

        labels = [f"{f.repository.name}" for f in files]

        fig = go.Figure(data=go.Heatmap(
            z=similarity_matrix,
            x=labels,
            y=labels,
            colorscale='RdYlBu_r',
            zmin=0,
            zmax=1,
            hoverongaps=False,
            hovertemplate=(
                '%{x}<br>%{y}<br>'
                'Similarity: %{z:.3f}<extra></extra>'
            ),
        ))

        fig.update_layout(
            title=dict(
                text="CLAUDE.md Files Similarity Matrix",
                font=dict(size=24),
            ),
            xaxis=dict(
                title="Repository",
                tickangle=45,
            ),
            yaxis=dict(
                title="Repository",
            ),
            width=1000,
            height=1000,
        )

        output_path = os.path.join(self.output_dir, filename)
        fig.write_html(output_path)
        return output_path

    def create_network_graph(
        self,
        files: List[ClaudeFile],
        similarity_matrix: np.ndarray,
        threshold: float = 0.5,
        filename: str = "relationship_network.html",
    ) -> str:
        """
        Create a network graph of file relationships.

        Args:
            files: List of ClaudeFile objects
            similarity_matrix: Pairwise similarity matrix
            threshold: Minimum similarity to draw an edge
            filename: Output filename

        Returns:
            Path to the generated HTML file
        """
        import plotly.graph_objects as go
        import networkx as nx

        # Create graph
        G = nx.Graph()

        # Add nodes
        for i, f in enumerate(files):
            G.add_node(i, name=f.repository.full_name, stars=f.repository.stars)

        # Add edges
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                if similarity_matrix[i, j] >= threshold:
                    G.add_edge(i, j, weight=similarity_matrix[i, j])

        # Layout
        pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

        # Edge traces
        edge_x = []
        edge_y = []
        edge_weights = []

        for edge in G.edges(data=True):
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_weights.append(edge[2]['weight'])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines'
        )

        # Node traces
        node_x = [pos[node][0] for node in G.nodes()]
        node_y = [pos[node][1] for node in G.nodes()]
        node_colors = [files[node].repository.stars for node in G.nodes()]
        node_sizes = [10 + G.degree(node) * 5 for node in G.nodes()]
        node_text = [
            f"<b>{files[node].repository.full_name}</b><br>"
            f"Stars: {files[node].repository.stars}<br>"
            f"Connections: {G.degree(node)}"
            for node in G.nodes()
        ]

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            hoverinfo='text',
            text=[files[node].repository.name for node in G.nodes()],
            textposition="top center",
            textfont=dict(size=8),
            hovertext=node_text,
            marker=dict(
                showscale=True,
                colorscale='YlOrRd',
                color=node_colors,
                size=node_sizes,
                colorbar=dict(
                    thickness=15,
                    title='Stars',
                    xanchor='left',
                ),
                line=dict(width=2, color='white'),
            )
        )

        # Create figure
        fig = go.Figure(data=[edge_trace, node_trace],
                       layout=go.Layout(
                           title=dict(
                               text=f'CLAUDE.md Relationship Network (threshold={threshold})',
                               font=dict(size=24),
                           ),
                           showlegend=False,
                           hovermode='closest',
                           xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                           yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                           plot_bgcolor='white',
                           width=1200,
                           height=800,
                       ))

        output_path = os.path.join(self.output_dir, filename)
        fig.write_html(output_path)
        return output_path

    def create_summary_table(
        self,
        files: List[ClaudeFile],
        filename: str = "summary_table.html",
    ) -> str:
        """
        Create an HTML table summarizing all files.

        Args:
            files: List of ClaudeFile objects
            filename: Output filename

        Returns:
            Path to the generated HTML file
        """
        import pandas as pd

        # Prepare data
        data = []
        for f in sorted(files, key=lambda x: x.repository.stars, reverse=True):
            data.append({
                "Repository": f'<a href="{f.repository.url}" target="_blank">{f.repository.full_name}</a>',
                "Stars": f.repository.stars,
                "Description": (f.repository.description or "N/A")[:100],
                "File": f'<a href="{f.html_url}" target="_blank">{f.path}</a>',
                "Size": f"{f.size:,} bytes",
                "Summary": (f.summary or "N/A")[:150] + "...",
            })

        df = pd.DataFrame(data)

        # Create HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>CLAUDE.md Files Summary</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 20px;
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                h1 {{
                    color: #333;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                th, td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #4CAF50;
                    color: white;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                a {{
                    color: #0366d6;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                .stats {{
                    margin-bottom: 20px;
                    padding: 15px;
                    background-color: #f8f9fa;
                    border-radius: 8px;
                }}
            </style>
        </head>
        <body>
            <h1>CLAUDE.md Files Summary</h1>
            <div class="stats">
                <strong>Total Files:</strong> {len(files)} |
                <strong>Total Stars:</strong> {sum(f.repository.stars for f in files):,} |
                <strong>Avg Stars:</strong> {sum(f.repository.stars for f in files) // max(len(files), 1):,}
            </div>
            {df.to_html(index=False, escape=False, classes='data-table')}
        </body>
        </html>
        """

        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return output_path

    def visualize_all(
        self,
        result: AnalysisResult,
        similarity_threshold: float = 0.5,
    ) -> Dict[str, str]:
        """
        Generate all visualizations.

        Args:
            result: AnalysisResult with files and relationships
            similarity_threshold: Threshold for network graph edges

        Returns:
            Dictionary of visualization type to file path
        """
        files = result.files
        embedding_gen = EmbeddingGenerator()

        # Ensure embeddings exist
        files_with_embeddings = [f for f in files if f.embedding]
        if not files_with_embeddings:
            files = embedding_gen.generate_embeddings(files)

        # Calculate similarity matrix
        similarity_matrix = embedding_gen.calculate_similarity_matrix(files)

        # Reduce dimensions for scatter plot
        coordinates = embedding_gen.reduce_dimensions(files, n_components=2)

        # Generate visualizations
        paths = {}

        if len(coordinates) > 0:
            paths["scatter"] = self.create_scatter_plot(
                files, coordinates, result.clusters
            )

        if len(similarity_matrix) > 0:
            paths["heatmap"] = self.create_similarity_heatmap(
                files, similarity_matrix
            )
            paths["network"] = self.create_network_graph(
                files, similarity_matrix, threshold=similarity_threshold
            )

        paths["table"] = self.create_summary_table(files)

        return paths
