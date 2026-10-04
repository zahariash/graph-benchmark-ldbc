"""Expected results of the LDBC SNB Interactive v1 complex queries Q1-Q14, computed from the CSVs.

Each oracle returns the final rows (after ORDER BY and LIMIT) in the RETURN column order of
falkordb/query_complex14.py. Dates are the raw CSV strings, list columns are sorted tuples.
``knows`` is undirected everywhere; Message is Post and Comment.
"""

import sys
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise

import polars as pl

from correctness.oracle import REL_FILES, Data, Rows

c = pl.col

SAMIR = 2199023262543
RAFAEL = 2783

PARAMS: dict[int, dict] = {
    1: {"personId": SAMIR, "firstName": "Jose"},
    2: {"personId": SAMIR, "maxDate": "2010-10-16T12:00:00.000+0000"},
    3: {
        "personId": SAMIR,
        "countryXName": "Angola",
        "countryYName": "Colombia",
        "startDate": "2010-06-01T12:00:00.000+0000",
        "endDate": "2010-06-29T12:00:00.000+0000",
    },
    4: {"personId": SAMIR, "startDate": "2010-06-01T00:00:00.000+0000", "endDate": "2010-06-30T00:00:00.000+0000"},
    5: {"personId": SAMIR, "minDate": "2010-11-01T12:00:00.000+0000"},
    6: {"personId": SAMIR, "tagName": "Carl_Gustaf_Emil_Mannerheim"},
    7: {"personId": SAMIR},
    8: {"personId": 143},
    9: {"personId": SAMIR, "maxDate": "2010-11-16T12:00:00.000+0000"},
    10: {"personId": SAMIR, "month": 5},
    11: {"personId": SAMIR, "countryName": "Hungary", "workFromYear": 2011},
    12: {"personId": SAMIR, "tagClassName": "Monarch"},
    13: {"person1Id": SAMIR, "person2Id": RAFAEL},
    14: {"person1Id": SAMIR, "person2Id": RAFAEL},
}

# Extra Q13/Q14 pairs at knows distance 2, 3 and 4 (SAMIR and RAFAEL are direct friends)
PATH_PAIRS = [(933, 987), (933, 267), (933, 4598)]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def edge_table(d: Data, rel: str) -> pl.DataFrame:
    """Edge table with its properties; the first two columns renamed to src and dst."""
    df = pl.read_csv(d.csv_root / REL_FILES[rel], separator="|")
    src, dst = df.columns[:2]
    return df.rename({src: "src", dst: "dst"})


def edges(d: Data, rel: str, src: str, dst: str) -> pl.DataFrame:
    return d.rel_table(rel).select(c("src").alias(src), c("dst").alias(dst))


def knows(d: Data) -> pl.DataFrame:
    return pl.concat([edges(d, "knows", "a", "b"), edges(d, "knows", "b", "a").select("a", "b")])


def distances(d: Data, pid: int, max_hops: int | None = None) -> pl.DataFrame:
    """BFS over undirected knows: (person, dist) for every person within max_hops, start included."""
    adj = knows(d)
    seen = pl.DataFrame({"person": [pid], "dist": [0]}, schema={"person": pl.Int64, "dist": pl.Int64})
    frontier = seen.select("person")
    hops = 0
    while frontier.height and (max_hops is None or hops < max_hops):
        hops += 1
        frontier = (
            frontier.join(adj, left_on="person", right_on="a")
            .select(person=c("b"))
            .unique()
            .join(seen, on="person", how="anti")
        )
        seen = pl.concat([seen, frontier.with_columns(dist=pl.lit(hops, pl.Int64))])
    return seen


def circle(d: Data, pid: int, hops: int) -> pl.DataFrame:
    """Distinct persons at distance 1..hops, as column person."""
    return distances(d, pid, hops).filter(c("dist") > 0).select("person")


def friends(d: Data, pid: int) -> pl.DataFrame:
    return circle(d, pid, 1)


def names(d: Data, label: str, var: str, alias: str, kind: str | None = None) -> pl.DataFrame:
    """(var, alias) = (id, name) of `label` nodes, optionally restricted to one type."""
    df = d.node_table(label)
    if kind is not None:
        df = df.filter(c("type") == kind)
    return df.select(c("id").alias(var), c("name").alias(alias))


def persons(d: Data, *names: str) -> pl.DataFrame:
    return d.node_table("Person").select(c("id").alias("person"), *names)


def messages(d: Data) -> pl.DataFrame:
    """All Posts and Comments as (message, creator, creationDate, content)."""
    posts = d.node_table("Post").select(
        c("id").alias("message"), "creationDate", pl.coalesce("content", "imageFile").alias("content")
    )
    posts = posts.join(edges(d, "postHasCreator", "message", "creator"), on="message")
    comments = d.node_table("Comment").select(c("id").alias("message"), "creationDate", "content")
    comments = comments.join(edges(d, "commentHasCreator", "message", "creator"), on="message")
    return pl.concat([posts, comments.select(posts.columns)])


def place_ids(d: Data, name: str, kind: str) -> list[int]:
    return d.node_table("Place").filter((c("name") == name) & (c("type") == kind))["id"].to_list()


def epoch_ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp() * 1000)


def latest_messages(d: Data, people: pl.DataFrame, date_filter: pl.Expr) -> Rows:
    """Q2/Q9: latest 20 messages of `people` matching date_filter."""
    df = messages(d).filter(date_filter).join(people, left_on="creator", right_on="person")
    df = df.sort(["creationDate", "message"], descending=[True, False]).head(20)
    df = df.join(persons(d, "firstName", "lastName"), left_on="creator", right_on="person")
    df = df.sort(["creationDate", "message"], descending=[True, False])
    return df.select("creator", "firstName", "lastName", "message", "content", "creationDate").rows()


# ---------------------------------------------------------------------------
# Q1-Q14
# ---------------------------------------------------------------------------


def organisations(d: Data, people: list[int], rel: str, org_type: str, place_type: str, year: str) -> dict:
    """Per person: sorted tuple of (organisation name, year, place name)."""
    df = (
        edge_table(d, rel)
        .filter(c("src").is_in(people))
        .join(names(d, "Organisation", "dst", "org", org_type), on="dst")
        .join(edges(d, "organisationIsLocatedIn", "dst", "place"), on="dst")
        .join(names(d, "Place", "place", "placeName", place_type), on="place")
    )
    out = defaultdict(list)
    for person, name, y, place in df.select("src", "org", year, "placeName").iter_rows():
        out[person].append((name, y, place))
    return {person: tuple(sorted(entries)) for person, entries in out.items()}


def q1(d: Data) -> Rows:
    p = PARAMS[1]
    props = persons(d, "firstName", "lastName", "birthday", "creationDate", "gender", "browserUsed", "locationIP")
    df = distances(d, p["personId"], 3).filter(c("dist") > 0)
    df = df.join(props, on="person").filter(c("firstName") == p["firstName"])
    df = df.sort(["dist", "lastName", "person"]).head(20)
    df = df.join(edges(d, "personIsLocatedIn", "person", "city"), on="person")
    df = df.join(names(d, "Place", "city", "cityName", "city"), on="city")
    df = df.sort(["dist", "lastName", "person"])
    ids = df["person"].to_list()
    unis = organisations(d, ids, "studyAt", "university", "city", "classYear")
    companies = organisations(d, ids, "workAt", "company", "country", "workFrom")
    cols = ["person", "lastName", "dist", "birthday", "creationDate", "gender", "browserUsed", "locationIP", "cityName"]
    return [(*row, unis.get(row[0], ()), companies.get(row[0], ())) for row in df.select(cols).iter_rows()]


def q2(d: Data) -> Rows:
    p = PARAMS[2]
    return latest_messages(d, friends(d, p["personId"]), c("creationDate") <= p["maxDate"])


def q3(d: Data) -> Rows:
    p = PARAMS[3]
    (x,) = place_ids(d, p["countryXName"], "country")
    (y,) = place_ids(d, p["countryYName"], "country")
    excluded_cities = d.rel_table("isPartOf").filter(c("dst").is_in([x, y]))["src"].to_list()
    homes = edges(d, "personIsLocatedIn", "person", "city")
    people = circle(d, p["personId"], 2).join(homes, on="person").filter(~c("city").is_in(excluded_cities))
    located = pl.concat(
        [edges(d, "postIsLocatedIn", "message", "country"), edges(d, "commentIsLocatedIn", "message", "country")]
    )
    df = (
        messages(d)
        .filter((c("creationDate") >= p["startDate"]) & (c("creationDate") < p["endDate"]))
        .join(people.select("person"), left_on="creator", right_on="person")
        .join(located, on="message")
        .group_by("creator")
        .agg(xCount=(c("country") == x).sum().cast(pl.Int64), yCount=(c("country") == y).sum().cast(pl.Int64))
        .filter((c("xCount") > 0) & (c("yCount") > 0))
        .with_columns(xyCount=c("xCount") + c("yCount"))
        .sort(["xyCount", "creator"], descending=[True, False])
        .head(20)
    )
    df = df.join(persons(d, "firstName", "lastName"), left_on="creator", right_on="person")
    df = df.sort(["xyCount", "creator"], descending=[True, False])
    return df.select("creator", "firstName", "lastName", "xCount", "yCount", "xyCount").rows()


def q4(d: Data) -> Rows:
    p = PARAMS[4]
    posts = d.node_table("Post").select(c("id").alias("post"), "creationDate")
    df = (
        friends(d, p["personId"])
        .join(edges(d, "postHasCreator", "post", "person"), on="person")
        .join(edges(d, "postHasTag", "post", "tag"), on="post")
        .select("tag", "post")
        .unique()
        .join(posts, on="post")
        .group_by("tag")
        .agg(
            postCount=((c("creationDate") >= p["startDate"]) & (c("creationDate") < p["endDate"])).sum().cast(pl.Int64),
            invalid=(c("creationDate") < p["startDate"]).sum(),
        )
        .filter((c("postCount") > 0) & (c("invalid") == 0))
        .join(names(d, "Tag", "tag", "name"), on="tag")
        .sort(["postCount", "name"], descending=[True, False])
        .head(10)
    )
    return df.select("name", "postCount").rows()


def q5(d: Data) -> Rows:
    p = PARAMS[5]
    joined = (
        edge_table(d, "hasMember")
        .filter(c("joinDate") > p["minDate"])
        .select(c("src").alias("forum"), c("dst").alias("person"))
        .join(circle(d, p["personId"], 2), on="person")
    )
    posts = (
        edges(d, "containerOf", "forum", "post")
        .join(edges(d, "postHasCreator", "post", "person"), on="post")
        .join(joined, on=["forum", "person"])
        .group_by("forum")
        .agg(postCount=pl.len().cast(pl.Int64))
    )
    df = (
        joined.select("forum")
        .unique()
        .join(posts, on="forum", how="left")
        .with_columns(c("postCount").fill_null(0))
        .sort(["postCount", "forum"], descending=[True, False])
        .head(20)
    )
    df = df.join(d.node_table("Forum").select(c("id").alias("forum"), "title"), on="forum")
    df = df.sort(["postCount", "forum"], descending=[True, False])
    return df.select("title", "postCount").rows()


def q6(d: Data) -> Rows:
    p = PARAMS[6]
    tags = names(d, "Tag", "tag", "name")
    known = tags.filter(c("name") == p["tagName"])["tag"].to_list()
    has_tag = edges(d, "postHasTag", "post", "tag")
    df = (
        circle(d, p["personId"], 2)
        .join(edges(d, "postHasCreator", "post", "person"), on="person")
        .join(has_tag.filter(c("tag").is_in(known)).select("post"), on="post")
        .join(has_tag.filter(~c("tag").is_in(known)), on="post")
        .join(tags, on="tag")
        .group_by("name")
        .agg(postCount=pl.len().cast(pl.Int64))
        .sort(["postCount", "name"], descending=[True, False])
        .head(10)
    )
    return df.rows()


def q7(d: Data) -> Rows:
    pid = PARAMS[7]["personId"]
    likes = pl.concat([edge_table(d, "likePost"), edge_table(d, "likeComment")]).select(
        c("src").alias("liker"), c("dst").alias("message"), c("creationDate").alias("likeTime")
    )
    own = messages(d).filter(c("creator") == pid).drop("creator")
    df = (
        likes.join(own, on="message")
        .sort(["likeTime", "message"], descending=[True, False])
        .group_by("liker", maintain_order=True)
        .first()
        .sort(["likeTime", "liker"], descending=[True, False])
        .head(20)
    )
    df = df.join(persons(d, "firstName", "lastName"), left_on="liker", right_on="person")
    df = df.sort(["likeTime", "liker"], descending=[True, False])
    known = set(friends(d, pid)["person"].to_list())
    cols = ["liker", "firstName", "lastName", "likeTime", "message", "content", "creationDate"]
    return [
        (*row[:6], (epoch_ms(row[3]) - epoch_ms(row[6])) // 60000, row[0] not in known)
        for row in df.select(cols).iter_rows()
    ]


def q8(d: Data) -> Rows:
    pid = PARAMS[8]["personId"]
    own = messages(d).filter(c("creator") == pid).select(c("message").alias("parent"))
    replies = pl.concat([edges(d, "replyOfPost", "comment", "parent"), edges(d, "replyOfComment", "comment", "parent")])
    comments = d.node_table("Comment").select(c("id").alias("comment"), "creationDate", "content")
    df = (
        replies.join(own, on="parent")
        .join(comments, on="comment")
        .sort(["creationDate", "comment"], descending=[True, False])
        .head(20)
        .join(edges(d, "commentHasCreator", "comment", "person"), on="comment")
        .join(persons(d, "firstName", "lastName"), on="person")
        .sort(["creationDate", "comment"], descending=[True, False])
    )
    return df.select("person", "firstName", "lastName", "creationDate", "comment", "content").rows()


def q9(d: Data) -> Rows:
    p = PARAMS[9]
    return latest_messages(d, circle(d, p["personId"], 2), c("creationDate") < p["maxDate"])


def q10(d: Data) -> Rows:
    p = PARAMS[10]
    pid, month = p["personId"], p["month"]
    near = distances(d, pid, 1)["person"].to_list()
    candidates = (
        friends(d, pid)
        .join(knows(d), left_on="person", right_on="a")
        .select(person=c("b"))
        .unique()
        .filter(~c("person").is_in(near))
    )
    month_of, day_of = c("birthday").str.slice(5, 2).cast(pl.Int64), c("birthday").str.slice(8, 2).cast(pl.Int64)
    zodiac = ((month_of == month) & (day_of >= 21)) | ((month_of == month % 12 + 1) & (day_of < 22))
    df = (
        candidates.join(persons(d, "firstName", "lastName", "gender", "birthday"), on="person")
        .filter(zodiac)
        .join(edges(d, "personIsLocatedIn", "person", "city"), on="person")
        .join(names(d, "Place", "city", "cityName", "city"), on="city")
    )
    interests = edges(d, "hasInterest", "p", "tag").filter(c("p") == pid)["tag"].to_list()
    posts = edges(d, "postHasCreator", "post", "person").join(df.select("person"), on="person")
    common = edges(d, "postHasTag", "post", "tag").filter(c("tag").is_in(interests)).select("post").unique()
    counts = posts.group_by("person").agg(postCount=pl.len())
    common_counts = posts.join(common, on="post").group_by("person").agg(commonPostCount=pl.len())
    df = (
        df.join(counts, on="person", how="left")
        .join(common_counts, on="person", how="left")
        .with_columns(c("postCount", "commonPostCount").fill_null(0).cast(pl.Int64))
        .with_columns(score=2 * c("commonPostCount") - c("postCount"))
        .sort(["score", "person"], descending=[True, False])
        .head(10)
    )
    return df.select("person", "firstName", "lastName", "score", "gender", "cityName").rows()


def q11(d: Data) -> Rows:
    p = PARAMS[11]
    country = place_ids(d, p["countryName"], "country")
    df = (
        edge_table(d, "workAt")
        .filter(c("workFrom") < p["workFromYear"])
        .join(circle(d, p["personId"], 2), left_on="src", right_on="person")
        .join(names(d, "Organisation", "dst", "org", "company"), on="dst")
        .join(edges(d, "organisationIsLocatedIn", "dst", "place").filter(c("place").is_in(country)), on="dst")
        .sort(["workFrom", "src", "org"], descending=[False, False, True])
        .head(10)
        .join(persons(d, "firstName", "lastName"), left_on="src", right_on="person")
        .sort(["workFrom", "src", "org"], descending=[False, False, True])
    )
    return df.select("src", "firstName", "lastName", "org", "workFrom").rows()


def tags_of_class(d: Data, name: str) -> list[int]:
    """Tags whose type is the tag class `name` or one of its subclasses, plus tags named `name`."""
    classes = d.node_table("Tagclass").filter(c("name") == name).select(c("id").alias("cls"))
    sub = edges(d, "isSubclassOf", "child", "cls")
    frontier = classes
    while frontier.height:
        frontier = frontier.join(sub, on="cls").select(cls=c("child")).join(classes, on="cls", how="anti").unique()
        classes = pl.concat([classes, frontier])
    typed = edges(d, "hasType", "tag", "cls").join(classes, on="cls")["tag"]
    named = d.node_table("Tag").filter(c("name") == name)["id"]
    return pl.concat([typed, named]).unique().to_list()


def q12(d: Data) -> Rows:
    p = PARAMS[12]
    tags = names(d, "Tag", "tag", "name").filter(c("tag").is_in(tags_of_class(d, p["tagClassName"])))
    df = (
        friends(d, p["personId"])
        .join(edges(d, "commentHasCreator", "comment", "person"), on="person")
        .join(edges(d, "replyOfPost", "comment", "post"), on="comment")
        .join(edges(d, "postHasTag", "post", "tag"), on="post")
        .join(tags, on="tag")
        .group_by("person")
        .agg(tagNames=c("name").unique().sort(), replyCount=c("comment").n_unique().cast(pl.Int64))
        .sort(["replyCount", "person"], descending=[True, False])
        .head(20)
        .join(persons(d, "firstName", "lastName"), on="person")
        .sort(["replyCount", "person"], descending=[True, False])
    )
    return [
        (person, first, last, tuple(names), count)
        for person, first, last, names, count in df.select(
            "person", "firstName", "lastName", "tagNames", "replyCount"
        ).iter_rows()
    ]


def q13(d: Data) -> Rows:
    p = PARAMS[13]
    dist = distances(d, p["person1Id"]).filter(c("person") == p["person2Id"])["dist"]
    return [(dist.item() if dist.len() else -1,)]


def shortest_paths(d: Data, source: int, target: int) -> list[tuple[int, ...]]:
    """All shortest undirected knows paths from source to target, as node id tuples."""
    from_source = dict(distances(d, source).iter_rows())
    if target not in from_source:
        return []
    length = from_source[target]
    from_target = dict(distances(d, target, length).iter_rows())
    on_path = {v for v, k in from_source.items() if k + from_target.get(v, length + 1) == length}
    nexts = defaultdict(list)
    for a, b in knows(d).filter(c("a").is_in(on_path) & c("b").is_in(on_path)).iter_rows():
        if from_source[b] == from_source[a] + 1:
            nexts[a].append(b)

    def extend(path: tuple[int, ...]) -> list[tuple[int, ...]]:
        if path[-1] == target:
            return [path]
        return [full for b in nexts[path[-1]] for full in extend((*path, b))]

    return extend((source,))


def reply_weights(d: Data, people: set[int]) -> dict[frozenset, float]:
    """Interaction weight per unordered person pair: 1.0 per reply to a post, 0.5 per reply to a comment."""
    creators = edges(d, "commentHasCreator", "comment", "a")
    replies = [
        (edges(d, "replyOfPost", "comment", "parent"), edges(d, "postHasCreator", "parent", "b"), 1.0),
        (edges(d, "replyOfComment", "comment", "parent"), edges(d, "commentHasCreator", "parent", "b"), 0.5),
    ]
    weights = defaultdict(float)
    for reply, parent_creator, weight in replies:
        df = creators.filter(c("a").is_in(people)).join(reply, on="comment").join(parent_creator, on="parent")
        for a, b, n in df.filter(c("b").is_in(people)).group_by("a", "b").len().iter_rows():
            weights[frozenset((a, b))] += weight * n
    return weights


def q14(d: Data) -> Rows:
    p = PARAMS[14]
    paths = shortest_paths(d, p["person1Id"], p["person2Id"])
    weights = reply_weights(d, {v for path in paths for v in path})
    rows = [(path, sum((weights[frozenset(e)] for e in pairwise(path)), 0.0)) for path in paths]
    return sorted(rows, key=lambda row: -row[1])


EXPECTED: dict[int, Callable[[Data], Rows]] = {
    1: q1,
    2: q2,
    3: q3,
    4: q4,
    5: q5,
    6: q6,
    7: q7,
    8: q8,
    9: q9,
    10: q10,
    11: q11,
    12: q12,
    13: q13,
    14: q14,
}

# Q14 orders by pathWeight only, so equal weights may come back in any order
ORDERED = set(EXPECTED) - {14}

# Columns holding collect() results, whose element order is unspecified
SORTED_LISTS = {1: (9, 10), 12: (3,)}


def normalize(value):
    """Engine value -> oracle value: CSV date strings, tuples for lists, maps and structs."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}+0000"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, dict):
        return tuple(normalize(v) for v in value.values())
    if isinstance(value, list):
        return tuple(normalize(v) for v in value)
    return value


def normalize_row(idx: int, row) -> tuple:
    values = [normalize(v) for v in row]
    for col in SORTED_LISTS.get(idx, ()):
        if values[col] is not None:
            values[col] = tuple(sorted(values[col]))
    return tuple(values)


if __name__ == "__main__":
    selected = [int(i) for i in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(EXPECTED)
    data = Data()
    total = time.perf_counter()
    for idx in selected:
        start = time.perf_counter()
        result = EXPECTED[idx](data)
        print(f"\nQ{idx}: {len(result)} rows in {time.perf_counter() - start:.2f}s")
        for row in result[:3]:
            print(f"  {row}")
    print(f"\nTotal {time.perf_counter() - total:.2f}s")
