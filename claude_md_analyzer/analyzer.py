"""Content analyzer for CLAUDE.md files."""

import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .models import ClaudeFile


@dataclass
class Section:
    """A section in the markdown file."""
    title: str
    level: int
    content: str
    start_line: int
    end_line: int


class ContentAnalyzer:
    """Analyze CLAUDE.md file contents."""

    # Common section patterns in CLAUDE.md files
    COMMON_SECTIONS = [
        "overview", "introduction", "getting started",
        "usage", "api", "configuration", "installation",
        "examples", "commands", "features", "requirements",
        "dependencies", "testing", "development", "contributing",
        "license", "credits", "acknowledgments", "todo",
        "changelog", "roadmap", "architecture", "design",
    ]

    def __init__(self):
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.code_block_pattern = re.compile(r'```[\s\S]*?```', re.MULTILINE)
        self.link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        self.list_pattern = re.compile(r'^[\s]*[-*+]\s+', re.MULTILINE)

    def analyze(self, file: ClaudeFile) -> ClaudeFile:
        """
        Analyze a CLAUDE.md file and add structure and summary.

        Args:
            file: ClaudeFile to analyze

        Returns:
            Updated ClaudeFile with structure and summary
        """
        content = file.content

        # Extract structure
        structure = self._extract_structure(content)
        file.structure = structure

        # Generate summary
        summary = self._generate_summary(content, structure, file.repository)
        file.summary = summary

        return file

    def analyze_batch(self, files: List[ClaudeFile]) -> List[ClaudeFile]:
        """
        Analyze multiple files.

        Args:
            files: List of ClaudeFile objects

        Returns:
            List of analyzed ClaudeFile objects
        """
        return [self.analyze(f) for f in files]

    def _extract_structure(self, content: str) -> Dict[str, Any]:
        """Extract the structure of a markdown file."""
        sections = self._parse_sections(content)

        return {
            "sections": [
                {
                    "title": s.title,
                    "level": s.level,
                    "content_preview": s.content[:200] + "..." if len(s.content) > 200 else s.content,
                    "line_count": s.end_line - s.start_line,
                }
                for s in sections
            ],
            "stats": self._calculate_stats(content),
            "keywords": self._extract_keywords(content),
            "links": self._extract_links(content),
            "code_blocks": self._count_code_blocks(content),
        }

    def _parse_sections(self, content: str) -> List[Section]:
        """Parse markdown sections."""
        lines = content.split('\n')
        sections = []
        current_section = None
        current_content = []
        current_start = 0

        for i, line in enumerate(lines):
            heading_match = self.heading_pattern.match(line)
            if heading_match:
                # Save previous section
                if current_section:
                    current_section.content = '\n'.join(current_content)
                    current_section.end_line = i
                    sections.append(current_section)

                # Start new section
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                current_section = Section(
                    title=title,
                    level=level,
                    content="",
                    start_line=i,
                    end_line=i,
                )
                current_content = []
                current_start = i
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            current_section.content = '\n'.join(current_content)
            current_section.end_line = len(lines)
            sections.append(current_section)

        return sections

    def _calculate_stats(self, content: str) -> Dict[str, int]:
        """Calculate basic statistics about the content."""
        lines = content.split('\n')
        words = content.split()

        # Count different elements
        headings = len(self.heading_pattern.findall(content))
        code_blocks = len(self.code_block_pattern.findall(content))
        links = len(self.link_pattern.findall(content))
        list_items = len(self.list_pattern.findall(content))

        return {
            "total_lines": len(lines),
            "total_words": len(words),
            "total_chars": len(content),
            "headings_count": headings,
            "code_blocks_count": code_blocks,
            "links_count": links,
            "list_items_count": list_items,
        }

    def _extract_keywords(self, content: str) -> List[str]:
        """Extract important keywords from content."""
        # Remove code blocks
        text = self.code_block_pattern.sub('', content)

        # Remove links
        text = self.link_pattern.sub(r'\1', text)

        # Extract words
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', text.lower())

        # Count frequency
        word_freq = {}
        for word in words:
            if word not in self._get_stop_words():
                word_freq[word] = word_freq.get(word, 0) + 1

        # Get top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:20]]

    def _extract_links(self, content: str) -> List[Dict[str, str]]:
        """Extract all links from content."""
        matches = self.link_pattern.findall(content)
        return [{"text": text, "url": url} for text, url in matches[:20]]

    def _count_code_blocks(self, content: str) -> List[Dict[str, Any]]:
        """Extract code block information."""
        code_blocks = []
        pattern = re.compile(r'```(\w*)\n([\s\S]*?)```', re.MULTILINE)

        for match in pattern.finditer(content):
            language = match.group(1) or "plain"
            code = match.group(2)
            code_blocks.append({
                "language": language,
                "lines": len(code.split('\n')),
                "preview": code[:100] + "..." if len(code) > 100 else code,
            })

        return code_blocks[:10]  # Limit to 10 code blocks

    def _generate_summary(
        self, content: str, structure: Dict[str, Any], repository
    ) -> str:
        """Generate a human-readable summary of the file."""
        stats = structure.get("stats", {})
        sections = structure.get("sections", [])
        keywords = structure.get("keywords", [])

        # Build summary
        parts = []

        # Repository info
        if repository.description:
            parts.append(f"Repository: {repository.description}")

        # Section overview
        section_titles = [s["title"] for s in sections[:5]]
        if section_titles:
            parts.append(f"Main sections: {', '.join(section_titles)}")

        # Content stats
        parts.append(
            f"Content: {stats.get('total_lines', 0)} lines, "
            f"{stats.get('total_words', 0)} words, "
            f"{stats.get('code_blocks_count', 0)} code blocks"
        )

        # Key topics
        if keywords:
            parts.append(f"Key topics: {', '.join(keywords[:10])}")

        # First paragraph as description
        first_para = self._get_first_paragraph(content)
        if first_para:
            parts.append(f"Description: {first_para[:200]}...")

        return " | ".join(parts)

    def _get_first_paragraph(self, content: str) -> str:
        """Get the first meaningful paragraph of text."""
        # Remove frontmatter
        content = re.sub(r'^---[\s\S]*?---', '', content)

        # Remove headings
        lines = content.split('\n')
        paragraph_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if paragraph_lines:
                    break
                continue
            if stripped.startswith('#'):
                continue
            if stripped.startswith('```'):
                continue
            paragraph_lines.append(stripped)

        return ' '.join(paragraph_lines)

    def _get_stop_words(self) -> set:
        """Get common stop words to filter out."""
        return {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "up", "about", "into",
            "over", "after", "beneath", "under", "above", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "shall", "can", "this", "that",
            "these", "those", "it", "its", "you", "your", "we", "our",
            "they", "their", "he", "she", "his", "her", "who", "which",
            "what", "when", "where", "why", "how", "all", "each", "every",
            "both", "few", "more", "most", "other", "some", "such", "no",
            "not", "only", "own", "same", "than", "too", "very", "just",
            "also", "now", "here", "there", "then", "use", "using", "used",
        }

    def compare_files(
        self, file1: ClaudeFile, file2: ClaudeFile
    ) -> Dict[str, Any]:
        """Compare two CLAUDE.md files."""
        struct1 = file1.structure or {}
        struct2 = file2.structure or {}

        # Compare sections
        sections1 = set(s["title"].lower() for s in struct1.get("sections", []))
        sections2 = set(s["title"].lower() for s in struct2.get("sections", []))

        # Compare keywords
        keywords1 = set(struct1.get("keywords", []))
        keywords2 = set(struct2.get("keywords", []))

        return {
            "common_sections": list(sections1 & sections2),
            "unique_to_file1": list(sections1 - sections2),
            "unique_to_file2": list(sections2 - sections1),
            "common_keywords": list(keywords1 & keywords2),
            "keyword_overlap_ratio": (
                len(keywords1 & keywords2) / max(len(keywords1 | keywords2), 1)
            ),
            "size_ratio": file1.size / max(file2.size, 1),
        }
