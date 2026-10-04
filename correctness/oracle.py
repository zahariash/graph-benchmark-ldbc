"""Engine-independent expected results computed from the LDBC CSVs with polars.

A Cypher pattern is evaluated as a sequence of joins: every node variable is a
column of IDs, every relationship hop is an inner join with the edge table, and
a variable that already exists closes a cycle. Inner joins preserve bag
semantics, so ``count(*)`` is the row count and ``DISTINCT`` is ``unique()``.
"""

from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_ROOT = REPO_ROOT / "csv"

NODE_FILES = {
    "Comment": "dynamic/comment_0_0.csv",
    "Forum": "dynamic/forum_0_0.csv",
    "Person": "dynamic/person_0_0.csv",
    "Post": "dynamic/post_0_0.csv",
    "Organisation": "static/organisation_0_0.csv",
    "Place": "static/place_0_0.csv",
    "Tag": "static/tag_0_0.csv",
    "Tagclass": "static/tagclass_0_0.csv",
}

REL_FILES = {
    "containerOf": "dynamic/forum_containerOf_post_0_0.csv",
    "commentHasCreator": "dynamic/comment_hasCreator_person_0_0.csv",
    "postHasCreator": "dynamic/post_hasCreator_person_0_0.csv",
    "hasInterest": "dynamic/person_hasInterest_tag_0_0.csv",
    "hasMember": "dynamic/forum_hasMember_person_0_0.csv",
    "hasModerator": "dynamic/forum_hasModerator_person_0_0.csv",
    "commentHasTag": "dynamic/comment_hasTag_tag_0_0.csv",
    "forumHasTag": "dynamic/forum_hasTag_tag_0_0.csv",
    "postHasTag": "dynamic/post_hasTag_tag_0_0.csv",
    "hasType": "static/tag_hasType_tagclass_0_0.csv",
    "commentIsLocatedIn": "dynamic/comment_isLocatedIn_place_0_0.csv",
    "organisationIsLocatedIn": "static/organisation_isLocatedIn_place_0_0.csv",
    "personIsLocatedIn": "dynamic/person_isLocatedIn_place_0_0.csv",
    "postIsLocatedIn": "dynamic/post_isLocatedIn_place_0_0.csv",
    "isPartOf": "static/place_isPartOf_place_0_0.csv",
    "isSubclassOf": "static/tagclass_isSubclassOf_tagclass_0_0.csv",
    "knows": "dynamic/person_knows_person_0_0.csv",
    "likeComment": "dynamic/person_likes_comment_0_0.csv",
    "likePost": "dynamic/person_likes_post_0_0.csv",
    "replyOfComment": "dynamic/comment_replyOf_comment_0_0.csv",
    "replyOfPost": "dynamic/comment_replyOf_post_0_0.csv",
    "studyAt": "dynamic/person_studyAt_organisation_0_0.csv",
    "workAt": "dynamic/person_workAt_organisation_0_0.csv",
}

TOTAL_NODES = 3_181_724
TOTAL_RELS = 17_256_038

Rows = list[tuple]


class Data:
    def __init__(self, csv_root: Path = CSV_ROOT):
        self.csv_root = csv_root
        self._nodes: dict[str, pl.DataFrame] = {}
        self._rels: dict[str, pl.DataFrame] = {}

    def node_table(self, label: str) -> pl.DataFrame:
        if label not in self._nodes:
            self._nodes[label] = pl.read_csv(self.csv_root / NODE_FILES[label], separator="|")
        return self._nodes[label]

    def rel_table(self, rel: str) -> pl.DataFrame:
        """Edge table with columns src, dst and a unique eid per edge."""
        if rel not in self._rels:
            df = pl.read_csv(self.csv_root / REL_FILES[rel], separator="|", columns=[0, 1])
            src, dst = df.columns
            self._rels[rel] = df.rename({src: "src", dst: "dst"}).with_row_index("eid")
        return self._rels[rel]

    def nodes(self, label: str, var: str, where: pl.Expr | None = None) -> pl.DataFrame:
        """IDs of `label` nodes satisfying `where` (over raw CSV columns), as column `var`."""
        df = self.node_table(label)
        if where is not None:
            df = df.filter(where)
        return df.select(pl.col("id").alias(var))

    def where(self, df: pl.DataFrame, label: str, var: str, where: pl.Expr) -> pl.DataFrame:
        return df.join(self.nodes(label, var, where), on=var)

    def hop(
        self,
        df: pl.DataFrame | None,
        rel: str,
        src: str,
        dst: str,
        undirected: bool = False,
    ) -> pl.DataFrame:
        """Pattern (src)-[:rel]->(dst). Joins on whichever of src/dst already exist in df."""
        edges = self.rel_table(rel).select(pl.col("src").alias(src), pl.col("dst").alias(dst))
        if undirected:
            flipped = self.rel_table(rel).select(pl.col("dst").alias(src), pl.col("src").alias(dst))
            edges = pl.concat([edges, flipped])
        if df is None:
            return edges
        on = [c for c in (src, dst) if c in df.columns]
        return df.join(edges, on=on)

    def optional_hop(self, df: pl.DataFrame, rel: str, src: str, dst: str) -> pl.DataFrame:
        edges = self.rel_table(rel).select(pl.col("src").alias(src), pl.col("dst").alias(dst))
        on = [c for c in (src, dst) if c in df.columns]
        return df.join(edges, on=on, how="left")

    def props(self, df: pl.DataFrame, var: str, label: str, *names: str) -> pl.DataFrame:
        """Add columns `var.name` for each property name; keeps nulls for unmatched vars."""
        table = self.node_table(label).select(
            pl.col("id").alias(var), *[pl.col(n).alias(f"{var}.{n}") for n in names]
        )
        return df.join(table, on=var, how="left")

    def paths(
        self,
        rel: str,
        start: pl.DataFrame,
        lo: int,
        hi: int,
        undirected: bool = False,
        trail: bool = True,
        reverse: bool = False,
    ) -> pl.DataFrame:
        """Variable-length paths (start)-[:rel*lo..hi]->(end) as rows (start, end), one per path.

        trail=True forbids reusing an edge within a path (Neo4j/openCypher semantics);
        trail=False counts walks (Kuzu default). reverse=True follows edges dst->src.
        """
        edges = self.rel_table(rel)
        flipped = edges.select("eid", pl.col("dst").alias("src"), pl.col("src").alias("dst"))
        if undirected:
            edges = pl.concat([edges, flipped])
        elif reverse:
            edges = flipped
        frontier = start.select(pl.col(start.columns[0]).alias("start")).with_columns(end=pl.col("start"))
        collected = []
        for k in range(1, hi + 1):
            step = edges.select(pl.col("src").alias("end"), pl.col("dst").alias("next"), pl.col("eid").alias(f"e{k}"))
            frontier = frontier.join(step, on="end").drop("end").rename({"next": "end"})
            if trail and k > 1:
                fresh = [pl.col(f"e{k}") != pl.col(f"e{i}") for i in range(1, k)]
                frontier = frontier.filter(pl.all_horizontal(fresh))
            if k >= lo:
                collected.append(frontier.select("start", "end"))
        return pl.concat(collected)


def rows(df: pl.DataFrame) -> Rows:
    return df.rows()


def count(df: pl.DataFrame) -> Rows:
    return [(df.height,)]
