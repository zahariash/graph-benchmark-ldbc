# FalkorDB

This section describes how to benchmark the social network data in [FalkorDB](https://github.com/FalkorDB/FalkorDB), a graph database built as a Redis module. Version 6.0 replaced the 4.x C engine with a new engine written in Rust; the commands and Cypher are unchanged.

## Setup

FalkorDB runs as a server. Start it via Docker using the provided `docker-compose.yml`, which pins the image to `6.0.1`:

```sh
docker compose up -d
```

The scripts connect with the [`falkordb`](https://pypi.org/project/falkordb/) Python client and are configured via environment variables:

- `FALKORDB_HOST` (optional, defaults to `localhost`)
- `FALKORDB_PORT` (optional, defaults to `6379`; also sets the host port in `docker-compose.yml`)
- `FALKORDB_GRAPH` (optional, defaults to `ldbc_snb_sf1`)
- `FALKORDB_VERSION` (optional, Docker image tag, defaults to `6.0.1`)

## Build graph

The script `build_graph.py` drops any existing graph with the same name, creates a range index on `ID` for each node label, then ingests the CSV files in batches with `UNWIND ... CREATE`. Edges look up both endpoints through the `ID` indexes. After ingestion it builds range indexes on the selectively filtered properties (`Place.name`, `Tag.name`, `Tagclass.name`, `Organisation.name`, `Person.firstName`, `Person.lastName`, `Comment.length`), waits until every index is operational, and prints the total node and relationship counts.

The secondary indexes follow Ladybug's ART indexes with two differences. There is no index on `Person.birthday`, because Q8 filters on `date(p.birthday)` and a property index cannot serve that predicate. `Organisation.name` and `Tagclass.name` are indexed for their equality filters; Ladybug leaves them out because they slowed down its engine on these small tables. Neo4j, Kuzu and lance-graph use ID indexes only.

```sh
uv run build_graph.py
```

## Visualize graph

The FalkorDB image ships with the FalkorDB Browser, available at `http://localhost:3000`.

## Execute queries

The query suite consists of the same 30 Cypher queries used for Neo4j, unchanged. Each query is sent with `GRAPH.RO_QUERY`.

Run the full query suite using the provided script below.

```bash
uv run query.py
```

Run a subset by passing a comma-separated list of query numbers:

```bash
uv run query.py "1,2,6"
```

### Run benchmark

Run from `falkordb/`:

```sh
uv run --frozen pytest benchmark_query.py \
  --benchmark-min-rounds=5 \
  --benchmark-min-time=0.000005 \
  --benchmark-max-time=1.0 \
  --benchmark-timer=time.perf_counter \
  --benchmark-calibration-precision=10 \
  --benchmark-warmup=off \
  --benchmark-warmup-iterations=5 \
  --benchmark-disable-gc \
  --benchmark-sort=fullname
```

## Results

Measured on **2026-10-04** on an AMD Ryzen 9 6900HS (16 logical CPUs, 30 GiB RAM) running Linux 7.1.3 and Python 3.14.0, with FalkorDB 6.0.1 in Docker started from the provided `docker-compose.yml` (`THREAD_COUNT` and `OMP_THREAD_COUNT` 16, query timeouts disabled, unlimited result set size). This is a different machine from the Apple M5 used for the other engines, so these numbers are not directly comparable with the main table.

[CLI output](../results/falkordb-6.0.1.txt) · [Raw benchmark JSON](../results/falkordb-6.0.1.json)

Ingestion took 38 s for the 3,181,724 nodes, 950 s for the 17,256,038 relationships and 4 s for the secondary indexes. After loading, `GRAPH.MEMORY USAGE` reports 2.84 GB for the graph and the server's resident memory (RSS) is about 3.5 GB; Redis's allocator peak during ingestion was 3.8 GB.

All 30 queries passed their result assertions with the benchmark settings above. Apart from Q30, every query averages under 11 ms. Q30 averages 81.6 s over five rounds: the planner starts from each `Person`, pairs all of that person's comments with all of their posts (about 447M candidate pairs) and only then checks `replyOfPost`. The query text is identical to Neo4j's for all 30 queries.

### Compared with FalkorDB 4.22.0

The previous run used FalkorDB 4.22.0, which has the C engine, on the same machine ([CLI output](../results/archived/falkordb-4.22.0.txt), [Q30 runs](../results/archived/falkordb-4.22.0-q30.txt)). 6.0.1 has a lower mean latency on 22 of 30 queries.

- The three slowest 4.22.0 queries improved most. Q12 fell from 8,054 ms to 1.8 ms and Q16 from 105 ms to 7.1 ms: 6.0.1 starts both from the indexed `Place`, where 4.22.0 scanned every `Comment` or `Post`. Q30 fell from 1,281 s (a single run, excluded from the 4.22.0 suite) to 81.6 s, so it is now part of the timed suite.
- Q2, Q3, Q13, Q28 and Q29 got slower, from 0.27–2.1 ms to 6.2–8.5 ms. In Q2 and Q3, `GRAPH.PROFILE` shows the traversal over `postHasCreator` taking about 6.6 ms even when it expands a single post; Q29 has the same shape as Q2. Q28 now starts from the `Tagclass` and expands about 19,000 rows before filtering on `Place.name`.
- Ingestion was slower (950 s for the relationships, 710 s on 4.22.0) and the graph uses more memory (2.84 GB, 1.87 GB on 4.22.0).
