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


def generate_graph_html(graph: nx.DiGraph, pagerank: dict) -> str:
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

    max_pr = max(pagerank.values()) if pagerank else 1

    # Add nodes
    for node in graph.nodes():
        pr = pagerank.get(node, 0)

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
            title=f"{node}\nPageRank: {pr:.6f}",
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

    if marker in html:
        html = html.replace(
            marker,
            marker + freeze_script,
            1
        )

    return html



def run_crawl(job_id: str, start_url: str, max_pages: int, max_depth: int):
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
            unique_domains=False
        )

        # Generate graph HTML
        graph_html = generate_graph_html(result['graph'], result['pagerank'])

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result'] = {
            'graph_html': graph_html,
            'top_10': result['top_10'],
            'pages_crawled': result['stats']['visited_pages'],
            'errors': result['errors']
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
    max_pages = int(request.form.get('max_pages', 50))
    max_depth = int(request.form.get('max_depth', 3))

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
    thread = threading.Thread(target=run_crawl, args=(job_id, start_url, max_pages, max_depth))
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