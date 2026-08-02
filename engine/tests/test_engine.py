import asyncio
import json
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from siftlane_engine.engine import FlowEngine
from siftlane_engine.models import FlowNode


def test_decode_json_payload_accepts_json():
    assert FlowEngine._decode_json_payload('{"items": [1, 2]}') == {
        "items": [1, 2]
    }


def test_decode_json_payload_accepts_jsonp():
    assert FlowEngine._decode_json_payload(
        'china({"data": {"list": [{"title": "News"}]}});'
    ) == {"data": {"list": [{"title": "News"}]}}


@pytest.mark.parametrize(
    "body",
    [
        'alert(1); callback({"items": []})',
        'callback({"items": []}); cleanup()',
        'callback({items: []})',
    ],
)
def test_decode_json_payload_rejects_scripts_and_non_json(body):
    with pytest.raises(json.JSONDecodeError):
        FlowEngine._decode_json_payload(body)


def test_extract_html_field_can_join_multiple_matches():
    scope = BeautifulSoup(
        "<main><p>First paragraph.</p><p>Second paragraph.</p></main>",
        "html.parser",
    )

    assert FlowEngine._extract_html_field(
        scope,
        {
            "selector": "main p",
            "attribute": "text",
            "all": True,
            "separator": "\n\n",
        },
    ) == "First paragraph.\n\nSecond paragraph."


def test_extract_html_field_can_parse_embedded_script_html():
    scope = BeautifulSoup(
        """
        <main>
          <script>
            var contentdate = '<p>First paragraph.</p><p>Second paragraph.<\\/p>';
          </script>
        </main>
        """,
        "html.parser",
    )

    assert FlowEngine._extract_html_field(
        scope,
        {
            "script_variable": "contentdate",
            "selector": "p",
            "attribute": "text",
            "all": True,
            "separator": "\n\n",
        },
    ) == "First paragraph.\n\nSecond paragraph."


def test_extract_html_field_can_read_json_ld_path():
    scope = BeautifulSoup(
        """
        <script type="application/ld+json">
          {"@graph": [{"author": {"name": "Ada Reporter"}}]}
        </script>
        """,
        "html.parser",
    )

    assert FlowEngine._extract_html_field(
        scope,
        {
            "selector": "script[type='application/ld+json']",
            "attribute": "json",
            "path": "@graph.0.author.name",
        },
    ) == "Ada Reporter"


def test_html_extract_can_deduplicate_resolved_urls():
    node = FlowNode(
        id="extract",
        type="html_extract",
        name="Extract links",
        config={
            "item_selector": "a",
            "deduplicate_by": "url",
            "fields": {"url": {"selector": "", "attribute": "href"}},
        },
    )
    context = SimpleNamespace(flow=SimpleNamespace(max_items=10))
    engine = FlowEngine.__new__(FlowEngine)

    outputs = engine._html_extract(
        node,
        [
            {"url": "https://example.test/list", "body": '<a href="/one">One</a>'},
            {"url": "https://example.test/other", "body": '<a href="/one">Duplicate</a>'},
        ],
        context,
    )

    assert outputs == [{"url": "https://example.test/one"}]


def test_render_template_value_resolves_nested_metadata():
    assert FlowEngine._render_template_value(
        {
            "source": "{{source}}",
            "article": {"author": "{{author}}"},
            "labels": ["detail", "{{kind}}"],
        },
        {"source": "Fixture News", "author": "Ada", "kind": "report"},
    ) == {
        "source": "Fixture News",
        "article": {"author": "Ada"},
        "labels": ["detail", "report"],
    }


@pytest.mark.asyncio
async def test_request_can_fallback_and_skip_failed_items():
    class FakeResponse:
        status = 200
        media_type = "text/html"
        headers = {}

        def __init__(self, url: str):
            self.url = url

        def text(self):
            return "<main>ok</main>"

    class FakeHttp:
        async def fetch(self, url, **_):
            if url == "https://example.test/article":
                raise RuntimeError("TLS failed")
            if url.endswith("/missing"):
                raise RuntimeError("not reachable")
            return FakeResponse(url)

    events = []

    async def event(*args):
        events.append(args)

    context = SimpleNamespace(
        flow=SimpleNamespace(max_items=10),
        http=FakeHttp(),
        cancelled=asyncio.Event(),
        event=event,
    )
    node = FlowNode(
        id="request",
        type="http_request",
        name="Fetch details",
        config={
            "url": "{{url}}",
            "respect_robots": True,
            "continue_on_error": True,
            "fallback_to_http": True,
        },
        retry={
            "max_attempts": 2,
            "backoff_seconds": 0,
            "max_backoff_seconds": 0,
            "retryable_errors": ["RuntimeError"],
        },
    )

    engine = FlowEngine.__new__(FlowEngine)
    outputs = await engine._request(
        node,
        [
            {"url": "https://example.test/article"},
            {"url": "https://example.test/missing"},
        ],
        context,
    )

    assert [item["url"] for item in outputs] == ["http://example.test/article"]
    assert [entry[0] for entry in events] == [
        "request.fallback",
        "request.retrying",
        "request.skipped",
    ]


@pytest.mark.asyncio
async def test_emit_can_skip_items_without_extracted_content():
    class FakeStorage:
        def __init__(self):
            self.contents = []

        async def count_items(self, _):
            return 0

        async def add_item(self, *args):
            self.contents.append(args[4])
            return SimpleNamespace(), True

    events = []

    async def event(*args):
        events.append(args)

    async def progress(*_):
        return None

    storage = FakeStorage()
    context = SimpleNamespace(
        run_id="run-1",
        flow=SimpleNamespace(id="flow-1", name="Detail flow", max_items=10),
        storage=storage,
        cancelled=asyncio.Event(),
        event=event,
        progress=progress,
    )
    node = FlowNode(
        id="emit",
        type="emit",
        name="Emit complete articles",
        config={"skip_empty_content": True},
    )

    engine = FlowEngine.__new__(FlowEngine)
    emitted = await engine._emit(
        node,
        [
            {"url": "https://example.test/empty", "title": "Empty", "content": ""},
            {"url": "https://example.test/full", "title": "Full", "content": "Body"},
        ],
        context,
    )

    assert emitted == 1
    assert storage.contents == ["Body"]
    assert events[0][0] == "item.skipped"
