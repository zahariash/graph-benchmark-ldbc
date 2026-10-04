from pathlib import Path

import ladybug as lb
import pytest

import query_complex14 as query
from correctness import complex14
from correctness.harness import assert_complex, complex_params

DB_PATH = Path(__file__).with_name("ldbc_snb_sf1.lbdb")

KNOWN_FAILURES = {}


# 0 = default thread count; some 0.21.x bugs only show at low thread counts
@pytest.fixture(scope="session", params=[0, 1], ids=["default-threads", "1-thread"])
def connection(request):
    db = lb.Database(str(DB_PATH), read_only=True)
    yield lb.Connection(db, num_threads=request.param)


@pytest.mark.parametrize("idx", complex_params(KNOWN_FAILURES))
def test_complex(connection, idx):
    assert_complex(idx, query.QUERY_FUNCTIONS[idx](connection).rows())


@pytest.mark.parametrize(
    ("pair", "idx"), [pytest.param(pair, idx, id=f"{pair}-Q{idx}") for pair in complex14.PATH_PAIRS for idx in (13, 14)]
)
def test_paths(connection, monkeypatch, pair, idx):
    monkeypatch.setitem(complex14.PARAMS, idx, {"person1Id": pair[0], "person2Id": pair[1]})
    result = query.QUERY_FUNCTIONS[idx](connection, person1Id=pair[0], person2Id=pair[1])
    assert_complex(idx, result.rows())
