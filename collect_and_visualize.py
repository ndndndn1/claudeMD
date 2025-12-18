#!/usr/bin/env python3
"""
Collect CLAUDE.md files and generate interactive graph visualization.
Outputs JSON data and HTML for GitHub Pages deployment.
Uses gh CLI for better reliability.
"""

import os
import json
import subprocess
import numpy as np
from collections import Counter
import math

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

def search_claude_md_files(max_results=50):
    """Search GitHub for CLAUDE.md files using gh CLI."""
    print("  Searching GitHub for CLAUDE.md files...")

    # Search for CLAUDE.md files
    results = run_gh_command([
        'search', 'code', 'filename:CLAUDE.md',
        '--limit', str(max_results),
        '--json', 'repository,path'
    ])

    if not results:
        return []

    files = []
    seen_repos = set()

    for item in results:
        repo_name = item['repository']['nameWithOwner']
        if repo_name in seen_repos:
            continue
        seen_repos.add(repo_name)

        print(f"    Processing: {repo_name}...")

        # Get repo details
        repo_info = run_gh_command([
            'repo', 'view', repo_name,
            '--json', 'name,owner,stargazerCount,description,primaryLanguage,repositoryTopics,url'
        ])

        if not repo_info:
            continue

        stars = repo_info.get('stargazerCount', 0)

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
                import base64
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

        files.append({
            "repo_name": repo_info.get('name', ''),
            "repo_full_name": repo_name,
            "stars": stars,
            "description": repo_info.get('description', '') or '',
            "url": f"https://github.com/{repo_name}/blob/main/{item['path']}",
            "repo_url": repo_info.get('url', f"https://github.com/{repo_name}"),
            "language": language_name,
            "topics": topics,
            "content": content,
            "size": len(content),
            "path": item['path']
        })

        print(f"    ✓ Found: {repo_name} ({stars} ⭐)")

    return files

def extract_keywords(content, max_keywords=5):
    """Extract keywords from content."""
    import re
    # Simple keyword extraction from headers
    headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
    keywords = []
    for h in headers[:max_keywords]:
        # Clean up header
        cleaned = re.sub(r'[^\w\s]', '', h).strip().lower()
        if cleaned and len(cleaned) > 2:
            keywords.append(cleaned)
    return keywords[:max_keywords]

def generate_summary(content, max_length=200):
    """Generate simple summary from content."""
    import re
    # Get first paragraph or section
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

def calculate_similarity_tfidf(files):
    """Calculate similarity using TF-IDF."""
    import re

    # Tokenize
    def tokenize(text):
        words = re.findall(r'\b[a-z]+\b', text.lower())
        return [w for w in words if len(w) > 2]

    docs = [tokenize(f['content']) for f in files]

    # Build vocabulary
    vocab = set()
    for doc in docs:
        vocab.update(doc)
    vocab = sorted(vocab)
    word_to_idx = {w: i for i, w in enumerate(vocab)}

    if len(vocab) == 0:
        return np.zeros((len(files), len(files)))

    # Calculate TF-IDF
    n_docs = len(docs)
    df = Counter()
    for doc in docs:
        df.update(set(doc))

    # TF-IDF vectors
    vectors = []
    for doc in docs:
        tf = Counter(doc)
        vec = np.zeros(len(vocab))
        for word, count in tf.items():
            if word in word_to_idx:
                idx = word_to_idx[word]
                idf = math.log(n_docs / (df[word] + 1))
                vec[idx] = count * idf
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vectors.append(vec)

    # Cosine similarity
    vectors = np.array(vectors)
    similarity = np.dot(vectors, vectors.T)

    return similarity

def generate_graph_data(files, similarity_matrix, threshold=0.15):
    """Generate graph data in JSON format for visualization."""
    nodes = []
    edges = []

    # Create nodes
    for i, f in enumerate(files):
        keywords = extract_keywords(f['content'])
        summary = generate_summary(f['content'])

        nodes.append({
            "id": f"node_{i}",
            "label": f['repo_name'],
            "full_name": f['repo_full_name'],
            "stars": f['stars'],
            "description": f['description'] or "",
            "url": f['url'],
            "repo_url": f['repo_url'],
            "language": f['language'] or "Unknown",
            "topics": f['topics'] or [],
            "keywords": keywords,
            "size": f['size'],
            "summary": summary,
        })

    # Create edges based on similarity
    if similarity_matrix is not None:
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                sim = similarity_matrix[i, j]
                if sim >= threshold:
                    edges.append({
                        "source": f"node_{i}",
                        "target": f"node_{j}",
                        "similarity": round(float(sim), 3),
                    })

    return {"nodes": nodes, "edges": edges}

def generate_html_visualization(graph_data, output_path):
    """Generate interactive HTML visualization using Cytoscape.js."""

    nodes_json = json.dumps(graph_data["nodes"])
    edges_json = json.dumps(graph_data["edges"])

    # Calculate statistics
    total_stars = sum(n["stars"] for n in graph_data["nodes"])
    avg_stars = total_stars // len(graph_data["nodes"]) if graph_data["nodes"] else 0
    generated_date = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLAUDE.md Relationship Graph</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.27.0/cytoscape.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/cytoscape-fcose@2.2.0/cytoscape-fcose.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }}
        .header {{
            padding: 20px;
            background: rgba(0,0,0,0.3);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        .stats {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            font-size: 14px;
            color: #aaa;
        }}
        .stat-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .stat-value {{
            color: #4ecdc4;
            font-weight: bold;
            font-size: 18px;
        }}
        .container {{
            display: flex;
            height: calc(100vh - 100px);
        }}
        #cy {{
            flex: 1;
            background: transparent;
        }}
        .sidebar {{
            width: 350px;
            background: rgba(0,0,0,0.3);
            border-left: 1px solid rgba(255,255,255,0.1);
            padding: 20px;
            overflow-y: auto;
        }}
        .sidebar h2 {{
            font-size: 16px;
            color: #4ecdc4;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .node-info {{
            display: none;
        }}
        .node-info.active {{
            display: block;
        }}
        .info-label {{
            font-size: 12px;
            color: #888;
            margin-top: 15px;
            margin-bottom: 5px;
        }}
        .info-value {{
            font-size: 14px;
            color: #fff;
            word-break: break-word;
        }}
        .info-value a {{
            color: #4ecdc4;
            text-decoration: none;
        }}
        .info-value a:hover {{
            text-decoration: underline;
        }}
        .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 5px;
        }}
        .tag {{
            background: rgba(78, 205, 196, 0.2);
            color: #4ecdc4;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 11px;
        }}
        .controls {{
            margin-bottom: 20px;
        }}
        .control-group {{
            margin-bottom: 15px;
        }}
        .control-label {{
            font-size: 12px;
            color: #888;
            margin-bottom: 5px;
        }}
        select, input[type="range"] {{
            width: 100%;
            padding: 8px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 5px;
            color: #fff;
            font-size: 13px;
        }}
        input[type="range"] {{
            -webkit-appearance: none;
            height: 6px;
            padding: 0;
        }}
        input[type="range"]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            background: #4ecdc4;
            border-radius: 50%;
            cursor: pointer;
        }}
        .btn {{
            background: #4ecdc4;
            color: #1a1a2e;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 13px;
            margin-right: 8px;
            margin-bottom: 8px;
        }}
        .btn:hover {{
            background: #3db9b1;
        }}
        .legend {{
            margin-top: 20px;
            padding: 15px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }}
        .legend-title {{
            font-size: 12px;
            color: #888;
            margin-bottom: 10px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
            font-size: 12px;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .placeholder {{
            color: #666;
            text-align: center;
            padding: 40px 20px;
        }}
        .search-box {{
            margin-bottom: 15px;
        }}
        .search-box input {{
            width: 100%;
            padding: 10px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 5px;
            color: #fff;
            font-size: 13px;
        }}
        .search-box input::placeholder {{
            color: #666;
        }}
        .footer {{
            font-size: 11px;
            color: #666;
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
        @media (max-width: 768px) {{
            .container {{
                flex-direction: column;
            }}
            .sidebar {{
                width: 100%;
                height: auto;
                max-height: 300px;
            }}
            #cy {{
                height: 60vh;
            }}
            .stats {{
                flex-direction: column;
                gap: 5px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔗 CLAUDE.md Relationship Graph</h1>
        <div class="stats">
            <div class="stat-item">
                <span>Repositories:</span>
                <span class="stat-value">{len(graph_data["nodes"])}</span>
            </div>
            <div class="stat-item">
                <span>Connections:</span>
                <span class="stat-value">{len(graph_data["edges"])}</span>
            </div>
            <div class="stat-item">
                <span>Total Stars:</span>
                <span class="stat-value">{total_stars:,}</span>
            </div>
            <div class="stat-item">
                <span>Updated:</span>
                <span class="stat-value" style="font-size:14px">{generated_date}</span>
            </div>
        </div>
    </div>

    <div class="container">
        <div id="cy"></div>
        <div class="sidebar">
            <div class="controls">
                <h2>⚙️ Controls</h2>

                <div class="search-box">
                    <input type="text" id="search" placeholder="Search repositories...">
                </div>

                <div class="control-group">
                    <div class="control-label">Layout</div>
                    <select id="layout-select">
                        <option value="fcose">Force-Directed (fcose)</option>
                        <option value="circle">Circle</option>
                        <option value="concentric">Concentric (by stars)</option>
                        <option value="grid">Grid</option>
                    </select>
                </div>

                <div class="control-group">
                    <div class="control-label">Edge Threshold: <span id="threshold-value">0.15</span></div>
                    <input type="range" id="threshold" min="0.05" max="0.8" step="0.05" value="0.15">
                </div>

                <div style="margin-top: 15px;">
                    <button class="btn" onclick="resetView()">🔄 Reset View</button>
                    <button class="btn" onclick="exportPNG()">📷 Export PNG</button>
                </div>
            </div>

            <div class="legend">
                <div class="legend-title">Node Size = Stars</div>
                <div class="legend-title">Edge Width = Similarity</div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #ff6b6b;"></div>
                    <span>High stars (1000+)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #feca57;"></div>
                    <span>Medium stars (100-999)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #4ecdc4;"></div>
                    <span>Low stars (&lt;100)</span>
                </div>
            </div>

            <div id="node-info" class="node-info">
                <h2>📋 Repository Info</h2>
                <div class="info-label">Name</div>
                <div class="info-value" id="info-name"></div>
                <div class="info-label">Stars</div>
                <div class="info-value" id="info-stars"></div>
                <div class="info-label">Language</div>
                <div class="info-value" id="info-language"></div>
                <div class="info-label">Description</div>
                <div class="info-value" id="info-description"></div>
                <div class="info-label">Topics</div>
                <div class="tags" id="info-topics"></div>
                <div class="info-label">Keywords</div>
                <div class="tags" id="info-keywords"></div>
                <div class="info-label">Summary</div>
                <div class="info-value" id="info-summary"></div>
                <div class="info-label">Links</div>
                <div class="info-value">
                    <a id="link-repo" href="#" target="_blank">📁 Repository</a> |
                    <a id="link-file" href="#" target="_blank">📄 CLAUDE.md</a>
                </div>
            </div>

            <div class="placeholder" id="placeholder">
                Click on a node to see details
            </div>

            <div class="footer">
                Generated by Claude MD Analyzer<br>
                Data stored as JSON for GitHub Pages
            </div>
        </div>
    </div>

    <script>
        // Data
        const nodesData = {nodes_json};
        const edgesData = {edges_json};

        let currentThreshold = 0.15;

        // Get node color based on stars
        function getNodeColor(stars) {{
            if (stars >= 1000) return '#ff6b6b';
            if (stars >= 100) return '#feca57';
            return '#4ecdc4';
        }}

        // Get node size based on stars (log scale)
        function getNodeSize(stars) {{
            return Math.max(20, Math.min(80, 15 + Math.log10(stars + 1) * 15));
        }}

        // Create Cytoscape elements
        function createElements(threshold) {{
            const nodes = nodesData.map(n => ({{
                data: {{
                    id: n.id,
                    label: n.label,
                    ...n
                }}
            }}));

            const edges = edgesData
                .filter(e => e.similarity >= threshold)
                .map(e => ({{
                    data: {{
                        id: e.source + '-' + e.target,
                        source: e.source,
                        target: e.target,
                        similarity: e.similarity
                    }}
                }}));

            return [...nodes, ...edges];
        }}

        // Initialize Cytoscape
        let cy = cytoscape({{
            container: document.getElementById('cy'),
            elements: createElements(currentThreshold),
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'label': 'data(label)',
                        'width': function(ele) {{ return getNodeSize(ele.data('stars')); }},
                        'height': function(ele) {{ return getNodeSize(ele.data('stars')); }},
                        'background-color': function(ele) {{ return getNodeColor(ele.data('stars')); }},
                        'border-width': 2,
                        'border-color': '#fff',
                        'color': '#fff',
                        'font-size': '10px',
                        'text-valign': 'bottom',
                        'text-margin-y': 5,
                        'text-outline-width': 2,
                        'text-outline-color': '#1a1a2e'
                    }}
                }},
                {{
                    selector: 'node:selected',
                    style: {{
                        'border-width': 4,
                        'border-color': '#fff',
                        'background-color': '#fff',
                        'color': '#4ecdc4'
                    }}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'width': function(ele) {{ return 1 + ele.data('similarity') * 5; }},
                        'line-color': 'rgba(78, 205, 196, 0.4)',
                        'curve-style': 'bezier',
                        'opacity': function(ele) {{ return 0.3 + ele.data('similarity') * 0.5; }}
                    }}
                }},
                {{
                    selector: 'edge:selected',
                    style: {{
                        'line-color': '#4ecdc4',
                        'opacity': 1
                    }}
                }},
                {{
                    selector: '.highlighted',
                    style: {{
                        'background-color': '#fff',
                        'border-color': '#4ecdc4'
                    }}
                }},
                {{
                    selector: '.faded',
                    style: {{
                        'opacity': 0.2
                    }}
                }}
            ],
            layout: {{
                name: 'fcose',
                animate: true,
                randomize: true,
                nodeDimensionsIncludeLabels: true,
                idealEdgeLength: 150,
                nodeRepulsion: 8000,
                edgeElasticity: 0.45
            }}
        }});

        // Node click handler
        cy.on('tap', 'node', function(evt) {{
            const node = evt.target;
            const data = node.data();

            document.getElementById('info-name').innerHTML =
                '<a href="' + data.repo_url + '" target="_blank">' + data.full_name + '</a>';
            document.getElementById('info-stars').textContent = data.stars.toLocaleString() + ' ⭐';
            document.getElementById('info-language').textContent = data.language || 'Unknown';
            document.getElementById('info-description').textContent = data.description || 'No description';
            document.getElementById('info-summary').textContent = data.summary || 'No summary available';

            // Topics
            const topicsEl = document.getElementById('info-topics');
            topicsEl.innerHTML = (data.topics || []).map(t => '<span class="tag">' + t + '</span>').join('');

            // Keywords
            const keywordsEl = document.getElementById('info-keywords');
            keywordsEl.innerHTML = (data.keywords || []).map(k => '<span class="tag">' + k + '</span>').join('');

            document.getElementById('link-repo').href = data.repo_url;
            document.getElementById('link-file').href = data.url;

            document.getElementById('node-info').classList.add('active');
            document.getElementById('placeholder').style.display = 'none';

            // Highlight connected nodes
            cy.elements().removeClass('highlighted faded');
            const neighborhood = node.neighborhood().add(node);
            cy.elements().not(neighborhood).addClass('faded');
            neighborhood.addClass('highlighted');
        }});

        // Background click
        cy.on('tap', function(evt) {{
            if (evt.target === cy) {{
                cy.elements().removeClass('highlighted faded');
            }}
        }});

        // Layout change
        document.getElementById('layout-select').addEventListener('change', function() {{
            const layoutName = this.value;
            let layout;

            if (layoutName === 'concentric') {{
                layout = {{
                    name: 'concentric',
                    concentric: function(node) {{ return node.data('stars'); }},
                    levelWidth: function() {{ return 2; }},
                    animate: true
                }};
            }} else if (layoutName === 'fcose') {{
                layout = {{
                    name: 'fcose',
                    animate: true,
                    randomize: false,
                    nodeDimensionsIncludeLabels: true,
                    idealEdgeLength: 150,
                    nodeRepulsion: 8000
                }};
            }} else {{
                layout = {{
                    name: layoutName,
                    animate: true
                }};
            }}

            cy.layout(layout).run();
        }});

        // Threshold change
        document.getElementById('threshold').addEventListener('input', function() {{
            currentThreshold = parseFloat(this.value);
            document.getElementById('threshold-value').textContent = currentThreshold.toFixed(2);

            // Update edges
            cy.edges().remove();
            const newEdges = edgesData
                .filter(e => e.similarity >= currentThreshold)
                .map(e => ({{
                    data: {{
                        id: e.source + '-' + e.target,
                        source: e.source,
                        target: e.target,
                        similarity: e.similarity
                    }}
                }}));
            cy.add(newEdges);
        }});

        // Search
        document.getElementById('search').addEventListener('input', function() {{
            const query = this.value.toLowerCase();

            if (!query) {{
                cy.elements().removeClass('highlighted faded');
                return;
            }}

            const matches = cy.nodes().filter(node => {{
                const data = node.data();
                return data.label.toLowerCase().includes(query) ||
                       data.full_name.toLowerCase().includes(query) ||
                       (data.description || '').toLowerCase().includes(query) ||
                       (data.topics || []).some(t => t.toLowerCase().includes(query));
            }});

            if (matches.length > 0) {{
                cy.elements().addClass('faded');
                matches.removeClass('faded').addClass('highlighted');
                const neighborhood = matches.neighborhood();
                neighborhood.removeClass('faded');
            }}
        }});

        // Reset view
        function resetView() {{
            cy.fit();
            cy.elements().removeClass('highlighted faded');
            document.getElementById('search').value = '';
        }}

        // Export PNG
        function exportPNG() {{
            const png = cy.png({{
                output: 'blob',
                bg: '#1a1a2e',
                scale: 2
            }});

            const link = document.createElement('a');
            link.href = URL.createObjectURL(png);
            link.download = 'claude-md-graph.png';
            link.click();
        }}
    </script>
</body>
</html>
'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"  ✓ Generated HTML visualization: {output_path}")

def main():
    print("=" * 60)
    print("CLAUDE.md Analyzer - Graph Visualization Generator")
    print("=" * 60)
    print()

    # Collect data
    print("🔍 Starting CLAUDE.md collection...")
    files = search_claude_md_files(max_results=50)

    if not files:
        print("❌ No files collected. Exiting.")
        return

    print()
    print(f"📊 Collected {len(files)} files")

    # Calculate similarity matrix
    print("📐 Calculating similarity matrix...")
    similarity_matrix = calculate_similarity_tfidf(files)
    print("  ✓ Similarity matrix calculated")

    # Generate graph data
    print("🔗 Generating graph data...")
    graph_data = generate_graph_data(files, similarity_matrix, threshold=0.15)
    print(f"  ✓ Nodes: {len(graph_data['nodes'])}, Edges: {len(graph_data['edges'])}")

    # Create output directories
    os.makedirs("./docs", exist_ok=True)
    os.makedirs("./output", exist_ok=True)

    # Save graph data as JSON
    json_path = "./docs/graph_data.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved graph data: {json_path}")

    # Generate HTML visualization
    print("🎨 Generating HTML visualization...")
    html_path = "./docs/index.html"
    generate_html_visualization(graph_data, html_path)

    # Also save to output directory
    generate_html_visualization(graph_data, "./output/graph_visualization.html")

    print()
    print("=" * 60)
    print("✅ Complete!")
    print("=" * 60)
    print()
    print("📁 Output files:")
    print(f"   - {json_path} (Graph data - JSON)")
    print(f"   - {html_path} (Interactive visualization)")
    print()
    print("🚀 For GitHub Pages deployment:")
    print("   1. Enable GitHub Pages in repository settings")
    print("   2. Set source to 'docs' folder")
    print("   3. Access at: https://<username>.github.io/<repo>/")

if __name__ == "__main__":
    main()
