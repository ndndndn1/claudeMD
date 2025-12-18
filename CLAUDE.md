# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GitHub CLAUDE.md 파일 분석 도구. CLAUDE.md 파일을 수집하고, TF-IDF 기반 유사도를 계산하여 그래프로 시각화합니다. GitHub Pages로 배포되는 인터랙티브 뷰어를 제공합니다.

**Live Demo:** https://ndndndn1.github.io/claudeMD/

## Build & Run Commands

```bash
# Install dependencies
pip install -e .

# Collect CLAUDE.md files (stars >= 30 filter)
python collect_to_kuzu.py

# Run CLI
claude-md search --max 50 --min-stars 10
claude-md full --max 30 --min-stars 100 --output ./output

# Run MCP server (auto-configured via .claude/mcp.json)
python -m claude_md_analyzer.mcp_server
```

## Architecture

### Dual Storage System
- **KùzuDB** (`claude_md_analyzer/storage.py`): Graph database for Cypher queries and relationship traversal
- **JSON** (`docs/graph_data.json`): Static export for GitHub Pages visualization

### Data Flow
1. `collect_to_kuzu.py` → GitHub API로 CLAUDE.md 수집 → KùzuDB 저장 → JSON 내보내기
2. `docs/index.html` → graph_data.json 로드 → Cytoscape.js로 시각화

### Key Modules
| Module | Purpose |
|--------|---------|
| `storage.py` | KùzuDB wrapper, RepoNode/SimilarityEdge 관리 |
| `mcp_server.py` | MCP 서버 - Claude Code에서 직접 호출 가능 |
| `agent_api.py` | AI 에이전트용 구조화된 API |
| `embeddings.py` | sentence-transformers 기반 임베딩 |

### MCP Tools (via `.claude/mcp.json`)
| Tool | Description |
|------|-------------|
| `collect_claude_md` | GitHub에서 CLAUDE.md 수집 |
| `search_claude_md` | 저장된 파일 검색 |
| `open_file` | 파일 내용 열기 |
| `analyze_file` | 파일 구조/키워드 분석 |
| `get_similar` | 유사 저장소 찾기 |
| `download_files` | 파일 다운로드 |
| `merge_files` | 파일 병합 |
| `get_graph_data` | 시각화 데이터 반환 |
| `get_stats` | DB 통계 조회 |
| `export_json` | JSON 내보내기 |
| `list_repositories` | 전체 저장소 목록 (정렬 가능) |
| `get_clusters` | 유사도 기반 클러스터 조회 |
| `filter_by_language` | 언어별 필터링 |
| `filter_by_stars` | 별 개수로 필터링 |
| `get_languages` | 언어별 통계 |
| `recalculate_similarities` | 유사도 재계산 |

## Important Notes

- `collect_to_kuzu.py` 실행 시 `graph_data.json`만 업데이트됨 (index.html은 보존)
- `generate_html_visualization()` 함수는 비활성화됨 - 기존 UI 보존 목적
- Summary 필드는 CLAUDE.md의 "Project Overview" 섹션에서 추출 (없으면 첫 문단 사용)
