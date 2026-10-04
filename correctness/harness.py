"""Shared helpers for the per-engine correctness tests (`<engine>/correctness_*.py`)."""

from collections import Counter
from collections.abc import Callable

import pytest

from correctness import complex14
from correctness.checks import CHECKS, Check
from correctness.oracle import Data, Rows

_data = Data()


def expected(check: Check, oracle: Callable[[Data], Rows] | None = None) -> Rows:
    return (oracle or check.expected)(_data)


def assert_rows(got: Rows, want: Rows, ordered: bool) -> None:
    if ordered:
        assert got == want
        return
    missing = list((Counter(want) - Counter(got)).elements())
    extra = list((Counter(got) - Counter(want)).elements())
    assert not missing and not extra, (
        f"expected {len(want)} rows, got {len(got)}; "
        f"missing {len(missing)} e.g. {missing[:3]}; extra {len(extra)} e.g. {extra[:3]}"
    )


def assert_complex(idx: int, got: Rows) -> None:
    """Compare an engine's rows for complex query `idx` with the oracle, after normalising values."""
    rows = [complex14.normalize_row(idx, row) for row in got]
    assert_rows(rows, complex14.EXPECTED[idx](_data), idx in complex14.ORDERED)


def _param(value, name: str, known_failures: dict[str, tuple[str, type[Exception]]]):
    marks = []
    if name in known_failures:
        reason, raises = known_failures[name]
        marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=raises))
    return pytest.param(value, id=name, marks=marks)


def check_params(known_failures: dict[str, tuple[str, type[Exception]]]):
    """One pytest param per check; a known failure must keep failing with the given exception."""
    unknown = set(known_failures) - {check.name for check in CHECKS}
    assert not unknown, f"unknown checks in KNOWN_FAILURES: {sorted(unknown)}"
    return [_param(check, check.name, known_failures) for check in CHECKS]


def complex_params(known_failures: dict[str, tuple[str, type[Exception]]]):
    """One pytest param per complex query (Q1..Q14); a known failure must keep failing as given."""
    names = {f"Q{idx}": idx for idx in complex14.EXPECTED}
    unknown = set(known_failures) - set(names)
    assert not unknown, f"unknown queries in KNOWN_FAILURES: {sorted(unknown)}"
    return [_param(idx, name, known_failures) for name, idx in names.items()]
