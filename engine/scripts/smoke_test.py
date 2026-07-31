from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
            media_type = "text/plain"
        else:
            body = b"""
                <html><body>
                  <article><h2>Smoke one</h2><a href="/one">Open</a><p>First body</p></article>
                  <article><h2>Smoke two</h2><a href="/two">Open</a><p>Second body</p></article>
                </body></html>
            """
            media_type = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def flow(url: str) -> dict[str, object]:
    return {
        "name": f"Smoke test {int(time.time())}",
        "description": "Disposable end-to-end engine verification",
        "max_items": 10,
        "timeout_seconds": 10,
        "nodes": [
            {"id": "start", "type": "start", "name": "Seeds", "config": {"urls": [url]}},
            {
                "id": "request",
                "type": "http_request",
                "name": "Fetch",
                "config": {"url": "{{url}}", "respect_robots": True},
            },
            {
                "id": "extract",
                "type": "html_extract",
                "name": "Extract",
                "config": {
                    "item_selector": "article",
                    "fields": {
                        "title": "h2",
                        "url": {"selector": "a", "attribute": "href"},
                        "content": "p",
                    },
                },
            },
            {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "request"},
            {"id": "e2", "source": "request", "target": "extract"},
            {"id": "e3", "source": "extract", "target": "emit"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    fixture_url = f"http://127.0.0.1:{fixture.server_port}/page"
    try:
        with httpx.Client(base_url=args.base_url, headers=headers, timeout=15) as client:
            health = client.get("/health")
            health.raise_for_status()
            created = client.post("/api/v1/flows", json=flow(fixture_url))
            created.raise_for_status()
            flow_id = created.json()["id"]
            queued = client.post(
                "/api/v1/runs",
                json={"flow_id": flow_id, "parameters": {}, "idempotency_key": f"smoke-{time.time_ns()}"},
            )
            queued.raise_for_status()
            run_id = queued.json()["id"]
            for _ in range(200):
                run = client.get(f"/api/v1/runs/{run_id}").json()
                if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("smoke run did not finish")
            if run["status"] != "SUCCEEDED":
                raise RuntimeError(f"smoke run failed: {run}")

            items = client.get(f"/api/v1/runs/{run_id}/items").json()["items"]
            events = client.get(f"/api/v1/runs/{run_id}/events").json()
            snapshot = client.get(f"/api/v1/runs/{run_id}/flow").json()
            resume_after = events[-2]["sequence"]
            resumed = client.get(
                f"/api/v1/runs/{run_id}/events/stream",
                headers={"Last-Event-ID": str(resume_after), **headers},
            )
            resumed.raise_for_status()
            if "event: run.completed" not in resumed.text:
                raise RuntimeError("SSE resume did not return the terminal event")
            if [item["title"] for item in items] != ["Smoke one", "Smoke two"]:
                raise RuntimeError(f"unexpected smoke items: {items}")
            print(
                json.dumps(
                    {
                        "health": health.json()["status"],
                        "flowId": flow_id,
                        "runId": run_id,
                        "flowRevision": snapshot["flow_revision"],
                        "status": run["status"],
                        "itemCount": len(items),
                        "eventCount": len(events),
                        "sseResume": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    finally:
        fixture.shutdown()
        fixture.server_close()


if __name__ == "__main__":
    main()
