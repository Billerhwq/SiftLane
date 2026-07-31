import pytest
from pydantic import ValidationError

from siftlane_engine.models import FlowDefinition


def graph(edges=None):
    return {
        "name": "Fixture",
        "nodes": [
            {"id": "start", "type": "start", "name": "Start", "config": {"urls": ["https://example.com"]}},
            {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
        ],
        "edges": edges or [{"id": "e1", "source": "start", "target": "emit"}],
    }


def test_valid_graph_is_accepted():
    flow = FlowDefinition.model_validate(graph())
    assert flow.nodes[0].id == "start"


def test_cycle_is_rejected():
    value = graph(
        [
            {"id": "e1", "source": "start", "target": "emit"},
            {"id": "e2", "source": "emit", "target": "start"},
        ]
    )
    with pytest.raises(ValidationError, match="acyclic"):
        FlowDefinition.model_validate(value)


def test_disconnected_node_is_rejected():
    value = graph()
    value["nodes"].append(
        {"id": "unused", "type": "transform", "name": "Unused", "config": {"mapping": {"x": "y"}}}
    )
    with pytest.raises(ValidationError, match="reachable"):
        FlowDefinition.model_validate(value)


def test_node_config_is_validated_against_capability_schema():
    value = graph()
    value["nodes"][0]["config"] = {"urls": [], "unknown": True}
    with pytest.raises(ValidationError, match="invalid config for node start"):
        FlowDefinition.model_validate(value)
