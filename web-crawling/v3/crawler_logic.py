"""
Web Crawler with PageRank Analysis

This module provides functionality to crawl websites, build a directed graph of URLs,
calculate PageRank scores, and save results in JSON format for web app consumption.
"""

import json
import pickle
import time
from collections import defaultdict
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Set, Tuple, Optional
import warnings

import requests
from bs4 import BeautifulSoup
import networkx as nx

# Suppress SSL warnings for invalid certificates
warnings.filterwarnings("ignore", message="Unverified HTTPS request")


class WebCrawler:
    """A web crawler that builds a directed graph and computes PageRank."""

    def __init__(
        self,
        start_url: str,
        max_depth: int = 2,
        max_pages: int = 100,
        timeout: int = 10,
        delay: float = 1.0,
        verify_ssl: bool = False,
        unique_domains: bool = True
    ):
        """
        Initialize the web crawler.

        Args:
            start_url: The starting URL for crawling
            max_depth: Maximum depth to crawl (default: 2)
            max_pages: Maximum number of pages to crawl (default: 100)
            timeout: Request timeout in seconds (default: 10)
            delay: Delay between requests in seconds (default: 1.0)
            verify_ssl: Whether to verify SSL certificates (default: False)
            unique_domains: Whether to filter for unique domains (default: True)
        """
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.verify_ssl = verify_ssl
        self.unique_domains = unique_domains

        self.visited: Set[str] = set()
        self.graph = nx.DiGraph()
        self.errors: List[Dict] = []
        self.domain_cache: Dict[str, str] = {}

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if url in self.domain_cache:
            return self.domain_cache[url]
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        self.domain_cache[url] = domain
        return domain

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and absolute."""
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme) and bool(parsed.netloc)
        except Exception:
            return False

    def _normalize_url(self, url: str, base_url: str) -> Optional[str]:
        """Normalize URL by joining with base and removing fragments."""
        try:
            full_url = urljoin(base_url, url)
            parsed = urlparse(full_url)
            # Remove fragment
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized
        except Exception:
            return None

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all links from HTML content."""
        links = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                normalized = self._normalize_url(href, base_url)
                if normalized and self._is_valid_url(normalized):
                    links.append(normalized)
        except Exception as e:
            self.errors.append({
                'url': base_url,
                'error': f"Link extraction failed: {str(e)}"
            })
        return links

    
    def _fetch_page(self, url: str):
        """Fetch a page and return its HTML and final URL."""
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
                )
            }

            response = requests.get(
                url,
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=headers,
                allow_redirects=True
            )

            response.raise_for_status()
            return response.text, response.url

        except requests.exceptions.Timeout:
            self.errors.append({'url': url, 'error': 'Connection timeout'})
        except requests.exceptions.SSLError:
            self.errors.append({'url': url, 'error': 'SSL certificate error'})
        except requests.exceptions.ConnectionError:
            self.errors.append({'url': url, 'error': 'Connection error'})
        except requests.exceptions.HTTPError as e:
            self.errors.append({
                'url': url,
                'error': f'HTTP error: {e.response.status_code}'
            })
        except Exception as e:
            self.errors.append({
                'url': url,
                'error': f'Unexpected error: {str(e)}'
            })

        return None, None

    def crawl(self, progress_callback=None) -> nx.DiGraph:
        """Crawl pages and optionally publish graph snapshots as pages are processed."""

        queue = [(self.start_url, 0)]
        queued = {self.start_url}

        start_host = urlparse(self.start_url).netloc.lower()

        while queue and len(self.visited) < self.max_pages:
            requested_url, depth = queue.pop(0)

            if depth > self.max_depth:
                continue

            if requested_url in self.visited:
                continue

            html, final_url = self._fetch_page(requested_url)

            if html is None or final_url is None:
                self.visited.add(requested_url)
                if progress_callback:
                    progress_callback(self.graph, len(self.visited), self.max_pages, requested_url)
                continue

            current_url = self._normalize_url(final_url, final_url)

            if current_url is None or current_url in self.visited:
                if progress_callback:
                    progress_callback(self.graph, len(self.visited), self.max_pages, requested_url)
                continue

            self.visited.add(current_url)
            self.graph.add_node(current_url)

            links = self._extract_links(html, final_url)

            for link in links:
                parsed = urlparse(link)

                if parsed.scheme not in ('http', 'https'):
                    continue

                if self.unique_domains:
                    if parsed.netloc.lower() != start_host:
                        continue

                if link == current_url:
                    continue

                self.graph.add_edge(current_url, link)

                if (
                    link not in self.visited
                    and link not in queued
                    and depth < self.max_depth
                    and len(self.visited) + len(queue) < self.max_pages
                ):
                    queue.append((link, depth + 1))
                    queued.add(link)

            # Publish the current graph after this page and its outgoing links are processed.
            if progress_callback:
                progress_callback(self.graph, len(self.visited), self.max_pages, current_url)

            time.sleep(self.delay)

        return self.graph


    def calculate_pagerank(self, alpha: float = 0.85, max_iter: int = 100) -> Dict[str, float]:
        """
        Calculate PageRank for all nodes in the graph.

        Args:
            alpha: Damping factor (default: 0.85)
            max_iter: Maximum iterations (default: 100)

        Returns:
            Dictionary mapping URLs to PageRank scores
        """
        if self.graph.number_of_nodes() == 0:
            return {}

        try:
            pagerank = nx.pagerank(self.graph, alpha=alpha, max_iter=max_iter)
            return pagerank
        except Exception as e:
            self.errors.append({'error': f'PageRank calculation failed: {str(e)}'})
            return {}

    def get_top_pagerank(self, n: int = 10) -> List[Tuple[str, float]]:
        """
        Get top N URLs by PageRank score.

        Args:
            n: Number of top URLs to return (default: 10)

        Returns:
            List of (url, pagerank) tuples sorted by PageRank descending
        """
        pagerank = self.calculate_pagerank()
        sorted_pr = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
        return sorted_pr[:n]

    def get_graph_stats(self) -> Dict:
        """Get statistics about the crawled graph."""
        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'density': nx.density(self.graph) if self.graph.number_of_nodes() > 0 else 0,
            'visited_pages': len(self.visited),
            'errors': len(self.errors)
        }

    def save_json(self, filepath: str) -> None:
        """Save graph and PageRank results to JSON file."""
        pagerank = self.calculate_pagerank()
        top_10 = self.get_top_pagerank(10)
        stats = self.get_graph_stats()

        # Convert graph to node-link format
        graph_data = nx.node_link_data(self.graph)

        data = {
            'start_url': self.start_url,
            'max_depth': self.max_depth,
            'max_pages': self.max_pages,
            'graph': graph_data,
            'pagerank': pagerank,
            'top_10': [{'url': url, 'pagerank': score} for url, score in top_10],
            'stats': stats,
            'errors': self.errors
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_pickle(self, filepath: str) -> None:
        """Save graph and PageRank results to pickle file."""
        pagerank = self.calculate_pagerank()
        top_10 = self.get_top_pagerank(10)
        stats = self.get_graph_stats()

        data = {
            'start_url': self.start_url,
            'max_depth': self.max_depth,
            'max_pages': self.max_pages,
            'graph': self.graph,
            'pagerank': pagerank,
            'top_10': top_10,
            'stats': stats,
            'errors': self.errors
        }

        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def load_json(self, filepath: str) -> Dict:
        """Load results from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Reconstruct graph
        self.graph = nx.node_link_graph(data['graph'])
        return data

    def load_pickle(self, filepath: str) -> Dict:
        """Load results from pickle file."""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        self.graph = data['graph']
        return data


def crawl_and_analyze(
    start_url: str,
    max_depth: int = 2,
    max_pages: int = 100,
    timeout: int = 10,
    delay: float = 1.0,
    verify_ssl: bool = False,
    unique_domains: bool = True,
    output_json: Optional[str] = None,
    output_pickle: Optional[str] = None,
    progress_callback=None
) -> Dict:
    """
    Convenience function to crawl a website and analyze PageRank.

    Args:
        start_url: Starting URL for crawling
        max_depth: Maximum crawl depth (default: 2)
        max_pages: Maximum pages to crawl (default: 100)
        timeout: Request timeout (default: 10)
        delay: Delay between requests (default: 1.0)
        verify_ssl: Verify SSL certificates (default: False)
        unique_domains: Filter for same domain (default: True)
        output_json: Path to save JSON output (optional)
        output_pickle: Path to save pickle output (optional)

    Returns:
        Dictionary with graph, PageRank, stats, and errors
    """
    crawler = WebCrawler(
        start_url=start_url,
        max_depth=max_depth,
        max_pages=max_pages,
        timeout=timeout,
        delay=delay,
        verify_ssl=verify_ssl,
        unique_domains=unique_domains
    )

    crawler.crawl(progress_callback=progress_callback)

    result = {
        'graph': crawler.graph,
        'pagerank': crawler.calculate_pagerank(),
        'top_10': crawler.get_top_pagerank(10),
        'stats': crawler.get_graph_stats(),
        'errors': crawler.errors
    }

    if output_json:
        crawler.save_json(output_json)

    if output_pickle:
        crawler.save_pickle(output_pickle)

    return result


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = 'https://example.com'

    print(f"Crawling: {url}")
    result = crawl_and_analyze(
        start_url=url,
        max_depth=2,
        max_pages=50,
        output_json='crawl_results.json',
        output_pickle='crawl_results.pkl'
    )

    print(f"\nGraph Stats: {result['stats']}")
    print("\nTop 10 PageRank:")
    for i, (url, score) in enumerate(result['top_10'], 1):
        print(f"  {i}. {url}: {score:.6f}")

    if result['errors']:
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result['errors'][:5]:
            print(f"  - {err}")