from __future__ import annotations

import pytest
from falkordb import FalkorDB, Graph

import query
from correctness.harness import assert_rows, check_params, expected
from correctness.oracle import TOTAL_NODES, TOTAL_RELS

TIMEOUT_MS = 120_000

OVERRIDES = {
    # The verbatim Q30 takes ~80 s because of the planner; same result, staged with WITH
    "B30": """
    MATCH (c:Comment)-[:replyOfPost]->(post:Post)-[:postHasCreator]->(creator:Person)
    WITH c, creator
    MATCH (c)-[:commentHasCreator]->(creator)
    RETURN DISTINCT c.ID
    """,
}

KNOWN_FAILURES = {
    "M06": ("https://github.com/FalkorDB/FalkorDB/issues/2441 relationship reused within one path", AssertionError),
}


@pytest.fixture(scope="session")
def graph() -> Graph:
    db = FalkorDB(host=query.FALKORDB_HOST, port=query.FALKORDB_PORT)
    yield db.select_graph(query.FALKORDB_GRAPH)
    db.close()


def _run(graph: Graph, cypher: str) -> list[tuple]:
    return [tuple(row) for row in graph.ro_query(cypher, timeout=TIMEOUT_MS).result_set]


def test_graph_totals(graph):
    assert _run(graph, "MATCH (n) RETURN count(n)") == [(TOTAL_NODES,)]
    assert _run(graph, "MATCH ()-[r]->() RETURN count(r)") == [(TOTAL_RELS,)]


@pytest.mark.parametrize("check", check_params(KNOWN_FAILURES))
def test_correctness(graph, check):
    got = _run(graph, OVERRIDES.get(check.name, check.cypher))
    assert_rows(got, expected(check), check.ordered)
