import pytest
from falkordb import FalkorDB, Graph

import query_complex14 as query
from correctness import complex14
from correctness.harness import assert_complex, complex_params

KNOWN_FAILURES = {}


@pytest.fixture(scope="session")
def graph() -> Graph:
    db = FalkorDB(host=query.FALKORDB_HOST, port=query.FALKORDB_PORT)
    yield db.select_graph(query.FALKORDB_GRAPH)
    db.close()


def _run(graph: Graph, idx: int) -> list[tuple]:
    return [tuple(record.values()) for record in query.QUERY_FUNCTIONS[idx](graph)]


def test_params():
    assert query.PARAMS == complex14.PARAMS


@pytest.mark.parametrize("idx", complex_params(KNOWN_FAILURES))
def test_complex(graph, idx):
    assert_complex(idx, _run(graph, idx))


@pytest.mark.parametrize(
    ("pair", "idx"), [pytest.param(pair, idx, id=f"{pair}-Q{idx}") for pair in complex14.PATH_PAIRS for idx in (13, 14)]
)
def test_paths(graph, monkeypatch, pair, idx):
    params = {"person1Id": pair[0], "person2Id": pair[1]}
    monkeypatch.setitem(query.PARAMS, idx, params)
    monkeypatch.setitem(complex14.PARAMS, idx, params)
    assert_complex(idx, _run(graph, idx))
