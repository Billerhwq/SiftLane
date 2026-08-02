from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .models import (
    NODE_CONFIG_SCHEMAS,
    FlowNode,
    FlowRecord,
    NodeCapability,
    NodeType,
    utc_now,
)
from .security import SecureHttpClient
from .storage import Storage


EventWriter = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]
ProgressWriter = Callable[[str, str, int], Awaitable[None]]


@dataclass
class ExecutionContext:
    run_id: str
    flow: FlowRecord
    parameters: dict[str, Any]
    storage: Storage
    http: SecureHttpClient
    cancelled: asyncio.Event
    event: EventWriter
    progress: ProgressWriter


class FlowEngine:
    def __init__(self, storage: Storage, http: SecureHttpClient):
        self.storage = storage
        self.http = http

    async def execute(
        self,
        run_id: str,
        flow: FlowRecord,
        parameters: dict[str, Any],
        cancelled: asyncio.Event,
        event: EventWriter,
        progress: ProgressWriter,
    ) -> int:
        context = ExecutionContext(
            run_id=run_id,
            flow=flow,
            parameters=parameters,
            storage=self.storage,
            http=self.http,
            cancelled=cancelled,
            event=event,
            progress=progress,
        )
        nodes = {node.id: node for node in flow.nodes}
        incoming = {node.id: [] for node in flow.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in flow.nodes}
        indegree = {node.id: 0 for node in flow.nodes}
        for edge in flow.edges:
            incoming[edge.target].append(edge)
            outgoing[edge.source].append(edge.target)
            indegree[edge.target] += 1

        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for target in outgoing[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)

        outputs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        checkpoints = await context.storage.load_checkpoints(run_id)
        for index, node_id in enumerate(ordered):
            self._check_cancelled(context)
            node = nodes[node_id]
            checkpoint = checkpoints.get(node_id)
            if checkpoint is not None:
                for port, items in checkpoint.outputs.items():
                    outputs[(node_id, port)] = items[: flow.max_items]
                item_count = await context.storage.count_items(run_id)
                await progress(node.id, f"Restored {node.name} from checkpoint", item_count)
                await event(
                    "node.restored",
                    "info",
                    f"Restored node: {node.name}",
                    {
                        "nodeId": node.id,
                        "nodeType": node.type.value,
                        "outputCount": sum(len(items) for items in checkpoint.outputs.values()),
                        "attemptCount": checkpoint.attempt_count,
                    },
                )
                continue

            item_count = await context.storage.count_items(run_id)
            await progress(node.id, f"Executing {node.name}", item_count)
            await event(
                "node.started",
                "info",
                f"Executing node: {node.name}",
                {"nodeId": node.id, "nodeType": node.type.value, "index": index},
            )
            node_inputs: list[dict[str, Any]] = []
            for edge in incoming[node_id]:
                node_inputs.extend(outputs.get((edge.source, edge.source_port), []))
            if node.type == NodeType.START:
                node_inputs = [dict(context.parameters)]
            node_outputs, added, attempts = await self._execute_with_retry(
                node, node_inputs, context
            )
            bounded_outputs = {
                port: values[: flow.max_items] for port, values in node_outputs.items()
            }
            for port, values in bounded_outputs.items():
                outputs[(node_id, port)] = values
            await context.storage.save_checkpoint(
                run_id,
                node.id,
                bounded_outputs,
                attempt_count=attempts,
                emitted_count=added,
            )
            item_count = await context.storage.count_items(run_id)
            await event(
                "node.completed",
                "info",
                f"Completed node: {node.name}",
                {
                    "nodeId": node.id,
                    "outputCount": sum(len(values) for values in bounded_outputs.values()),
                    "emittedItems": item_count,
                    "attemptCount": attempts,
                },
            )
        return await context.storage.count_items(run_id)

    async def _execute_with_retry(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
        policy = node.retry
        for attempt in range(1, policy.max_attempts + 1):
            self._check_cancelled(context)
            try:
                outputs, emitted = await self._execute_node(node, inputs, context)
                return outputs, emitted, attempt
            except RunCancelled:
                raise
            except Exception as error:
                if attempt >= policy.max_attempts or not self._should_retry(error, node):
                    raise
                delay = min(
                    policy.backoff_seconds * (2 ** (attempt - 1)),
                    policy.max_backoff_seconds,
                )
                await context.event(
                    "node.retrying",
                    "warning",
                    f"Retrying node {node.name} after attempt {attempt}",
                    {
                        "nodeId": node.id,
                        "attempt": attempt,
                        "nextAttempt": attempt + 1,
                        "delaySeconds": delay,
                        "errorType": type(error).__name__,
                        "error": str(error)[:500],
                    },
                )
                if delay:
                    try:
                        await asyncio.wait_for(context.cancelled.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                    self._check_cancelled(context)
        raise RuntimeError("retry loop exhausted unexpectedly")

    @staticmethod
    def _should_retry(error: Exception, node: FlowNode) -> bool:
        if isinstance(error, HttpStatusError):
            return error.status in node.retry.retryable_statuses
        names = {klass.__name__ for klass in type(error).mro()}
        return bool(names.intersection(node.retry.retryable_errors))

    async def _execute_node(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> tuple[dict[str, list[dict[str, Any]]], int]:
        if node.type == NodeType.START:
            return {"default": self._start(node, context)}, 0
        if node.type == NodeType.HTTP_REQUEST:
            return {"default": await self._request(node, inputs, context)}, 0
        if node.type == NodeType.HTML_EXTRACT:
            return {"default": self._html_extract(node, inputs, context)}, 0
        if node.type == NodeType.JSON_EXTRACT:
            return {"default": self._json_extract(node, inputs, context)}, 0
        if node.type == NodeType.CONDITION:
            return self._condition(node, inputs), 0
        if node.type == NodeType.LOOP:
            return {"default": self._loop(node, inputs, context)}, 0
        if node.type == NodeType.PAGINATION:
            return {"default": self._pagination(node, inputs, context)}, 0
        if node.type == NodeType.TRANSFORM:
            return {"default": self._transform(node, inputs, context)}, 0
        if node.type == NodeType.EMIT:
            emitted = await self._emit(node, inputs, context)
            return {"default": inputs}, emitted
        raise ValueError(f"unsupported node type: {node.type}")

    def _start(self, node: FlowNode, context: ExecutionContext) -> list[dict[str, Any]]:
        configured = node.config.get("urls", [])
        urls = context.parameters.get("seed_urls", configured)
        if isinstance(urls, str):
            urls = [line.strip() for line in urls.splitlines() if line.strip()]
        if not isinstance(urls, list) or not urls:
            raise ValueError("start node requires at least one URL")
        return [
            {**context.parameters, "url": str(url), "seed_url": str(url)}
            for url in urls[: context.flow.max_items]
        ]

    async def _request(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        url_template = str(node.config.get("url", "{{url}}"))
        raw_headers = node.config.get("headers", {})
        if not isinstance(raw_headers, dict):
            raise ValueError("request headers must be an object")
        headers = {
            str(name): self._resolve_secret(str(value))
            for name, value in raw_headers.items()
        }
        respect_robots = bool(node.config.get("respect_robots", True))
        continue_on_error = bool(node.config.get("continue_on_error", False))
        fallback_to_http = bool(node.config.get("fallback_to_http", False))
        force_http = bool(node.config.get("force_http", False))
        request_timeout = float(node.config.get("timeout_seconds", 0)) or None
        for item in inputs[: context.flow.max_items]:
            self._check_cancelled(context)
            url = self._template(url_template, item)
            if force_http:
                url = self._http_fallback_url(url) or url
            response = None
            error: Exception | None = None
            attempt_limit = node.retry.max_attempts if continue_on_error else 1
            for attempt in range(1, attempt_limit + 1):
                try:
                    response = await self._fetch_with_fallback(
                        node,
                        context,
                        url,
                        headers=headers,
                        respect_robots=respect_robots,
                        fallback_to_http=fallback_to_http,
                        timeout_seconds=request_timeout,
                    )
                    error = None
                    break
                except Exception as attempt_error:
                    error = attempt_error
                    should_retry = (
                        attempt < attempt_limit and self._should_retry(error, node)
                    )
                    if not should_retry:
                        break
                    delay = min(
                        node.retry.backoff_seconds * (2 ** (attempt - 1)),
                        node.retry.max_backoff_seconds,
                    )
                    await context.event(
                        "request.retrying",
                        "warning",
                        f"Retrying failed request: {url}",
                        {
                            "nodeId": node.id,
                            "url": url,
                            "attempt": attempt,
                            "nextAttempt": attempt + 1,
                            "delaySeconds": delay,
                            "errorType": type(error).__name__,
                            "error": str(error)[:500],
                        },
                    )
                    if delay:
                        try:
                            await asyncio.wait_for(context.cancelled.wait(), timeout=delay)
                        except asyncio.TimeoutError:
                            pass
                        self._check_cancelled(context)
            if response is None:
                if not continue_on_error and error is not None:
                    raise error
                await context.event(
                    "request.skipped",
                    "warning",
                    f"Skipped failed request: {url}",
                    {
                        "nodeId": node.id,
                        "url": url,
                        "attempts": attempt_limit,
                        "errorType": type(error).__name__ if error else "UnknownError",
                        "error": str(error)[:500] if error else "unknown request error",
                    },
                )
                continue
            result.append(
                {
                    **item,
                    "url": response.url,
                    "status": response.status,
                    "media_type": response.media_type,
                    "body": response.text(),
                    "response_headers": response.headers,
                }
            )
        return result

    async def _fetch_with_fallback(
        self,
        node: FlowNode,
        context: ExecutionContext,
        url: str,
        *,
        headers: dict[str, str],
        respect_robots: bool,
        fallback_to_http: bool,
        timeout_seconds: float | None,
    ):
        try:
            return await self._fetch_response(
                context,
                url,
                headers=headers,
                respect_robots=respect_robots,
                timeout_seconds=timeout_seconds,
            )
        except Exception as primary_error:
            fallback_url = self._http_fallback_url(url) if fallback_to_http else None
            if fallback_url is None:
                raise
            try:
                response = await self._fetch_response(
                    context,
                    fallback_url,
                    headers=headers,
                    respect_robots=respect_robots,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as fallback_error:
                raise fallback_error from primary_error
            await context.event(
                "request.fallback",
                "warning",
                f"Retried request over HTTP: {fallback_url}",
                {"nodeId": node.id, "url": url, "fallbackUrl": fallback_url},
            )
            return response

    @staticmethod
    async def _fetch_response(
        context: ExecutionContext,
        url: str,
        *,
        headers: dict[str, str],
        respect_robots: bool,
        timeout_seconds: float | None = None,
    ):
        fetch = context.http.fetch(url, headers=headers, respect_robots=respect_robots)
        response = (
            await asyncio.wait_for(fetch, timeout=timeout_seconds)
            if timeout_seconds is not None
            else await fetch
        )
        if response.status < 200 or response.status >= 300:
            raise HttpStatusError(response.status, url)
        return response

    @staticmethod
    def _http_fallback_url(url: str) -> str | None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            return None
        return urlunsplit(("http", parsed.netloc, parsed.path, parsed.query, parsed.fragment))

    def _html_extract(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        selector = str(node.config.get("item_selector", "")).strip()
        fields = node.config.get("fields", {})
        deduplicate_by = str(node.config.get("deduplicate_by", "")).strip()
        seen: set[str] = set()
        if not isinstance(fields, dict) or not fields:
            raise ValueError("html_extract requires a non-empty fields object")
        for item in inputs:
            soup = BeautifulSoup(str(item.get("body", "")), "html.parser")
            scopes = soup.select(selector) if selector else [soup]
            for scope in scopes:
                extracted = {**item}
                for field, specification in fields.items():
                    extracted[field] = self._extract_html_field(scope, specification)
                    if field == "url" or field.endswith("_url"):
                        extracted[field] = urljoin(
                            str(item.get("url", "")), str(extracted[field] or "")
                        )
                extracted.pop("body", None)
                extracted.pop("response_headers", None)
                if deduplicate_by:
                    dedupe_value = str(self._path(extracted, deduplicate_by) or "")
                    if dedupe_value and dedupe_value in seen:
                        continue
                    if dedupe_value:
                        seen.add(dedupe_value)
                result.append(extracted)
                if len(result) >= context.flow.max_items:
                    return result
        return result

    def _json_extract(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        items_path = str(node.config.get("items_path", "")).strip()
        fields = node.config.get("fields", {})
        deduplicate_by = str(node.config.get("deduplicate_by", "")).strip()
        seen: set[str] = set()
        if not isinstance(fields, dict) or not fields:
            raise ValueError("json_extract requires a non-empty fields object")
        for item in inputs:
            payload = self._decode_json_payload(str(item.get("body", "")))
            candidates = self._path(payload, items_path) if items_path else payload
            if not isinstance(candidates, list):
                candidates = [candidates]
            for candidate in candidates:
                extracted = {key: value for key, value in item.items() if key != "body"}
                for field, path in fields.items():
                    extracted[field] = self._path(candidate, str(path))
                if deduplicate_by:
                    dedupe_value = str(self._path(extracted, deduplicate_by) or "")
                    if dedupe_value and dedupe_value in seen:
                        continue
                    if dedupe_value:
                        seen.add(dedupe_value)
                result.append(extracted)
                if len(result) >= context.flow.max_items:
                    return result
        return result

    @staticmethod
    def _decode_json_payload(body: str) -> Any:
        try:
            return json.loads(body)
        except json.JSONDecodeError as json_error:
            match = re.fullmatch(
                r"\s*[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
                r"\s*\((.*)\)\s*;?\s*",
                body,
                flags=re.DOTALL,
            )
            if match is None:
                raise json_error
            return json.loads(match.group(1))

    def _condition(
        self, node: FlowNode, inputs: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        field = str(node.config["field"])
        operator = str(node.config["operator"])
        expected = node.config.get("value")
        outputs: dict[str, list[dict[str, Any]]] = {"true": [], "false": []}
        for item in inputs:
            actual = self._path(item, field)
            matched = self._compare(actual, operator, expected)
            outputs["true" if matched else "false"].append(item)
        return outputs

    def _loop(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        items_path = str(node.config["items_path"])
        item_name = str(node.config["item_name"])
        index_name = str(node.config["index_name"])
        max_iterations = int(node.config["max_iterations"])
        limit = min(max_iterations, context.flow.max_items)
        result: list[dict[str, Any]] = []
        for source in inputs:
            candidates = self._path(source, items_path)
            if candidates is None:
                continue
            if not isinstance(candidates, list):
                raise ValueError(f"loop items_path must resolve to an array: {items_path}")
            for index, value in enumerate(candidates):
                result.append({**source, item_name: value, index_name: index})
                if len(result) >= limit:
                    return result
        return result

    def _pagination(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        url_template = str(node.config["url"])
        parameter = str(node.config["page_parameter"])
        start_page = int(node.config["start_page"])
        max_pages = int(node.config["max_pages"])
        result: list[dict[str, Any]] = []
        for source in inputs:
            base_url = self._template(url_template, source)
            parts = urlsplit(base_url)
            for page in range(start_page, start_page + max_pages):
                query = dict(parse_qsl(parts.query, keep_blank_values=True))
                query[parameter] = str(page)
                paged_url = urlunsplit(
                    (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
                )
                result.append({**source, "url": paged_url, "page": page})
                if len(result) >= context.flow.max_items:
                    return result
        return result

    def _transform(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        mapping = node.config.get("mapping", {})
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("transform requires a non-empty mapping object")
        result: list[dict[str, Any]] = []
        for item in inputs[: context.flow.max_items]:
            transformed = {**item}
            for field, value in mapping.items():
                transformed[field] = (
                    self._template(value, item) if isinstance(value, str) else value
                )
            result.append(transformed)
        return result

    @staticmethod
    def _compare(actual: Any, operator: str, expected: Any) -> bool:
        if operator == "exists":
            return actual is not None
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "contains":
            if actual is None:
                return False
            try:
                return expected in actual
            except TypeError:
                return str(expected) in str(actual)
        if operator in {"gt", "gte", "lt", "lte"}:
            try:
                left = float(actual)
                right = float(expected)
            except (TypeError, ValueError):
                return False
            if operator == "gt":
                return left > right
            if operator == "gte":
                return left >= right
            if operator == "lt":
                return left < right
            return left <= right
        raise ValueError(f"unsupported condition operator: {operator}")

    async def _emit(
        self,
        node: FlowNode,
        inputs: list[dict[str, Any]],
        context: ExecutionContext,
    ) -> int:
        mapping = node.config.get("fields", {})
        if mapping and not isinstance(mapping, dict):
            raise ValueError("emit fields must be an object")
        skip_empty_content = bool(node.config.get("skip_empty_content", False))
        emitted = 0
        existing_count = await context.storage.count_items(context.run_id)
        for item in inputs[: context.flow.max_items]:
            self._check_cancelled(context)
            values = {
                key: self._render_template_value(value, item)
                for key, value in mapping.items()
            }
            url = str(values.get("url") or item.get("url") or item.get("seed_url") or "")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("emitted item URL must be an absolute http(s) URL")
            title = str(values.get("title") or item.get("title") or url)
            content_value = values.get("content", item.get("content", ""))
            if skip_empty_content and not content_value:
                await context.event(
                    "item.skipped",
                    "warning",
                    f"Skipped item without extracted content: {title[:120]}",
                    {"nodeId": node.id, "url": url, "reason": "empty_content"},
                )
                continue
            if not content_value:
                content_value = json.dumps(item, ensure_ascii=False, default=str)
            content = (
                content_value
                if isinstance(content_value, str)
                else json.dumps(content_value, ensure_ascii=False, default=str)
            )
            media_type = str(
                values.get("media_type")
                or item.get("media_type")
                or "text/plain"
            )
            external_id = str(values.get("external_id") or item.get("external_id") or "")
            if not external_id:
                external_id = hashlib.sha256(
                    f"{url}\n{title}\n{content}".encode("utf-8")
                ).hexdigest()
            observed_at = self._datetime(
                values.get("observed_at") or item.get("observed_at")
            )
            metadata_value = values.get("metadata", item.get("metadata", {}))
            metadata = metadata_value if isinstance(metadata_value, dict) else {}
            metadata = {
                **metadata,
                "flowId": context.flow.id,
                "flowName": context.flow.name,
                "nodeId": node.id,
            }
            _, created = await context.storage.add_item(
                context.run_id,
                external_id,
                url,
                title[:1000],
                content,
                media_type,
                observed_at,
                metadata,
            )
            if created:
                emitted += 1
                await context.event(
                    "item.emitted",
                    "info",
                    f"Emitted item: {title[:120]}",
                    {"externalId": external_id, "url": url},
                )
                total = existing_count + emitted
                await context.progress(node.id, f"Emitted {total} item(s)", total)
        return emitted

    @staticmethod
    def _extract_html_field(scope: Any, specification: Any) -> str:
        if isinstance(specification, str):
            selector, attribute, default, multiple, separator, script_variable, json_path = (
                specification,
                "text",
                "",
                False,
                "\n\n",
                "",
                "",
            )
        elif isinstance(specification, dict):
            selector = str(specification.get("selector", ""))
            attribute = str(specification.get("attribute", "text"))
            default = str(specification.get("default", ""))
            multiple = bool(specification.get("all", False))
            separator = str(specification.get("separator", "\n\n"))
            script_variable = str(specification.get("script_variable", "")).strip()
            json_path = str(specification.get("path", "")).strip()
        else:
            raise ValueError("HTML field specification must be a selector or object")
        if script_variable:
            embedded_html = FlowEngine._extract_script_variable(scope, script_variable)
            if embedded_html is None:
                return default
            scope = BeautifulSoup(embedded_html, "html.parser")
        if multiple:
            targets = scope.select(selector) if selector else [scope]
            values = [
                FlowEngine._html_target_value(target, attribute, "", json_path)
                for target in targets
            ]
            values = [value for value in values if value]
            return separator.join(values) if values else default
        target = scope.select_one(selector) if selector else scope
        if target is None:
            return default
        return FlowEngine._html_target_value(target, attribute, default, json_path)

    @staticmethod
    def _html_target_value(
        target: Any, attribute: str, default: str, json_path: str = ""
    ) -> str:
        if attribute == "text":
            return target.get_text(" ", strip=True)
        if attribute == "html":
            return target.decode_contents()
        if attribute == "json":
            source = target.string or target.get_text()
            try:
                value = FlowEngine._path(json.loads(str(source)), json_path)
            except (json.JSONDecodeError, TypeError):
                return default
            if value is None:
                return default
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, default=str)
            return str(value)
        return str(target.get(attribute, default))

    @staticmethod
    def _extract_script_variable(scope: Any, variable: str) -> str | None:
        assignment = re.compile(
            rf"\b(?:(?:var|let|const)\s+)?{re.escape(variable)}\s*=\s*(['\"])",
            flags=re.MULTILINE,
        )
        for script in scope.select("script"):
            source = str(script.string or script.get_text() or "")
            match = assignment.search(source)
            if match is None:
                continue
            quote = match.group(1)
            start = match.end()
            for index in range(start, len(source)):
                if source[index] != quote:
                    continue
                backslashes = 0
                cursor = index - 1
                while cursor >= start and source[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    return FlowEngine._decode_javascript_string(source[start:index])
        return None

    @staticmethod
    def _decode_javascript_string(value: str) -> str:
        value = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            value,
        )
        value = re.sub(
            r"\\x([0-9a-fA-F]{2})",
            lambda match: chr(int(match.group(1), 16)),
            value,
        )
        escapes = {
            "\\": "\\",
            "'": "'",
            '"': '"',
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        return re.sub(
            r"\\([\\/'\"bfnrt])",
            lambda match: escapes[match.group(1)],
            value,
        )

    @staticmethod
    def _path(value: Any, path: str) -> Any:
        if not path:
            return value
        current = value
        for token in path.split("."):
            if token == "":
                continue
            if isinstance(current, dict):
                current = current.get(token)
            elif isinstance(current, list) and token.isdigit():
                index = int(token)
                current = current[index] if index < len(current) else None
            else:
                return None
        return current

    @classmethod
    def _template(cls, template: str, values: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            value = cls._path(values, match.group(1).strip())
            return "" if value is None else str(value)

        return re.sub(r"{{\s*([^{}]+?)\s*}}", replace, template)

    @classmethod
    def _render_template_value(cls, value: Any, values: dict[str, Any]) -> Any:
        if isinstance(value, str):
            return cls._template(value, values)
        if isinstance(value, dict):
            return {
                key: cls._render_template_value(nested, values)
                for key, nested in value.items()
            }
        if isinstance(value, list):
            return [cls._render_template_value(nested, values) for nested in value]
        return value

    @staticmethod
    def _resolve_secret(value: str) -> str:
        match = re.fullmatch(r"\$\{secret:([A-Za-z0-9_]+)}", value)
        if not match:
            return value
        name = f"SIFTLANE_ENGINE_SECRET_{match.group(1).upper()}"
        secret = os.getenv(name)
        if secret is None:
            raise ValueError(f"required secret is not configured: {match.group(1)}")
        return secret

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed
            except ValueError:
                pass
        return utc_now()

    @staticmethod
    def _check_cancelled(context: ExecutionContext) -> None:
        if context.cancelled.is_set():
            raise RunCancelled()


class RunCancelled(RuntimeError):
    pass


class HttpStatusError(RuntimeError):
    def __init__(self, status: int, url: str):
        super().__init__(f"request returned HTTP {status}: {url}")
        self.status = status


def node_capabilities() -> list[NodeCapability]:
    return [
        NodeCapability(
            type=NodeType.START,
            label="Start",
            description="Produces configured seed URLs and runtime parameters.",
            category="control",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.START],
        ),
        NodeCapability(
            type=NodeType.HTTP_REQUEST,
            label="HTTP request",
            description="Fetches a public HTTP resource with rate, redirect and size limits.",
            category="network",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.HTTP_REQUEST],
        ),
        NodeCapability(
            type=NodeType.HTML_EXTRACT,
            label="HTML extract",
            description="Extracts repeated records with CSS selectors.",
            category="extract",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.HTML_EXTRACT],
        ),
        NodeCapability(
            type=NodeType.JSON_EXTRACT,
            label="JSON extract",
            description="Extracts records and fields from a JSON response.",
            category="extract",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.JSON_EXTRACT],
        ),
        NodeCapability(
            type=NodeType.CONDITION,
            label="Condition",
            description="Routes records through true or false output ports.",
            category="control",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.CONDITION],
        ),
        NodeCapability(
            type=NodeType.LOOP,
            label="Loop",
            description="Expands an array into bounded downstream records.",
            category="control",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.LOOP],
        ),
        NodeCapability(
            type=NodeType.PAGINATION,
            label="Pagination",
            description="Generates a bounded set of page-number URLs.",
            category="network",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.PAGINATION],
        ),
        NodeCapability(
            type=NodeType.TRANSFORM,
            label="Transform",
            description="Maps values with safe {{field}} templates; no code execution.",
            category="process",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.TRANSFORM],
        ),
        NodeCapability(
            type=NodeType.EMIT,
            label="Emit",
            description="Writes normalized crawler items to the durable result store.",
            category="output",
            config_schema=NODE_CONFIG_SCHEMAS[NodeType.EMIT],
        ),
    ]
