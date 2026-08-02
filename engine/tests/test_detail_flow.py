from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from siftlane_engine.api import create_app
from siftlane_engine.config import Settings


class DetailFixtureHandler(BaseHTTPRequestHandler):
    requested_paths: list[str] = []

    def do_GET(self):
        self.__class__.requested_paths.append(self.path)
        if self.path == "/robots.txt":
            content_type = "text/plain"
            body = b"User-agent: *\nAllow: /\n"
        elif self.path == "/listing":
            content_type = "text/html"
            body = b"""
                <article><a href="/stories/one">Listing title one</a></article>
                <article><a href="/stories/two">Listing title two</a></article>
            """
        elif self.path == "/stories/one":
            content_type = "text/html"
            body = b"""
                <html><body>
                  <h1>Detail title one</h1>
                  <span class="author">Ada Reporter</span>
                  <time>2026-08-02T09:30:00Z</time>
                  <main><p>First paragraph.</p><p>Second paragraph.</p></main>
                </body></html>
            """
        elif self.path == "/stories/two":
            content_type = "text/html"
            body = b"""
                <html><body>
                  <h1>Detail title two</h1>
                  <span class="author">Lin Editor</span>
                  <time>2026-08-02T10:15:00Z</time>
                  <main><p>Third paragraph.</p><p>Fourth paragraph.</p></main>
                </body></html>
            """
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


def detail_flow(base_url: str) -> dict:
    return {
        "name": "Detail flow fixture",
        "max_items": 10,
        "timeout_seconds": 60,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start",
                "config": {"urls": [f"{base_url}/listing"]},
            },
            {
                "id": "list_request",
                "type": "http_request",
                "name": "Fetch listing",
                "config": {"url": "{{url}}", "respect_robots": True},
            },
            {
                "id": "link_extract",
                "type": "html_extract",
                "name": "Extract links",
                "config": {
                    "item_selector": "article a",
                    "fields": {
                        "title": {"selector": "", "attribute": "text"},
                        "url": {"selector": "", "attribute": "href"},
                    },
                },
            },
            {
                "id": "detail_request",
                "type": "http_request",
                "name": "Fetch detail",
                "config": {"url": "{{url}}", "respect_robots": True},
            },
            {
                "id": "detail_extract",
                "type": "html_extract",
                "name": "Extract detail",
                "config": {
                    "item_selector": "body",
                    "fields": {
                        "detail_title": "h1",
                        "content": {
                            "selector": "main p",
                            "attribute": "text",
                            "all": True,
                            "separator": "\n\n",
                        },
                        "author": ".author",
                        "published_at": "time",
                    },
                },
            },
            {
                "id": "emit",
                "type": "emit",
                "name": "Emit",
                "config": {
                    "fields": {
                        "title": "{{detail_title}}",
                        "external_id": "{{url}}",
                        "metadata": {
                            "source": "Fixture News",
                            "author": "{{author}}",
                            "publishedAt": "{{published_at}}",
                        },
                    }
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "list_request"},
            {"id": "e2", "source": "list_request", "target": "link_extract"},
            {"id": "e3", "source": "link_extract", "target": "detail_request"},
            {"id": "e4", "source": "detail_request", "target": "detail_extract"},
            {"id": "e5", "source": "detail_extract", "target": "emit"},
        ],
    }


def test_list_to_detail_flow_persists_full_article_and_metadata(tmp_path):
    DetailFixtureHandler.requested_paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), DetailFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    settings = Settings(
        data_dir=tmp_path,
        allow_private_networks=True,
        request_min_delay_seconds=0,
        worker_count=1,
    )
    try:
        with TestClient(create_app(settings)) as client:
            flow = client.post("/api/v1/flows", json=detail_flow(base_url))
            assert flow.status_code == 201, flow.text
            run = client.post("/api/v1/runs", json={"flow_id": flow.json()["id"]})
            assert run.status_code == 202, run.text
            run_id = run.json()["id"]
            for _ in range(1_000):
                record = client.get(f"/api/v1/runs/{run_id}").json()
                if record["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.03)
            assert record["status"] == "SUCCEEDED", json.dumps(record, indent=2)
            items = client.get(f"/api/v1/runs/{run_id}/items").json()["items"]
            assert len(items) == 2
            by_title = {item["title"]: item for item in items}
            first = by_title["Detail title one"]
            second = by_title["Detail title two"]
            assert first["content"] == "First paragraph.\n\nSecond paragraph."
            assert first["external_id"] == f"{base_url}/stories/one"
            assert first["metadata"]["author"] == "Ada Reporter"
            assert first["metadata"]["publishedAt"] == "2026-08-02T09:30:00Z"
            assert second["content"] == "Third paragraph.\n\nFourth paragraph."
            assert second["metadata"]["author"] == "Lin Editor"
            assert second["metadata"]["publishedAt"] == "2026-08-02T10:15:00Z"
            assert "/listing" in DetailFixtureHandler.requested_paths
            assert "/stories/one" in DetailFixtureHandler.requested_paths
            assert "/stories/two" in DetailFixtureHandler.requested_paths
    finally:
        server.shutdown()
        server.server_close()
