from __future__ import annotations

from pathlib import Path

import ladybug as lb
import pytest

from correctness import checks
from correctness.harness import assert_rows, check_params, expected
from correctness.oracle import TOTAL_NODES, TOTAL_RELS

DB_PATH = Path(__file__).with_name("ldbc_snb_sf1.lbdb")
TIMEOUT_MS = 120_000

OVERRIDES = {
    # birthday is a DATE property
    "B08": """
    MATCH (p:Person)<-[:hasModerator]-(f:Forum)
    WHERE p.birthday > DATE("1990-01-01")
      AND f.title CONTAINS "Emilio Fernandez"
    RETURN DISTINCT p.ID
    """,
    # Variable-length paths default to WALK semantics
    "V06": "MATCH (p:Person {ID: 933})-[:knows* TRAIL 1..3]-(f:Person) WHERE f.ID <> 933 RETURN count(*) AS n",
    # Pattern predicates are written as NOT EXISTS subqueries
    "X01": """
    MATCH (a:Person {ID: 933})-[:knows]-(b:Person)-[:knows]-(c:Person)
    WHERE c.ID <> 933 AND NOT EXISTS { MATCH (a)-[:knows]-(c) }
    RETURN DISTINCT c.ID
    """,
    "X02": """
    MATCH (p:Person)-[:personIsLocatedIn]->(l:Place)
    WHERE l.name = "Berlin" AND NOT EXISTS { MATCH (p)-[:workAt]->(:Organisation) }
    RETURN p.ID
    """,
}

# Fixed-length patterns may reuse a relationship (WALK semantics, the documented default)
EXPECTED_OVERRIDES = {"M06": checks.m6_walk}

KNOWN_FAILURES = {}


@pytest.fixture(scope="session")
def connection():
    db = lb.Database(str(DB_PATH), read_only=True)
    conn = lb.Connection(db)
    conn.set_query_timeout(TIMEOUT_MS)
    yield conn


def _run(conn: lb.Connection, cypher: str) -> list[tuple]:
    result = conn.execute(cypher)
    rows = []
    while result.has_next():
        rows.append(tuple(result.get_next()))
    result.close()
    return rows


def test_graph_totals(connection):
    assert _run(connection, "MATCH (n) RETURN count(*)") == [(TOTAL_NODES,)]
    assert _run(connection, "MATCH ()-[r]->() RETURN count(*)") == [(TOTAL_RELS,)]


@pytest.mark.parametrize("check", check_params(KNOWN_FAILURES))
def test_correctness(connection, check):
    got = _run(connection, OVERRIDES.get(check.name, check.cypher))
    assert_rows(got, expected(check, EXPECTED_OVERRIDES.get(check.name)), check.ordered)
