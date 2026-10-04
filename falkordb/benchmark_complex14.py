import pytest
from falkordb import FalkorDB, Graph

import query_complex14 as query


@pytest.fixture(scope="session")
def graph() -> Graph:
    db = FalkorDB(host=query.FALKORDB_HOST, port=query.FALKORDB_PORT)
    yield db.select_graph(query.FALKORDB_GRAPH)
    db.close()


def test_benchmark_complex1(benchmark, graph):
    benchmark(query.run_query1, graph)


def test_benchmark_complex2(benchmark, graph):
    benchmark(query.run_query2, graph)


def test_benchmark_complex3(benchmark, graph):
    benchmark(query.run_query3, graph)


def test_benchmark_complex4(benchmark, graph):
    benchmark(query.run_query4, graph)


def test_benchmark_complex5(benchmark, graph):
    benchmark(query.run_query5, graph)


def test_benchmark_complex6(benchmark, graph):
    benchmark(query.run_query6, graph)


def test_benchmark_complex7(benchmark, graph):
    benchmark(query.run_query7, graph)


def test_benchmark_complex8(benchmark, graph):
    benchmark(query.run_query8, graph)


def test_benchmark_complex9(benchmark, graph):
    benchmark(query.run_query9, graph)


def test_benchmark_complex10(benchmark, graph):
    benchmark(query.run_query10, graph)


def test_benchmark_complex11(benchmark, graph):
    benchmark(query.run_query11, graph)


def test_benchmark_complex12(benchmark, graph):
    benchmark(query.run_query12, graph)


def test_benchmark_complex13(benchmark, graph):
    benchmark(query.run_query13, graph)


def test_benchmark_complex14(benchmark, graph):
    benchmark(query.run_query14, graph)
