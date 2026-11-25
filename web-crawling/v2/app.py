"""
Flask Web Application for Web Crawler Visualization
"""

import os
import threading
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

# Import crawler logic
from crawler_logic import crawl_and_analyze
from pyvis.network import Network
import networkx as nx

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# In-memory job storage (use Redis or database in production)
jobs = {}


# def generate_graph_html(graph: nx.DiGraph, pagerank: dict) -> str:
#     """Generate an interactive HTML visualization of the graph using pyvis."""
#     net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="#333333", directed=True, cdn_resources="in_line")
#     net.barnes_hut(gravity=-3000, central_gravity=0.2, spring_length=150, spring_strength=0.02, damping=0.09)

#     # Get max PageRank for normalization
#     max_pr = max(pagerank.values()) if pagerank else 1
#     min_pr = min(pagerank.values()) if pagerank else 0

#     # Add nodes
#     for node in graph.nodes():
#         pr = pagerank.get(node, 0)
#         # Normalize size based on PageRank (10-50)
#         size = 10 + (pr / max_pr * 40) if max_pr > 0 else 20
#         # Color based on PageRank (blue to red gradient)
#         intensity = int(255 * (pr / max_pr)) if max_pr > 0 else 128
#         color = f"rgb({intensity}, {100}, {255 - intensity})"

#         # Truncate label for display
#         from urllib.parse import urlparse
#         parsed = urlparse(node)
#         label = f"{parsed.netloc}{parsed.path}" if parsed.path else parsed.netloc
#         if len(label) > 40:
#             label = label[:37] + "..."

#         net.add_node(node, label=label, title=f"{node}\nPageRank: {pr:.6f}",
#                     size=size, color=color, font={'size': 12})

#     # Add edges
#     for source, target in graph.edges():
#         net.add_edge(source, target, arrows='to', color='#888888', width=1)

#     # Generate HTML
#     return net.generate_html(notebook=False)


# def generate_graph_html(graph: nx.DiGraph, pagerank: dict) -> str:
def generate_graph_html(graph: nx.DiGraph, link_counts: dict) -> str:
    """Generate an interactive HTML graph that stops moving after stabilization."""
    net = Network(
        height="600px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#333333",
        directed=True,
        cdn_resources="in_line"
    )

    net.barnes_hut(
        gravity=-2000,
        central_gravity=0.3,
        spring_length=150,
        spring_strength=0.05,
        damping=0.09
    )

    # max_pr = max(pagerank.values()) if pagerank else 1
    max_pr = max(link_counts.values()) if link_counts else 1

    # Add nodes
    for node in graph.nodes():
        # pr = pagerank.get(node, 0)
        pr = link_counts.get(node, 0)

        size = 10 + (pr / max_pr * 40) if max_pr > 0 else 20
        intensity = int(255 * (pr / max_pr)) if max_pr > 0 else 128
        color = f"rgb({intensity}, 100, {255 - intensity})"

        from urllib.parse import urlparse
        parsed = urlparse(node)

        label = f"{parsed.netloc}{parsed.path}" if parsed.path else parsed.netloc

        if len(label) > 40:
            label = label[:37] + "..."

        net.add_node(
            node,
            label=label,
            # title=f"{node}\nPageRank: {pr:.6f}",
            title=f"{node}\nJumlah Link Masuk: {pr}",
            size=size,
            color=color,
            font={'size': 12}
        )

    # Add edges
    for source, target in graph.edges():
        net.add_edge(
            source,
            target,
            arrows='to',
            color='#888888',
            width=1
        )

    # Physics aktif hanya selama proses stabilisasi
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "stabilization": {
                "enabled": true,
                "iterations": 1000,
                "updateInterval": 50,
                "fit": true
            },
            "minVelocity": 0.75
        },
        "interaction": {
            "dragNodes": true,
            "dragView": true,
            "zoomView": true,
            "navigationButtons": true
        }
    }
    """)

    html = net.generate_html(notebook=False)

    # Matikan physics setelah graph selesai stabil
    marker = "network = new vis.Network(container, data, options);"

    freeze_script = """
    network.on("stabilizationIterationsDone", function () {
        network.setOptions({
            physics: {
                enabled: false
            }
        });
    });
    """

    interaction_script = """
    // Filter graph: tampilkan node yang dipilih dan tetangga langsungnya.
    const allNodeIds = network.body.data.nodes.getIds();
    const allEdgeIds = network.body.data.edges.getIds();

    const backButton = document.createElement("button");
    backButton.id = "showAllGraphButton";
    backButton.type = "button";
    backButton.textContent = "← Back / Tampilkan Semua";
    backButton.style.cssText = [
        "position:absolute",
        "top:12px",
        "left:12px",
        "z-index:1000",
        "display:none",
        "padding:9px 14px",
        "border:1px solid #ced4da",
        "border-radius:7px",
        "background:#ffffff",
        "color:#212529",
        "font-size:13px",
        "font-weight:600",
        "cursor:pointer",
        "box-shadow:0 2px 8px rgba(0,0,0,.15)"
    ].join(";");
    document.body.appendChild(backButton);

    function showAllGraph() {
        network.body.data.nodes.update(
            allNodeIds.map(id => ({ id: id, hidden: false }))
        );
        network.body.data.edges.update(
            allEdgeIds.map(id => ({ id: id, hidden: false }))
        );
        backButton.style.display = "none";
        network.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
    }

    function showConnectedGraph(selectedNodeId) {
        const connectedIds = network.getConnectedNodes(selectedNodeId);
        const visibleIds = new Set([selectedNodeId, ...connectedIds]);

        network.body.data.nodes.update(
            allNodeIds.map(id => ({ id: id, hidden: !visibleIds.has(id) }))
        );

        const visibleEdges = [];
        network.body.data.edges.get().forEach(edge => {
            const isConnected = visibleIds.has(edge.from) && visibleIds.has(edge.to);
            visibleEdges.push({ id: edge.id, hidden: !isConnected });
        });
        network.body.data.edges.update(visibleEdges);

        backButton.style.display = "block";
        network.fit({
            nodes: Array.from(visibleIds),
            animation: { duration: 400, easingFunction: "easeInOutQuad" }
        });
    }

    network.on("click", function (params) {
        if (params.nodes && params.nodes.length > 0) {
            showConnectedGraph(params.nodes[0]);

            // Send nodeClicked event to parent window
            const clickedNodeId = params.nodes[0];
            window.parent.postMessage({
                type: 'nodeClicked',
                url: clickedNodeId
            }, '*');
        }
    });

    backButton.addEventListener("click", showAllGraph);

    // Mendukung tombol Reset View dari halaman result.html.
    window.addEventListener("message", function (event) {
        if (event.data && event.data.type === "fit") {
            network.fit();
        } else if (event.data && event.data.type === "showAll") {
            showAllGraph();
        } else if (event.data && event.data.type === "showConnected") {
            // Handle showConnected message from parent (table row click)
            const targetUrl = event.data.url;
            if (targetUrl && allNodeIds.includes(targetUrl)) {
                showConnectedGraph(targetUrl);
            }
        }
    });
    """

    if marker in html:
        html = html.replace(
            marker,
            marker + freeze_script + interaction_script,
            1
        )

    return html



def run_crawl(job_id: str, start_url: str, max_depth: int, max_pages: int = 50):
    """Background task to run the crawl."""
    try:
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['message'] = 'Crawling in progress...'

        result = crawl_and_analyze(
            start_url=start_url,
            max_depth=max_depth,
            max_pages=max_pages,
            timeout=10,
            delay=0.5,
            verify_ssl=False,
            unique_domains=True,
            overall_timeout=300
        )

        # Generate graph HTML
        # graph_html = generate_graph_html(result['graph'], result['pagerank'])
        graph_html = generate_graph_html(
            result['graph'],
            result['in_degree']
        )

        # Store graph data for API access (nodes and edges)
        nodes = list(result['graph'].nodes())
        edges = list(result['graph'].edges())

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result'] = {
            'graph_html': graph_html,
            'top_10': result['top_10'],
            'pages_crawled': result['stats']['visited_pages'],
            'errors': result['errors'],
            'graph_nodes': nodes,
            'graph_edges': edges
        }
        jobs[job_id]['message'] = f'Crawling completed! {result["stats"]["visited_pages"]} pages crawled.'
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['message'] = f'Error: {str(e)}'
        jobs[job_id]['result'] = None


@app.route('/')
def index():
    """Homepage with URL input form."""
    return render_template('index.html')


@app.route('/crawl', methods=['POST'])
def crawl():
    """Start a crawl job."""
    start_url = request.form.get('url', '').strip()
    max_depth = int(request.form.get('max_depth', 3))
    max_pages = int(request.form.get('max_pages', 50))

    if not start_url:
        return jsonify({'error': 'URL is required'}), 400

    # Basic URL validation
    if not (start_url.startswith('http://') or start_url.startswith('https://')):
        start_url = 'https://' + start_url

    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        'id': job_id,
        'url': start_url,
        'status': 'pending',
        'message': 'Initializing...',
        'result': None
    }

    # Start background thread
    thread = threading.Thread(target=run_crawl, args=(job_id, start_url, max_depth, max_pages))
    thread.daemon = True
    thread.start()

    return redirect(url_for('job_status', job_id=job_id))


@app.route('/job/<job_id>')
def job_status(job_id):
    """Show job status page."""
    job = jobs.get(job_id)
    if not job:
        return render_template('error.html', message='Job not found'), 404
    return render_template('job_status.html', job=job)


@app.route('/api/job/<job_id>')
def job_status_api(job_id):
    """API endpoint for job status (for polling)."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'id': job['id'],
        'url': job['url'],
        'status': job['status'],
        'message': job['message']
    }

    if job['status'] == 'completed' and job['result']:
        response['result'] = job['result']

    return jsonify(response)


@app.route('/api/job/<job_id>/connected')
def get_connected_nodes(job_id):
    """API endpoint to get nodes connected to a specific URL."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job['status'] != 'completed' or not job['result']:
        return jsonify({'error': 'Job not completed'}), 400

    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400

    graph_nodes = job['result'].get('graph_nodes', [])
    graph_edges = job['result'].get('graph_edges', [])

    if url not in graph_nodes:
        return jsonify({'error': 'URL not found in graph'}), 404

    # Find connected nodes (both incoming and outgoing)
    connected = set([url])  # Include the selected node itself

    for source, target in graph_edges:
        if source == url:
            connected.add(target)  # Outgoing edges
        if target == url:
            connected.add(source)  # Incoming edges

    return jsonify({
        'selected_url': url,
        'connected_nodes': list(connected),
        'total_nodes': len(graph_nodes),
        'total_connected': len(connected)
    })


@app.route('/graph/<job_id>')
def graph_view(job_id):
    job = jobs.get(job_id)

    if not job:
        return "Job not found", 404

    if job['status'] != 'completed':
        return "Graph is not ready", 202

    graph_html = job['result'].get('graph_html')

    if not graph_html:
        return "Graph HTML is empty", 500

    return Response(graph_html, mimetype='text/html')

@app.route('/result/<job_id>')
def result(job_id):
    """Show results page."""
    job = jobs.get(job_id)
    if not job:
        return render_template('error.html', message='Job not found'), 404
    if job['status'] != 'completed':
        return redirect(url_for('job_status', job_id=job_id))
    return render_template('result.html', job=job)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)