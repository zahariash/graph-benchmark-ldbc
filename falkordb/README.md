# FalkorDB

This section describes how to benchmark the social network data in [FalkorDB](https://github.com/FalkorDB/FalkorDB), a graph database built as a Redis module that stores adjacency as sparse matrices and queries them with GraphBLAS.

## Setup

FalkorDB runs as a server. Start it via Docker using the provided `docker-compose.yml`, which pins the image to `v4.22.0`:

```sh
docker compose up -d
```

The scripts connect with the [`falkordb`](https://pypi.org/project/falkordb/) Python client and are configured via environment variables:

- `FALKORDB_HOST` (optional, defaults to `localhost`)
- `FALKORDB_PORT` (optional, defaults to `6379`; also sets the host port in `docker-compose.yml`)
- `FALKORDB_GRAPH` (optional, defaults to `ldbc_snb_sf1`)
- `FALKORDB_VERSION` (optional, Docker image tag, defaults to `v4.22.0`)

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
uv run --frozen pytest benchmark_query.py -k "not query30" \
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

`-k "not query30"` excludes Q30, which is timed separately (see below).

## Results

Measured on **2026-10-03** on an AMD Ryzen 9 6900HS (16 logical CPUs, 30 GiB RAM) running Linux 7.1.3 and Python 3.14.0, with FalkorDB 4.22.0 in Docker started from the provided `docker-compose.yml` (`THREAD_COUNT` and `OMP_THREAD_COUNT` 16, query timeout disabled, unlimited result set size). This is a different machine from the Apple M5 used for the other engines, so these numbers are not directly comparable with the main table.

[CLI output](../results/falkordb-4.22.0.txt) · [Raw benchmark JSON](../results/falkordb-4.22.0.json) · [Q30 runs](../results/falkordb-4.22.0-q30.txt)

Ingestion took 35 s for the 3,181,724 nodes, 710 s for the 17,256,038 relationships and 5 s for the secondary indexes. After loading, `GRAPH.MEMORY USAGE` reports 1.87 GB for the graph. The server's resident memory (RSS) stayed at about 2.1 GB during the query runs, and Redis's allocator peak during ingestion was 2.4 GB.

Q1–Q29 passed their result assertions. Apart from Q12 and Q16, every query averages under 17 ms. The slow queries come from the planner choosing a full label scan over a selective, indexed starting point:

- **Q12** (8,054 ms) scans all 2M `Comment` nodes and filters on `Place.name = "Berlin"` only at the end, instead of starting from the one indexed `Place`.
- **Q16** (105 ms) has the same shape over the 1M `Post` nodes for `Place.name = "Mumbai"`.
- **Q30** expands every `Post` to its creator and then to all of that creator's comments, about 447M candidate pairs, before checking `replyOfPost`. A single client-timed run took 1,281 s (21.3 min). Repeating it for at least five rounds was impractical, so Q30 is excluded from the timed suite.

The query text is identical to Neo4j's for all 30 queries. A semantically equivalent Q30 that matches `replyOfPost` first and checks `commentHasCreator` in a second `MATCH` (after `WITH c, creator`) returns the same result in 0.17 s on average over five runs; its text and timings are in the [Q30 runs](../results/falkordb-4.22.0-q30.txt) file. It is not used here because the other engines run the queries unmodified.
