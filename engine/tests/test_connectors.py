from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from siftlane_connector_sdk import (
    ConnectorCapability,
    ConnectorContext,
    ConnectorItem,
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
)
from siftlane_engine.connectors import ConnectorContractError, ConnectorRegistry


class FixtureConnector:
    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            id="dev.fixture-catalog",
            name="Fixture catalog",
            version="1.0.0",
            capabilities=[
                ConnectorCapability(
                    id="search_content",
                    label="Search content",
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                )
            ],
        )

    async def execute(
        self,
        request: ConnectorOperationRequest,
        context: ConnectorContext,
    ) -> ConnectorOperationResult:
        return ConnectorOperationResult(
            items=[
                ConnectorItem(
                    external_id="fixture-1",
                    url="https://example.com/fixture-1",
                    title=str(request.parameters["query"]),
                    observed_at=datetime.now(timezone.utc),
                )
            ]
        )


def test_manifest_and_registry_contract():
    registry = ConnectorRegistry([FixtureConnector()])
    manifests = registry.manifests()
    assert manifests[0].id == "dev.fixture-catalog"
    assert manifests[0].capabilities[0].id == "search_content"
    assert registry.get("dev.fixture-catalog") is not None


def test_registry_rejects_duplicate_ids():
    with pytest.raises(ConnectorContractError, match="duplicate connector id"):
        ConnectorRegistry([FixtureConnector(), FixtureConnector()])


def test_manifest_rejects_duplicate_capabilities():
    capability = ConnectorCapability(
        id="search_content",
        label="Search",
        input_schema={"type": "object"},
    )
    with pytest.raises(ValidationError, match="capability ids must be unique"):
        ConnectorManifest(
            id="dev.invalid",
            name="Invalid",
            version="1.0.0",
            capabilities=[capability, capability],
        )
