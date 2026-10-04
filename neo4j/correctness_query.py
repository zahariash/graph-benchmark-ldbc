from __future__ import annotations

import pytest
from neo4j import READ_ACCESS, GraphDatabase, Query, Session

import query
from correctness.harness import assert_rows, check_params, expected
from correctness.oracle import TOTAL_NODES, TOTAL_RELS

TIMEOUT_S = 120

KNOWN_FAILURES = {}


@pytest.fixture(scope="session")
def session() -> Session:
    if query.NEO4J_USER is None or query.NEO4J_PASSWORD is None:
        raise EnvironmentError("NEO4J_USER and NEO4J_PASSWORD must be set")
    with GraphDatabase.driver(query.URI, auth=(query.NEO4J_USER, query.NEO4J_PASSWORD)) as driver:
        with driver.session(database=query.NEO4J_DATABASE, default_access_mode=READ_ACCESS) as session:
            yield session


def _run(session: Session, cypher: str) -> list[tuple]:
    return [tuple(record.values()) for record in session.run(Query(cypher, timeout=TIMEOUT_S))]


def test_graph_totals(session):
    assert _run(session, "MATCH (n) RETURN count(n)") == [(TOTAL_NODES,)]
    assert _run(session, "MATCH ()-[r]->() RETURN count(r)") == [(TOTAL_RELS,)]


@pytest.mark.parametrize("check", check_params(KNOWN_FAILURES))
def test_correctness(session, check):
    assert_rows(_run(session, check.cypher), expected(check), check.ordered)
