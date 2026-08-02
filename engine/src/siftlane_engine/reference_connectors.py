from __future__ import annotations

import json
from datetime import datetime, timezone

from siftlane_connector_sdk import (
    ConnectorCapability,
    ConnectorContext,
    ConnectorHttpRequest,
    ConnectorItem,
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
    ConnectorRuntime,
    RuntimeRequirements,
)


class JsonFeedConnector(ConnectorRuntime):
    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            id="io.siftlane.json-feed",
            name="JSON Feed",
            version="1.0.0",
            description="Collects items from a JSON Feed 1.0 or 1.1 endpoint.",
            capabilities=[
                ConnectorCapability(
                    id="fetch",
                    label="Fetch feed",
                    description="Fetch and normalize one page of a JSON Feed.",
                    input_schema={
                        "type": "object",
                        "properties": {"url": {"type": "string", "minLength": 1}},
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                    supports_cursor=True,
                )
            ],
            runtime=RuntimeRequirements(allowed_domains=[]),
        )

    async def execute(
        self,
        request: ConnectorOperationRequest,
        context: ConnectorContext,
    ) -> ConnectorOperationResult:
        if request.capability != "fetch":
            raise ValueError(f"unsupported capability: {request.capability}")
        url = request.cursor or request.parameters.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("fetch requires a URL")
        response = await context.http.request(ConnectorHttpRequest(url=url))
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"JSON Feed returned HTTP {response.status}")
        try:
            document = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("JSON Feed response is not valid UTF-8 JSON") from error
        if not isinstance(document, dict) or not isinstance(document.get("items"), list):
            raise ValueError("JSON Feed response must contain an items array")

        normalized: list[ConnectorItem] = []
        for raw in document["items"][: request.limit]:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                continue
            item_url = raw.get("url") or raw.get("external_url") or url
            published = raw.get("date_published") or raw.get("date_modified")
            try:
                observed_at = (
                    datetime.fromisoformat(published.replace("Z", "+00:00"))
                    if isinstance(published, str)
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                observed_at = datetime.now(timezone.utc)
            normalized.append(
                ConnectorItem(
                    external_id=raw["id"],
                    url=str(item_url),
                    title=str(raw.get("title") or raw.get("summary") or ""),
                    content=str(raw.get("content_text") or raw.get("content_html") or ""),
                    media_type="application/json-feed+json",
                    observed_at=observed_at,
                    metadata={"authors": raw.get("authors", []), "tags": raw.get("tags", [])},
                )
            )
        next_url = document.get("next_url")
        return ConnectorOperationResult(
            items=normalized,
            next_cursor=next_url if isinstance(next_url, str) else None,
            metadata={"feedTitle": document.get("title", ""), "sourceUrl": url},
        )


BUILTIN_CONNECTORS: dict[str, type[ConnectorRuntime]] = {
    "builtin.json-feed": JsonFeedConnector,
}


def load_builtin(name: str) -> ConnectorRuntime:
    connector = BUILTIN_CONNECTORS.get(name)
    if connector is None:
        raise RuntimeError(f"built-in connector {name!r} was not found")
    return connector()
