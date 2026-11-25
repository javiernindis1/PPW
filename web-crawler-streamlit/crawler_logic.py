
import time
from collections import deque
from urllib.parse import urlparse, urljoin

import requests
import networkx as nx
from bs4 import BeautifulSoup


def normalize_url(url):
    """
    Normalisasi URL menjadi root domain.
    Contoh:
    https://example.com/image -> https://example.com/
    https://www.example.com/info -> https://example.com/
    """
    try:
        parsed = urlparse(url.strip())

        if not parsed.scheme:
            parsed = urlparse("https://" + url.strip())

        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None

        domain = parsed.hostname.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return f"https://{domain}/"

    except Exception:
        return None


def get_domain(url):
    parsed = urlparse(url)
    domain = (parsed.hostname or "").lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


class WebCrawler:

    def __init__(
        self,
        start_url,
        max_depth=2,
        max_pages=50,
        timeout=15,
        delay=0.3
    ):
        self.start_url = normalize_url(start_url)

        if not self.start_url:
            raise ValueError("URL awal tidak valid.")

        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay

        self.graph = nx.DiGraph()

        self.visited = set()
        self.queued = set()
        self.crawled_urls = []
        self.errors = []

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
            )
        })

    def fetch_page(self, url):

        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True
            )

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "html" not in content_type:
                return None, None

            final_url = normalize_url(response.url)

            return response.text, final_url

        except requests.exceptions.Timeout:
            error = "Connection timeout"

        except requests.exceptions.SSLError:
            error = "SSL certificate error"

        except requests.exceptions.HTTPError as e:
            error = str(e)

        except requests.exceptions.ConnectionError:
            error = "Connection error"

        except requests.exceptions.RequestException as e:
            error = str(e)

        self.errors.append({
            "url": url,
            "error": error
        })

        return None, None

    def extract_links(self, html, base_url):

        links = set()

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all("a", href=True):

            href = tag.get("href", "").strip()

            if not href:
                continue

            if href.startswith((
                "mailto:",
                "tel:",
                "javascript:",
                "#"
            )):
                continue

            absolute_url = urljoin(base_url, href)

            normalized = normalize_url(absolute_url)

            if normalized:
                links.add(normalized)

        return links

    def crawl(self, progress_callback=None):

        queue = deque([
            (self.start_url, 0)
        ])

        self.queued.add(get_domain(self.start_url))

        while queue and len(self.crawled_urls) < self.max_pages:

            current_url, depth = queue.popleft()

            current_domain = get_domain(current_url)

            if current_domain in self.visited:
                continue

            if depth > self.max_depth:
                continue

            self.visited.add(current_domain)

            html, final_url = self.fetch_page(current_url)

            if not html or not final_url:
                continue

            final_domain = get_domain(final_url)

            if final_domain in self.graph:
                continue

            self.visited.add(final_domain)

            self.graph.add_node(final_url)

            self.crawled_urls.append(final_url)

            links = self.extract_links(
                html,
                final_url
            )

            for target_url in links:

                target_domain = get_domain(target_url)

                # Tidak membuat self-loop.
                if target_domain == final_domain:
                    continue

                # Simpan hubungan antar-domain.
                self.graph.add_edge(
                    final_url,
                    target_url
                )

                # Cegah crawling domain yang sama.
                if (
                    depth < self.max_depth
                    and target_domain not in self.visited
                    and target_domain not in self.queued
                    and len(self.crawled_urls) + len(queue)
                    < self.max_pages
                ):

                    queue.append((
                        target_url,
                        depth + 1
                    ))

                    self.queued.add(target_domain)

            if progress_callback:
                progress_callback(
                    len(self.crawled_urls),
                    self.max_pages,
                    final_url
                )

            time.sleep(self.delay)

        return self.graph

    def calculate_pagerank(self):

        if self.graph.number_of_nodes() == 0:
            return {}

        return nx.pagerank(
            self.graph,
            alpha=0.85,
            max_iter=100
        )

    def get_rankings(self, pagerank):

        rankings = []

        for node in self.graph.nodes():

            rankings.append({
                "url": node,
                "inlinks": self.graph.in_degree(node),
                "outlinks": self.graph.out_degree(node),
                "pagerank": pagerank.get(node, 0)
            })

        # Ranking utama berdasarkan In-Degree.
        # Jika sama, gunakan PageRank.
        rankings.sort(
            key=lambda x: (
                x["inlinks"],
                x["pagerank"]
            ),
            reverse=True
        )

        for index, item in enumerate(rankings, start=1):
            item["rank"] = index

        return rankings


def crawl_and_analyze(
    start_url,
    max_depth=2,
    max_pages=50,
    timeout=15,
    delay=0.3,
    progress_callback=None
):

    crawler = WebCrawler(
        start_url=start_url,
        max_depth=max_depth,
        max_pages=max_pages,
        timeout=timeout,
        delay=delay
    )

    graph = crawler.crawl(
        progress_callback=progress_callback
    )

    pagerank = crawler.calculate_pagerank()

    rankings = crawler.get_rankings(pagerank)

    return {
        "start_url": crawler.start_url,
        "graph": graph,
        "pagerank": pagerank,
        "rankings": rankings,
        "crawled_urls": crawler.crawled_urls,
        "errors": crawler.errors,
        "stats": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "density": nx.density(graph)
            if graph.number_of_nodes() > 1 else 0,
            "visited": len(crawler.crawled_urls)
        }
    }
