#!/usr/bin/env python3
"""
Collect CLAUDE.md files and store in KùzuDB.
Also generates graph visualization for GitHub Pages.
"""

import os
import json
import subprocess
import base64
from datetime import datetime
from collections import Counter
import math
import re

from claude_md_analyzer.storage import KuzuStorage, RepoNode


def run_gh_command(args):
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
    except Exception as e:
        print(f"    Error: {e}")
        return None


def extract_keywords(content, max_keywords=5):
    """Extract keywords from content."""
    headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
    keywords = []
    for h in headers[:max_keywords]:
        cleaned = re.sub(r'[^\w\s]', '', h).strip().lower()
        if cleaned and len(cleaned) > 2:
            keywords.append(cleaned)
    return keywords[:max_keywords]


def generate_summary(content, max_length=200):
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


def calculate_tfidf_similarity(contents):
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


def collect_and_store(max_results=50, db_path="./data/kuzu_db"):
    """Collect CLAUDE.md files and store in KùzuDB."""
    print("=" * 60)
    print("CLAUDE.md Collector - KùzuDB Storage")
    print("=" * 60)
    print()

    # Initialize storage
    print("📦 Initializing KùzuDB storage...")
    storage = KuzuStorage(db_path)
    print(f"  ✓ Database path: {db_path}")

    # Search for CLAUDE.md files
    print()
    print("🔍 Searching GitHub for CLAUDE.md files...")
    results = run_gh_command([
        'search', 'code', 'filename:CLAUDE.md',
        '--limit', str(max_results),
        '--json', 'repository,path'
    ])

    if not results:
        print("❌ No files found or GitHub CLI error")
        return

    print(f"  ✓ Found {len(results)} search results")

    # Process each result
    print()
    print("📥 Collecting files...")
    collected = []
    contents = []
    repo_ids = []

    for item in results:
        repo_name = item['repository']['nameWithOwner']
        print(f"  Processing: {repo_name}...", end=" ")

        # Get repo details
        repo_info = run_gh_command([
            'repo', 'view', repo_name,
            '--json', 'name,owner,stargazerCount,description,primaryLanguage,repositoryTopics,url'
        ])

        if not repo_info:
            print("❌ Failed")
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

        if storage.add_repository(repo):
            collected.append(repo_name)
            contents.append(content)
            repo_ids.append(repo_name)
            print(f"✓ ({repo_info.get('stargazerCount', 0)} ⭐)")
        else:
            print("❌ Failed to store")

    print()
    print(f"📊 Collected {len(collected)} files")

    # Calculate and store similarities
    if len(contents) > 1:
        print()
        print("📐 Calculating similarities...")
        similarity_matrix = calculate_tfidf_similarity(contents)

        edge_count = 0
        for i in range(len(repo_ids)):
            for j in range(i + 1, len(repo_ids)):
                sim = similarity_matrix[i][j]
                if sim >= 0.1:
                    storage.add_similarity(repo_ids[i], repo_ids[j], sim)
                    edge_count += 1

        print(f"  ✓ Created {edge_count} similarity relationships")

    # Export to JSON for visualization
    print()
    print("📤 Exporting data...")
    os.makedirs("./docs", exist_ok=True)
    storage.export_to_json("./docs/graph_data.json")
    print("  ✓ Exported to ./docs/graph_data.json")

    # Generate HTML visualization
    print("🎨 Generating visualization...")
    generate_html_visualization(storage)
    print("  ✓ Generated ./docs/index.html")

    # Show stats
    print()
    print("=" * 60)
    stats = storage.get_stats()
    print(f"✅ Complete!")
    print(f"   Repositories: {stats.get('total_repositories', 0)}")
    print(f"   Relationships: {stats.get('total_relationships', 0)}")
    print(f"   Total Stars: {stats.get('total_stars', 0):,}")
    print("=" * 60)

    storage.close()


def generate_html_visualization(storage):
    """Generate interactive HTML visualization."""
    graph_data = storage.get_graph_data(min_similarity=0.1)

    nodes_json = json.dumps(graph_data["nodes"])
    edges_json = json.dumps(graph_data["edges"])

    total_stars = sum(n["stars"] for n in graph_data["nodes"])
    avg_stars = total_stars // len(graph_data["nodes"]) if graph_data["nodes"] else 0
    generated_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Read existing HTML template or create new
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLAUDE.md Relationship Graph</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.27.0/cytoscape.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/cytoscape-fcose@2.2.0/cytoscape-fcose.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #fff; }}
        .header {{ padding: 20px; background: rgba(0,0,0,0.3); border-bottom: 1px solid rgba(255,255,255,0.1); }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 20px; font-size: 14px; color: #aaa; }}
        .stat-item {{ display: flex; align-items: center; gap: 8px; }}
        .stat-value {{ color: #4ecdc4; font-weight: bold; font-size: 18px; }}
        .container {{ display: flex; height: calc(100vh - 100px); }}
        #cy {{ flex: 1; background: transparent; }}
        .sidebar {{ width: 350px; background: rgba(0,0,0,0.3); border-left: 1px solid rgba(255,255,255,0.1); padding: 20px; overflow-y: auto; }}
        .sidebar h2 {{ font-size: 16px; color: #4ecdc4; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        .node-info {{ display: none; }}
        .node-info.active {{ display: block; }}
        .info-label {{ font-size: 12px; color: #888; margin-top: 15px; margin-bottom: 5px; }}
        .info-value {{ font-size: 14px; color: #fff; word-break: break-word; }}
        .info-value a {{ color: #4ecdc4; text-decoration: none; }}
        .info-value a:hover {{ text-decoration: underline; }}
        .tags {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }}
        .tag {{ background: rgba(78, 205, 196, 0.2); color: #4ecdc4; padding: 3px 8px; border-radius: 10px; font-size: 11px; }}
        .controls {{ margin-bottom: 20px; }}
        .control-group {{ margin-bottom: 15px; }}
        .control-label {{ font-size: 12px; color: #888; margin-bottom: 5px; }}
        select, input[type="range"] {{ width: 100%; padding: 8px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 5px; color: #fff; font-size: 13px; }}
        .btn {{ background: #4ecdc4; color: #1a1a2e; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 13px; margin-right: 8px; margin-bottom: 8px; }}
        .btn:hover {{ background: #3db9b1; }}
        .legend {{ margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.05); border-radius: 8px; }}
        .legend-title {{ font-size: 12px; color: #888; margin-bottom: 10px; }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; margin-bottom: 5px; font-size: 12px; }}
        .legend-color {{ width: 12px; height: 12px; border-radius: 50%; }}
        .placeholder {{ color: #666; text-align: center; padding: 40px 20px; }}
        .search-box {{ margin-bottom: 15px; }}
        .search-box input {{ width: 100%; padding: 10px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 5px; color: #fff; font-size: 13px; }}
        .footer {{ font-size: 11px; color: #666; margin-top: 20px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); }}
        @media (max-width: 768px) {{ .container {{ flex-direction: column; }} .sidebar {{ width: 100%; height: auto; max-height: 300px; }} #cy {{ height: 60vh; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔗 CLAUDE.md Relationship Graph</h1>
        <div class="stats">
            <div class="stat-item"><span>Repositories:</span><span class="stat-value">{len(graph_data["nodes"])}</span></div>
            <div class="stat-item"><span>Connections:</span><span class="stat-value">{len(graph_data["edges"])}</span></div>
            <div class="stat-item"><span>Total Stars:</span><span class="stat-value">{total_stars:,}</span></div>
            <div class="stat-item"><span>Updated:</span><span class="stat-value" style="font-size:14px">{generated_date}</span></div>
        </div>
    </div>
    <div class="container">
        <div id="cy"></div>
        <div class="sidebar">
            <div class="controls">
                <h2>⚙️ Controls</h2>
                <div class="search-box"><input type="text" id="search" placeholder="Search repositories..."></div>
                <div class="control-group">
                    <div class="control-label">Layout</div>
                    <select id="layout-select">
                        <option value="fcose">Force-Directed</option>
                        <option value="circle">Circle</option>
                        <option value="concentric">Concentric</option>
                        <option value="grid">Grid</option>
                    </select>
                </div>
                <div class="control-group">
                    <div class="control-label">Edge Threshold: <span id="threshold-value">0.10</span></div>
                    <input type="range" id="threshold" min="0.05" max="0.8" step="0.05" value="0.1">
                </div>
                <div style="margin-top: 15px;">
                    <button class="btn" onclick="resetView()">🔄 Reset</button>
                    <button class="btn" onclick="exportPNG()">📷 Export</button>
                </div>
            </div>
            <div class="legend">
                <div class="legend-title">Node Size = Stars</div>
                <div class="legend-item"><div class="legend-color" style="background: #ff6b6b;"></div><span>1000+ stars</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #feca57;"></div><span>100-999 stars</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #4ecdc4;"></div><span>&lt;100 stars</span></div>
            </div>
            <div id="node-info" class="node-info">
                <h2>📋 Repository</h2>
                <div class="info-label">Name</div><div class="info-value" id="info-name"></div>
                <div class="info-label">Stars</div><div class="info-value" id="info-stars"></div>
                <div class="info-label">Language</div><div class="info-value" id="info-language"></div>
                <div class="info-label">Description</div><div class="info-value" id="info-description"></div>
                <div class="info-label">Topics</div><div class="tags" id="info-topics"></div>
                <div class="info-label">Keywords</div><div class="tags" id="info-keywords"></div>
                <div class="info-label">Links</div>
                <div class="info-value"><a id="link-repo" href="#" target="_blank">📁 Repo</a> | <a id="link-file" href="#" target="_blank">📄 CLAUDE.md</a></div>
            </div>
            <div class="placeholder" id="placeholder">Click a node</div>
            <div class="footer">KùzuDB Storage | MCP Server Ready</div>
        </div>
    </div>
    <script>
        const nodesData = {nodes_json};
        const edgesData = {edges_json};
        let currentThreshold = 0.1;
        function getNodeColor(stars) {{ if (stars >= 1000) return '#ff6b6b'; if (stars >= 100) return '#feca57'; return '#4ecdc4'; }}
        function getNodeSize(stars) {{ return Math.max(20, Math.min(80, 15 + Math.log10(stars + 1) * 15)); }}
        function createElements(threshold) {{
            const nodes = nodesData.map(n => ({{ data: {{ id: n.id, label: n.label, ...n }} }}));
            const edges = edgesData.filter(e => e.similarity >= threshold).map(e => ({{ data: {{ id: e.source + '-' + e.target, source: e.source, target: e.target, similarity: e.similarity }} }}));
            return [...nodes, ...edges];
        }}
        let cy = cytoscape({{
            container: document.getElementById('cy'),
            elements: createElements(currentThreshold),
            style: [
                {{ selector: 'node', style: {{ 'label': 'data(label)', 'width': function(ele) {{ return getNodeSize(ele.data('stars')); }}, 'height': function(ele) {{ return getNodeSize(ele.data('stars')); }}, 'background-color': function(ele) {{ return getNodeColor(ele.data('stars')); }}, 'border-width': 2, 'border-color': '#fff', 'color': '#fff', 'font-size': '10px', 'text-valign': 'bottom', 'text-margin-y': 5, 'text-outline-width': 2, 'text-outline-color': '#1a1a2e' }} }},
                {{ selector: 'edge', style: {{ 'width': function(ele) {{ return 1 + ele.data('similarity') * 5; }}, 'line-color': 'rgba(78, 205, 196, 0.4)', 'curve-style': 'bezier', 'opacity': function(ele) {{ return 0.3 + ele.data('similarity') * 0.5; }} }} }},
                {{ selector: '.faded', style: {{ 'opacity': 0.2 }} }}
            ],
            layout: {{ name: 'fcose', animate: true, randomize: true, nodeDimensionsIncludeLabels: true, idealEdgeLength: 150, nodeRepulsion: 8000 }}
        }});
        cy.on('tap', 'node', function(evt) {{
            const data = evt.target.data();
            document.getElementById('info-name').innerHTML = '<a href="' + data.repo_url + '" target="_blank">' + data.full_name + '</a>';
            document.getElementById('info-stars').textContent = data.stars.toLocaleString() + ' ⭐';
            document.getElementById('info-language').textContent = data.language || 'Unknown';
            document.getElementById('info-description').textContent = data.description || 'No description';
            document.getElementById('info-topics').innerHTML = (data.topics || []).map(t => '<span class="tag">' + t + '</span>').join('');
            document.getElementById('info-keywords').innerHTML = (data.keywords || []).map(k => '<span class="tag">' + k + '</span>').join('');
            document.getElementById('link-repo').href = data.repo_url;
            document.getElementById('link-file').href = data.url;
            document.getElementById('node-info').classList.add('active');
            document.getElementById('placeholder').style.display = 'none';
            cy.elements().removeClass('faded');
            const neighborhood = evt.target.neighborhood().add(evt.target);
            cy.elements().not(neighborhood).addClass('faded');
        }});
        cy.on('tap', function(evt) {{ if (evt.target === cy) cy.elements().removeClass('faded'); }});
        document.getElementById('layout-select').addEventListener('change', function() {{
            const name = this.value;
            let layout = name === 'concentric' ? {{ name: 'concentric', concentric: n => n.data('stars'), levelWidth: () => 2, animate: true }} : {{ name, animate: true }};
            cy.layout(layout).run();
        }});
        document.getElementById('threshold').addEventListener('input', function() {{
            currentThreshold = parseFloat(this.value);
            document.getElementById('threshold-value').textContent = currentThreshold.toFixed(2);
            cy.edges().remove();
            cy.add(edgesData.filter(e => e.similarity >= currentThreshold).map(e => ({{ data: {{ id: e.source + '-' + e.target, source: e.source, target: e.target, similarity: e.similarity }} }})));
        }});
        document.getElementById('search').addEventListener('input', function() {{
            const q = this.value.toLowerCase();
            if (!q) {{ cy.elements().removeClass('faded'); return; }}
            const matches = cy.nodes().filter(n => n.data('label').toLowerCase().includes(q) || n.data('full_name').toLowerCase().includes(q));
            cy.elements().addClass('faded');
            matches.removeClass('faded');
            matches.neighborhood().removeClass('faded');
        }});
        function resetView() {{ cy.fit(); cy.elements().removeClass('faded'); document.getElementById('search').value = ''; }}
        function exportPNG() {{ const png = cy.png({{ output: 'blob', bg: '#1a1a2e', scale: 2 }}); const link = document.createElement('a'); link.href = URL.createObjectURL(png); link.download = 'claude-md-graph.png'; link.click(); }}
    </script>
</body>
</html>
'''

    with open("./docs/index.html", 'w', encoding='utf-8') as f:
        f.write(html_content)


if __name__ == "__main__":
    collect_and_store(max_results=50)
