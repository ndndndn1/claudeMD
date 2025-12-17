"""File merger for combining CLAUDE.md files."""

import os
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from .models import ClaudeFile


class FileMerger:
    """Merge multiple CLAUDE.md files into one."""

    def __init__(self, output_dir: str = "./merged"):
        """
        Initialize merger.

        Args:
            output_dir: Directory to save merged files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def merge(
        self,
        files: List[ClaudeFile],
        output_name: str = "MERGED_CLAUDE.md",
        include_toc: bool = True,
        include_metadata: bool = True,
        separator: str = "---",
    ) -> str:
        """
        Merge multiple CLAUDE.md files into one.

        Args:
            files: List of ClaudeFile objects to merge
            output_name: Name of output file
            include_toc: Include table of contents
            include_metadata: Include file metadata headers
            separator: Separator between files

        Returns:
            Path to merged file
        """
        output_path = self.output_dir / output_name

        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("# Merged CLAUDE.md Files\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Total files: {len(files)}\n")
            f.write(f"Total stars: {sum(file.repository.stars for file in files):,}\n\n")

            # Table of contents
            if include_toc:
                f.write("## Table of Contents\n\n")
                for i, file in enumerate(files, 1):
                    anchor = self._make_anchor(file.repository.full_name)
                    f.write(f"{i}. [{file.repository.full_name}](#{anchor}) (⭐ {file.repository.stars})\n")
                f.write("\n")

            f.write(f"{separator}\n\n")

            # Content
            for i, file in enumerate(files):
                anchor = self._make_anchor(file.repository.full_name)

                if include_metadata:
                    f.write(f"<a name=\"{anchor}\"></a>\n\n")
                    f.write(f"## {file.repository.full_name}\n\n")
                    f.write(f"- **Stars:** {file.repository.stars}\n")
                    f.write(f"- **Description:** {file.repository.description or 'N/A'}\n")
                    f.write(f"- **URL:** {file.html_url}\n")
                    if file.summary:
                        f.write(f"- **Summary:** {file.summary}\n")
                    f.write("\n")
                    f.write("### Content\n\n")

                f.write(file.content)
                f.write("\n\n")

                if i < len(files) - 1:
                    f.write(f"{separator}\n\n")

        return str(output_path)

    def merge_by_topic(
        self,
        files: List[ClaudeFile],
        base_name: str = "CLAUDE_TOPIC",
    ) -> Dict[str, str]:
        """
        Merge files grouped by detected topics.

        Args:
            files: List of ClaudeFile objects
            base_name: Base name for output files

        Returns:
            Dictionary mapping topic names to merged file paths
        """
        # Group by top keyword
        topic_groups: Dict[str, List[ClaudeFile]] = {}

        for file in files:
            if file.structure and file.structure.get("keywords"):
                topic = file.structure["keywords"][0]
            else:
                topic = "general"

            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append(file)

        # Merge each group
        result = {}
        for topic, group_files in topic_groups.items():
            if len(group_files) > 0:
                output_name = f"{base_name}_{topic}.md"
                path = self.merge(group_files, output_name)
                result[topic] = path

        return result

    def merge_by_similarity(
        self,
        files: List[ClaudeFile],
        clusters: List[List[int]],
        base_name: str = "CLAUDE_CLUSTER",
    ) -> Dict[str, str]:
        """
        Merge files grouped by similarity clusters.

        Args:
            files: List of ClaudeFile objects
            clusters: List of cluster assignments (list of file indices)
            base_name: Base name for output files

        Returns:
            Dictionary mapping cluster IDs to merged file paths
        """
        result = {}

        for cluster_id, cluster_indices in enumerate(clusters):
            cluster_files = [files[i] for i in cluster_indices if i < len(files)]
            if cluster_files:
                output_name = f"{base_name}_{cluster_id}.md"
                path = self.merge(cluster_files, output_name)
                result[f"cluster_{cluster_id}"] = path

        return result

    def create_summary_doc(
        self,
        files: List[ClaudeFile],
        output_name: str = "CLAUDE_SUMMARY.md",
    ) -> str:
        """
        Create a summary document with brief overview of all files.

        Args:
            files: List of ClaudeFile objects
            output_name: Name of output file

        Returns:
            Path to summary file
        """
        output_path = self.output_dir / output_name

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# CLAUDE.md Files Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")

            # Statistics
            f.write("## Statistics\n\n")
            f.write(f"- Total files: {len(files)}\n")
            f.write(f"- Total stars: {sum(file.repository.stars for file in files):,}\n")
            f.write(f"- Average stars: {sum(file.repository.stars for file in files) // max(len(files), 1):,}\n")
            f.write(f"- Total content size: {sum(file.size for file in files):,} bytes\n\n")

            # Top repositories
            f.write("## Top Repositories by Stars\n\n")
            sorted_files = sorted(files, key=lambda x: x.repository.stars, reverse=True)
            for file in sorted_files[:10]:
                f.write(f"### [{file.repository.full_name}]({file.html_url})\n\n")
                f.write(f"⭐ **{file.repository.stars:,}** stars\n\n")
                if file.repository.description:
                    f.write(f"> {file.repository.description}\n\n")
                if file.summary:
                    f.write(f"**Summary:** {file.summary}\n\n")
                f.write("---\n\n")

            # All files table
            f.write("## All Files\n\n")
            f.write("| Repository | Stars | Description |\n")
            f.write("|------------|-------|-------------|\n")
            for file in sorted_files:
                desc = (file.repository.description or "N/A")[:50]
                f.write(f"| [{file.repository.name}]({file.html_url}) | {file.repository.stars:,} | {desc} |\n")

        return str(output_path)

    def extract_sections(
        self,
        files: List[ClaudeFile],
        section_name: str,
        output_name: Optional[str] = None,
    ) -> str:
        """
        Extract specific sections from all files and merge them.

        Args:
            files: List of ClaudeFile objects
            section_name: Name of section to extract (case-insensitive)
            output_name: Name of output file

        Returns:
            Path to merged sections file
        """
        if output_name is None:
            output_name = f"SECTIONS_{section_name.upper()}.md"

        output_path = self.output_dir / output_name

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# Extracted '{section_name}' Sections\n\n")
            f.write(f"From {len(files)} CLAUDE.md files\n\n")
            f.write("---\n\n")

            found_count = 0
            for file in files:
                if not file.structure or not file.structure.get("sections"):
                    continue

                # Find matching section
                for section in file.structure["sections"]:
                    if section_name.lower() in section["title"].lower():
                        found_count += 1
                        f.write(f"## From {file.repository.full_name}\n\n")
                        f.write(f"[{file.html_url}]({file.html_url})\n\n")
                        f.write(section.get("content_preview", "No content available"))
                        f.write("\n\n---\n\n")
                        break

            if found_count == 0:
                f.write(f"No sections matching '{section_name}' found.\n")
            else:
                f.write(f"\n**Total sections found: {found_count}**\n")

        return str(output_path)

    def _make_anchor(self, text: str) -> str:
        """Create a URL-safe anchor from text."""
        return text.lower().replace("/", "-").replace(" ", "-").replace(".", "-")
