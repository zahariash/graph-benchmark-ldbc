# Correctness checks

This section describes the result-correctness checks for the five engines (Neo4j, Kuzu, Ladybug, lance-graph, FalkorDB). The benchmark assertions compare a few hard-coded values, several of them `COUNT(...) > 0` booleans, top-1 rows or empty results, so an engine can pass them while returning wrong rows. These checks compare full result sets against expected results computed from the CSVs, without touching the timing code or the 30 benchmark query texts.

## Expected results

`oracle.py` computes the expected result of every check directly from the LDBC CSV files with polars, independently of any graph engine. A Cypher pattern is evaluated as a chain of inner joins over the edge tables: node variables are ID columns, each relationship hop is a join, a variable that already exists closes a cycle, `OPTIONAL MATCH` is a left join, `DISTINCT` is `unique()` and `count(*)` is the row count. Inner joins keep bag semantics, so path multiplicity is preserved exactly.

Results are compared as multisets of row tuples, ignoring column names, without normalising values. Only G01, whose `ORDER BY` breaks ties on a unique key, is compared as an ordered list.

## Checks

`checks.py` defines 61 checks, each with one canonical Cypher text (Neo4j dialect) and one oracle:

| Group | Checks | Semantics pinned |
| --- | --- | --- |
| B01–B30 | the 30 benchmark queries, expanded to full result sets | the rows behind each benchmark assertion: `COUNT(x) [> 0]` becomes `RETURN x` (bag), `COUNT(DISTINCT x)` becomes `RETURN DISTINCT x`, `LIMIT`/`ORDER BY` are dropped so grouped aggregates return every group |
| N07–N29 | non-empty variants of the empty-result queries Q7, Q24, Q25, Q26, Q29 | the same shapes with parameters that do match, so an engine cannot pass by returning nothing |
| M01–M06 | fixed-length multi-hop | path multiplicity (`count(*)` vs `DISTINCT`), named vs anonymous intermediate nodes, undirected traversal of a node with both in- and out-edges, relationship uniqueness within one `MATCH` |
| V01–V09 | variable-length paths | ranges, exact lengths (`*2..2`, `*3..3`) with and without endpoint filters, undirected ranges, trail path counts, tree-shaped chains (`replyOfComment`), hierarchy closures |
| O01–O03 | `OPTIONAL MATCH` | nulls kept, `count()` yielding zero, chained optionals |
| X01–X02 | negation | pattern predicates / `NOT EXISTS` |
| W01–W02 | `WITH` pipelines | mid-query aggregation and filtering, `ORDER BY ... LIMIT` before a second `MATCH` |
| G01 | ordered aggregate | `ORDER BY count DESC, name LIMIT 5`, order-sensitive |
| C01–C03 | cyclic patterns | triangles, same-creator comment replies, shared interests between friends |

### Walk vs trail

Neo4j and FalkorDB forbid reusing a relationship within one `MATCH` (trail semantics); Kuzu and Ladybug default to walk semantics. Checks compare only quantities on which both agree: distinct endpoints, directed `knows` paths of length ≤ 3 (the data has no self-loops or reciprocal `knows` pairs, so no edge can repeat) and tree-shaped relationships. Two checks set the semantics explicitly: V06 uses Kuzu's `* TRAIL` keyword, and Kuzu and Ladybug check M06 against a walk-semantics oracle through `EXPECTED_OVERRIDES`.

### Dialects

An engine that needs a different query text lists it in `OVERRIDES` in its own `correctness_query.py`, with a comment explaining why, the same way each engine's `query.py` holds its own benchmark queries. Overrides exist only where a construct differs:

- Kuzu and Ladybug: `birthday` is a `DATE` property (B08), `* TRAIL` (V06), `NOT EXISTS { MATCH ... }` instead of `NOT (pattern)` (X01, X02).
- FalkorDB: Q30 staged with `WITH` (B30); the verbatim text takes about 80 seconds because of a planner issue.
- lance-graph: `birthday` is an ISO date string (B08), pattern orderings from `lance_graph/query.py` where the canonical order fails to plan (B22, B28), and property names rewritten to lower case.

## Known failures

Each engine's `KNOWN_FAILURES` lists its wrong results and unsupported constructs with the reason (an upstream issue link where one exists) and the exception they fail with: `AssertionError` for a wrong result, the engine's error type for an unsupported construct. They run as strict `xfail`s pinned to that exception: a known failure is reported without failing the run, while a check that starts passing or fails differently fails the run until its entry is updated. Any other mismatch, engine error or timeout fails the test.

## Safety

All access is read-only (`GRAPH.RO_QUERY`, `read_only=True`, Neo4j `READ_ACCESS`). Queries run with a 120 s timeout where the engine supports one: FalkorDB `ro_query(timeout=)`, Neo4j transaction timeouts and Kuzu/Ladybug `set_query_timeout`. `test_graph_totals` in each engine's file checks the graph totals (3,181,724 nodes, 17,256,038 relationships).

## Run checks

The oracle needs the CSVs downloaded by `download_dataset.py`. Run each engine's `correctness_query.py` from its directory, with the graph loaded as described in its README:

```sh
cd neo4j && uv run --frozen pytest correctness_query.py -rx
cd kuzu && uv run --frozen pytest correctness_query.py -rx
cd ladybugdb && uv run --frozen pytest correctness_query.py -rx
cd lance_graph && uv run --frozen pytest correctness_query.py -rx
cd falkordb && uv run --frozen pytest correctness_query.py -rx
```

pytest reports 62 tests per engine: the 61 checks and `test_graph_totals`. `-rx` lists the known failures with their reasons; `-k "M0 or V0"` selects checks.

## Results

| Engine | Pass | Known failures |
| --- | ---: | --- |
| Neo4j 2025.12.1 | 61 | – |
| Kuzu 0.11.3 | 61 | – |
| Ladybug 0.21.1 | 61 | – |
| FalkorDB 6.0.2 | 60 | M06 ([#2441](https://github.com/FalkorDB/FalkorDB/issues/2441)) |
| lance-graph 0.5.4 | 49 | undirected patterns evaluated as outgoing only (M04–M06, V05, V06); unsupported `OPTIONAL MATCH` (O01–O03), pattern predicates (X01, X02) and `WITH ... WHERE` (W01); planner error (W02) |

All 30 benchmark queries (B01–B30) pass on every engine.

## Layout

- `oracle.py` – CSV loading and the join helpers that express expected results.
- `checks.py` – canonical Cypher and oracle for each check.
- `harness.py` – expected results, comparison and pytest parameters.
- `<engine>/correctness_query.py` – connection, query execution, `OVERRIDES` and `KNOWN_FAILURES` for one engine.

`pyproject.toml` adds the repository root to pytest's `pythonpath` so the engine directories can import `correctness`.

> [!NOTE]
> The engine directories have no `__init__.py`, so `import neo4j`, `import kuzu`, `import falkordb` and `import lance_graph` resolve to the installed packages. Adding an `__init__.py` to any of them would shadow its package in every pytest run.
