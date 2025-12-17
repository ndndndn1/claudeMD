# Claude MD Analyzer

GitHub CLAUDE.md 파일 분석 도구 - 임베딩 기반 관계 시각화 지원

## Features

- **GitHub 검색**: CLAUDE.md 파일 검색 (대소문자 무관)
- **메타데이터 수집**: 저장소 이름, 설명, star 수, 파일 구조
- **콘텐츠 분석**: 섹션 추출, 키워드 분석, 요약 생성
- **임베딩 시각화**: 파일 간 관계를 임베딩으로 시각화
- **일괄 다운로드**: 관련 파일 일괄 다운로드
- **파일 병합**: 여러 CLAUDE.md 파일을 하나로 병합
- **Agent-Friendly API**: AI 에이전트 친화적 인터페이스

## Installation

```bash
pip install -e .
```

또는 requirements만 설치:

```bash
pip install -r requirements.txt
```

## Quick Start

### CLI 사용

```bash
# 전체 분석 파이프라인 실행
claude-md full --max 30 --min-stars 100 --output ./output

# 검색만 실행
claude-md search --max 50 --min-stars 10

# 특정 파일 열기
claude-md open-file "https://github.com/owner/repo/blob/main/CLAUDE.md"

# 파일 다운로드
claude-md download --input results.json --output ./downloads

# 파일 병합
claude-md merge --input results.json --output MERGED.md
```

### Python API 사용

```python
from claude_md_analyzer import AgentAPI

# API 초기화
api = AgentAPI(github_token="your_token")

# 검색
result = api.search(max_results=50, min_stars=10)
print(result.to_json())

# 분석
result = api.analyze()

# 임베딩 생성 및 유사 파일 찾기
api.generate_embeddings()
similar = api.find_similar(file_index=0, top_k=5)

# 시각화 생성
api.visualize()

# 다운로드
api.download()

# 병합
api.merge()
```

### Agent API (AI 에이전트용)

```python
from claude_md_analyzer import AgentAPI

api = AgentAPI()

# 전체 분석 한 번에 실행
result = api.run_full_analysis(max_results=30, min_stars=100)

# 결과는 구조화된 JSON으로 반환
print(result.to_json())
```

## Agent API Methods

| Method | Description |
|--------|-------------|
| `search(max_results, min_stars, language)` | GitHub에서 CLAUDE.md 파일 검색 |
| `get_file(url)` | URL로 특정 파일 가져오기 |
| `analyze(file_index)` | 파일 분석 및 구조 추출 |
| `get_summary_table()` | 모든 파일 요약 테이블 |
| `generate_embeddings()` | 임베딩 생성 |
| `find_similar(file_index, top_k)` | 유사 파일 찾기 |
| `cluster_files(n_clusters)` | 파일 클러스터링 |
| `visualize(types)` | 시각화 생성 |
| `download(file_indices)` | 파일 다운로드 |
| `download_related(file_index)` | 관련 파일 다운로드 |
| `merge(file_indices)` | 파일 병합 |
| `create_summary()` | 요약 문서 생성 |
| `export_metadata(format)` | 메타데이터 내보내기 (JSON/CSV) |
| `list_files()` | 로드된 파일 목록 |
| `get_file_content(file_index)` | 특정 파일 내용 가져오기 |
| `run_full_analysis()` | 전체 분석 파이프라인 |

## Visualization Types

- **scatter**: 2D 산점도 - 파일 간 관계 시각화
- **heatmap**: 히트맵 - 유사도 매트릭스
- **network**: 네트워크 그래프 - 연결 관계 시각화
- **table**: HTML 테이블 - 요약 정보

## Output Structure

```
output/
├── relationship_scatter.html    # 관계 산점도
├── similarity_heatmap.html      # 유사도 히트맵
├── relationship_network.html    # 네트워크 그래프
├── summary_table.html           # 요약 테이블
├── downloads/                   # 다운로드된 파일
│   ├── owner/repo/CLAUDE.md
│   └── INDEX.md
└── merged/                      # 병합된 파일
    ├── MERGED_CLAUDE.md
    └── CLAUDE_SUMMARY.md
```

## Environment Variables

- `GITHUB_TOKEN`: GitHub Personal Access Token (권장)

## Requirements

- Python 3.9+
- sentence-transformers
- plotly
- scikit-learn
- umap-learn
- requests
- PyGithub
- rich
- typer

## License

MIT
