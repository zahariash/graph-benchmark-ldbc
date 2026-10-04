from __future__ import annotations

import re

import pytest

import query
from correctness.harness import assert_rows, check_params, expected
from correctness.oracle import TOTAL_NODES, TOTAL_RELS

OVERRIDES = {
    # No date(); birthday is an ISO date string
    "B08": """
    MATCH (p:Person)<-[:hasModerator]-(f:Forum)
    WHERE p.birthday > "1990-01-01"
      AND f.title CONTAINS "Emilio Fernandez"
    RETURN DISTINCT p.ID
    """,
    # Comma patterns sharing variables fail to plan; single chain as in query.py
    "B22": """
    MATCH (o:Organisation)<-[:workAt]-(p:Person)<-[:commentHasCreator]-(c:Comment)-[:replyOfPost]->(post:Post)
    WHERE o.name = "Linxair"
    RETURN DISTINCT c.ID
    """,
    # The canonical pattern order fails to plan; order as in query.py
    "B28": """
    MATCH (p:Person)-[:hasInterest]->(t:Tag)-[:hasType]->(tc:Tagclass),
          (p)-[:personIsLocatedIn]->(l:Place)
    WHERE tc.name = "BritishRoyalty" AND l.name = "Manila"
    RETURN DISTINCT p.ID
    """,
}

UNDIRECTED = "undirected -[:R]- patterns are evaluated as outgoing -[:R]-> only"
KNOWN_FAILURES = {
    "M04": (UNDIRECTED, AssertionError),
    "M05": (UNDIRECTED, AssertionError),
    "M06": (UNDIRECTED, AssertionError),
    "V05": (UNDIRECTED, AssertionError),
    "V06": (UNDIRECTED, AssertionError),
    "O01": ("unsupported: OPTIONAL MATCH", ValueError),
    "O02": ("unsupported: OPTIONAL MATCH", ValueError),
    "O03": ("unsupported: OPTIONAL MATCH", ValueError),
    "X01": ("unsupported: pattern predicates", ValueError),
    "X02": ("unsupported: pattern predicates", ValueError),
    "W01": ("unsupported: WITH ... WHERE", ValueError),
    "W02": ("planner error: variable not visible after WITH ... ORDER BY ... LIMIT", ValueError),
}


@pytest.fixture(scope="session")
def graph_context():
    config = query.build_config()
    datasets = query.load_datasets(query.GRAPH_ROOT)
    return query.QueryContext(
        config=config,
        datasets=datasets,
        engine=query.CypherEngine(config, datasets),
    )


def _to_lance(cypher: str) -> str:
    """Property names are stored lower-case."""
    cypher = re.sub(r"(?<=\w)\.([A-Za-z_]\w*)", lambda m: "." + m.group(1).lower(), cypher)
    return re.sub(r"\{\s*(\w+)\s*:", lambda m: "{" + m.group(1).lower() + ":", cypher)


def _run(context: query.QueryContext, cypher: str) -> list[tuple]:
    return query.to_polars(context.engine.execute(_to_lance(cypher))).rows()


def test_graph_totals(graph_context):
    datasets = graph_context.datasets
    assert sum(datasets[label].num_rows for label in query.NODE_LABELS) == TOTAL_NODES
    assert sum(datasets[rel].num_rows for rel in query.REL_DATASETS) == TOTAL_RELS


@pytest.mark.parametrize("check", check_params(KNOWN_FAILURES))
def test_correctness(graph_context, check):
    got = _run(graph_context, OVERRIDES.get(check.name, check.cypher))
    assert_rows(got, expected(check), check.ordered)
