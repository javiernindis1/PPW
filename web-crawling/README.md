# Web Crawler & PageRank Visualizer

A Flask web application that crawls websites, analyzes their internal link structure, computes PageRank scores, and visualizes the results as an interactive graph.

## Features

- **Web Crawling**: Enter any URL to crawl its internal pages (same domain only)
- **PageRank Analysis**: Computes PageRank scores for all crawled pages
- **Interactive Graph Visualization**: Uses pyvis to generate an interactive, zoomable/panable network graph
- **Top 10 Ranking Table**: Displays the top 10 pages by PageRank score
- **Real-time Progress**: Shows "Crawling in progress..." with polling updates
- **Clean UI**: Built with Bootstrap 5 for a responsive, modern interface

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your browser to http://localhost:5000

## Usage

1. Enter a website URL (e.g., `https://example.com`)
2. Adjust max pages and max depth if needed
3. Click "Start Crawling"
4. Wait for the crawl to complete (progress page auto-updates)
5. View the interactive graph and top 10 PageRank table

## Project Structure

```
web-crawling/
├── app.py              # Flask application
├── crawler_logic.py    # Crawling & PageRank logic
├── requirements.txt    # Python dependencies
├── templates/
│   ├── base.html       # Base template
│   ├── index.html      # Homepage with URL input
│   ├── job_status.html # Progress page with polling
│   ├── result.html     # Results page with graph & table
│   └── error.html      # Error page
└── README.md
```

## Dependencies

- **Flask** - Web framework
- **pyvis** - Interactive network visualization
- **networkx** - Graph algorithms (PageRank)
- **requests** - HTTP requests
- **beautifulsoup4** - HTML parsing

## Configuration

Environment variables:
- `SECRET_KEY` - Flask secret key (default: dev key)
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 5000)

## Notes

- The crawler only follows internal links (same domain as the start URL)
- Respects `robots.txt` is not implemented - use responsibly
- In-memory job storage (use Redis/database for production)
- SSL verification is disabled by default for compatibility