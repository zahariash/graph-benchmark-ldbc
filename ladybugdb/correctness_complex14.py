from pathlib import Path

import ladybug as lb
import pytest

import query_complex14 as query
from correctness import complex14
from correctness.harness import assert_complex, complex_params

DB_PATH = Path(__file__).with_name("ldbc_snb_sf1.lbdb")

KNOWN_FAILURES = {
    "Q1": ("COLLECT() over only nulls returns NULL instead of an empty list", AssertionError),
}
# The unrolled Q14 chain multiplies the reply matches of every path edge before counting them
PATH_FAILURES = {
    ((933, 4598), 14): ("4-hop Q14 exhausts the buffer pool", RuntimeError),
}


def _path_params():
    params = []
    for pair in complex14.PATH_PAIRS:
        for idx in (13, 14):
            marks = []
            if (pair, idx) in PATH_FAILURES:
                reason, raises = PATH_FAILURES[(pair, idx)]
                marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=raises))
            params.append(pytest.param(pair, idx, id=f"{pair}-Q{idx}", marks=marks))
    return params


@pytest.fixture(scope="session")
def connection():
    db = lb.Database(str(DB_PATH), read_only=True)
    yield lb.Connection(db)


@pytest.mark.parametrize("idx", complex_params(KNOWN_FAILURES))
def test_complex(connection, idx):
    assert_complex(idx, query.QUERY_FUNCTIONS[idx](connection).rows())


@pytest.mark.parametrize(("pair", "idx"), _path_params())
def test_paths(connection, monkeypatch, pair, idx):
    monkeypatch.setitem(complex14.PARAMS, idx, {"person1Id": pair[0], "person2Id": pair[1]})
    result = query.QUERY_FUNCTIONS[idx](connection, person1Id=pair[0], person2Id=pair[1])
    assert_complex(idx, result.rows())
