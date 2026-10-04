"""Correctness checks: one canonical Cypher text (Neo4j dialect) and one polars oracle each.

Engine-specific query texts live in each engine's correctness_query.py (OVERRIDES).
"""

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from correctness.oracle import Data, Rows, count, rows

c = pl.col


@dataclass(frozen=True)
class Check:
    name: str
    cypher: str
    expected: Callable[[Data], Rows]
    ordered: bool = False


CHECKS: list[Check] = []


def check(name, cypher, ordered=False):
    def register(fn):
        CHECKS.append(Check(name, cypher, fn, ordered))
        return fn

    return register


def persons_named(d: Data, var: str, first: str, last: str) -> pl.DataFrame:
    return d.nodes("Person", var, (c("firstName") == first) & (c("lastName") == last))


# ---------------------------------------------------------------------------
# B: the 30 benchmark queries expanded to full result sets
# (COUNT(...) [> 0] -> the counted values, LIMIT dropped, ORDER BY dropped)
# ---------------------------------------------------------------------------


@check(
    "B01",
    """
    MATCH (p:Person)-[:personIsLocatedIn]->(pl:Place),
          (p)-[:hasInterest]->(t:Tag)
    WHERE pl.name = "Glasgow" AND t.name = "Napoleon"
    RETURN p.firstName, p.lastName
    """,
)
def q1(d: Data):
    "Q1 names of Glasgow persons interested in Napoleon"
    df = d.nodes("Place", "pl", c("name") == "Glasgow")
    df = d.hop(df, "personIsLocatedIn", "p", "pl")
    df = d.hop(df, "hasInterest", "p", "t")
    df = d.where(df, "Tag", "t", c("name") == "Napoleon")
    return rows(d.props(df, "p", "Person", "firstName", "lastName").select("p.firstName", "p.lastName"))


@check(
    "B02",
    """
    MATCH (p:Person)<-[:postHasCreator]-(post:Post)
    WHERE p.firstName = "Lei" AND p.lastName = "Zhang"
      AND post.content CONTAINS "Zulu"
    RETURN post.ID
    """,
)
def q2(d: Data):
    "Q2 posts by Lei Zhang containing Zulu"
    df = d.hop(persons_named(d, "p", "Lei", "Zhang"), "postHasCreator", "post", "p")
    df = d.where(df, "Post", "post", c("content").str.contains("Zulu", literal=True))
    return rows(df.select("post"))


@check(
    "B03",
    """
    MATCH (post:Post {ID: 962077547172})-[:postHasCreator]->(person:Person),
          (person)-[:studyAt]->(org:Organisation)
    RETURN person.firstName, person.lastName, org.name
    """,
)
def q3(d: Data):
    "Q3 creator of post 962077547172 and their universities"
    df = d.nodes("Post", "post", c("id") == 962077547172)
    df = d.hop(df, "postHasCreator", "post", "person")
    df = d.hop(df, "studyAt", "person", "org")
    df = d.props(df, "person", "Person", "firstName", "lastName")
    df = d.props(df, "org", "Organisation", "name")
    return rows(df.select("person.firstName", "person.lastName", "org.name"))


@check(
    "B04",
    """
    MATCH (p:Person)<-[:commentHasCreator]-(c:Comment)
    WHERE p.firstName = "Alfredo"
      AND p.lastName = "Gomez"
      AND c.length > 100
    RETURN c.ID
    """,
)
def q4(d: Data):
    "Q4 comments by Alfredo Gomez longer than 100"
    df = d.hop(persons_named(d, "p", "Alfredo", "Gomez"), "commentHasCreator", "c", "p")
    df = d.where(df, "Comment", "c", c("length") > 100)
    return rows(df.select("c"))


@check(
    "B05",
    """
    MATCH (f:Forum)-[:hasMember]->(p:Person)
    WHERE f.title CONTAINS "John Brown"
      AND p.lastName CONTAINS "Choi"
    RETURN DISTINCT p.firstName, p.lastName
    """,
)
def q5(d: Data):
    "Q5 distinct Choi members of John Brown forums (LIMIT dropped)"
    df = d.nodes("Forum", "f", c("title").str.contains("John Brown", literal=True))
    df = d.hop(df, "hasMember", "f", "p")
    df = d.where(df, "Person", "p", c("lastName").str.contains("Choi", literal=True))
    df = d.props(df, "p", "Person", "firstName", "lastName")
    return rows(df.select("p.firstName", "p.lastName").unique())


@check(
    "B06",
    """
    MATCH (p:Person)-[:workAt]->(o:Organisation)
    WHERE o.name = "Nova_Air" AND p.lastName CONTAINS "Bravo"
    RETURN p.ID
    """,
)
def q6(d: Data):
    "Q6 Nova_Air employees whose last name contains Bravo"
    df = d.hop(d.nodes("Organisation", "o", c("name") == "Nova_Air"), "workAt", "p", "o")
    df = d.where(df, "Person", "p", c("lastName").str.contains("Bravo", literal=True))
    return rows(df.select("p"))


Q7 = """
    MATCH (p:Person {ID: %d})<-[:commentHasCreator]-(c:Comment)
          -[:replyOfPost]->(post:Post)-[:postHasTag]->(t:Tag),
          (c)-[:commentIsLocatedIn]->(place:Place)
    WHERE t.name = "%s"
    RETURN DISTINCT place.name
    """


def q7_shape(d: Data, person: int, tag: str) -> Rows:
    df = d.hop(d.nodes("Person", "p", c("id") == person), "commentHasCreator", "c", "p")
    df = d.hop(df, "replyOfPost", "c", "post")
    df = d.hop(df, "postHasTag", "post", "t")
    df = d.where(df, "Tag", "t", c("name") == tag)
    df = d.hop(df, "commentIsLocatedIn", "c", "place")
    return rows(d.props(df, "place", "Place", "name").select("place.name").unique())


@check("B07", Q7 % (1786706544494, "Jamaica"))
def q7(d: Data):
    "Q7 places where person 1786706544494 commented on Jamaica posts (empty)"
    return q7_shape(d, 1786706544494, "Jamaica")


Q8 = """
    MATCH (p:Person)<-[:hasModerator]-(f:Forum)
    WHERE date(p.birthday) > date("1990-01-01")
      AND f.title CONTAINS "Emilio Fernandez"
    RETURN DISTINCT p.ID
    """


@check("B08", Q8)
def q8(d: Data):
    "Q8 moderators born after 1990 of Emilio Fernandez forums"
    df = d.nodes("Forum", "f", c("title").str.contains("Emilio Fernandez", literal=True))
    df = d.hop(df, "hasModerator", "f", "p")
    df = d.where(df, "Person", "p", c("birthday").str.to_date() > pl.date(1990, 1, 1))
    return rows(df.select("p").unique())


@check(
    "B09",
    """
    MATCH (p:Person)-[:knows]->(p2:Person)-[:studyAt]->(o:Organisation)
          -[:organisationIsLocatedIn]->(l:Place)
    WHERE l.name = "Tallinn" AND p.lastName = "Johansson"
    RETURN p.ID, p.firstName, p.lastName
    """,
)
def q9(d: Data):
    "Q9 Johanssons who know someone who studied in Tallinn"
    df = d.hop(d.nodes("Person", "p", c("lastName") == "Johansson"), "knows", "p", "p2")
    df = d.hop(df, "studyAt", "p2", "o")
    df = d.hop(df, "organisationIsLocatedIn", "o", "l")
    df = d.where(df, "Place", "l", c("name") == "Tallinn")
    return rows(d.props(df, "p", "Person", "firstName", "lastName").select("p", "p.firstName", "p.lastName"))


@check(
    "B10",
    """
    MATCH (c:Comment)-[:replyOfPost]->(post:Post)-[:postHasTag]->(t:Tag),
          (c)-[:commentHasCreator]->(p:Person)
    WHERE t.name = "Cate_Blanchett"
    RETURN DISTINCT p.ID
    """,
)
def q10(d: Data):
    "Q10 persons who commented on Cate_Blanchett posts"
    df = d.hop(d.nodes("Tag", "t", c("name") == "Cate_Blanchett"), "postHasTag", "post", "t")
    df = d.hop(df, "replyOfPost", "c", "post")
    df = d.hop(df, "commentHasCreator", "c", "p")
    return rows(df.select("p").unique())


@check(
    "B11",
    """
    MATCH (p:Person)-[:workAt]->(o:Organisation)
    WHERE o.type <> "university"
    RETURN COUNT(DISTINCT p.ID) AS num_e, o.name
    """,
)
def q11(d: Data):
    "Q11 employees per non-university organisation (all groups, LIMIT dropped)"
    df = d.hop(d.nodes("Organisation", "o", c("type") != "university"), "workAt", "p", "o")
    df = d.props(df, "o", "Organisation", "name").group_by("o.name").agg(pl.col("p").n_unique().alias("num_e"))
    return rows(df.select("num_e", "o.name"))


@check(
    "B12",
    """
    MATCH (c:Comment)-[:commentHasCreator]->(p:Person)-[:personIsLocatedIn]->(l:Place)
    WHERE c.content IS NOT NULL AND l.name = "Berlin"
    RETURN DISTINCT c.ID
    """,
)
def q12(d: Data):
    "Q12 comments with content by Berlin persons (IDs instead of count)"
    df = d.hop(d.nodes("Place", "l", c("name") == "Berlin"), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "commentHasCreator", "c", "p")
    df = d.where(df, "Comment", "c", c("content").is_not_null())
    return rows(df.select("c").unique())


@check(
    "B13",
    """
    MATCH (p:Person)<-[:commentHasCreator]-(c:Comment)<-[:likeComment]-(p2:Person)
    WHERE p.firstName = "Rafael" AND p.lastName = "Alonso"
    RETURN DISTINCT p2.ID
    """,
)
def q13(d: Data):
    "Q13 persons who liked Rafael Alonso's comments"
    df = d.hop(persons_named(d, "p", "Rafael", "Alonso"), "commentHasCreator", "c", "p")
    df = d.hop(df, "likeComment", "p2", "c")
    return rows(df.select("p2").unique())


@check(
    "B14",
    """
    MATCH (f:Forum)-[:forumHasTag]->(:Tag)-[:hasType]->(:Tagclass {name: "Athlete"})
    RETURN DISTINCT f.ID
    """,
)
def q14(d: Data):
    "Q14 forums tagged with an Athlete tag"
    df = d.hop(d.nodes("Tagclass", "tc", c("name") == "Athlete"), "hasType", "t", "tc")
    df = d.hop(df, "forumHasTag", "f", "t")
    return rows(df.select("f").unique())


@check(
    "B15",
    """
    MATCH (f:Forum)-[:hasModerator]->(p:Person)-[:workAt]->(o:Organisation)
    WHERE o.name = "Air_Tanzania"
    RETURN DISTINCT f.ID
    """,
)
def q15(d: Data):
    "Q15 forums moderated by Air_Tanzania employees"
    df = d.hop(d.nodes("Organisation", "o", c("name") == "Air_Tanzania"), "workAt", "p", "o")
    df = d.hop(df, "hasModerator", "f", "p")
    return rows(df.select("f").unique())


@check(
    "B16",
    """
    MATCH (p:Person)-[:personIsLocatedIn]->(l:Place),
          (p)<-[:postHasCreator]-(post:Post)
    WHERE l.name = "Mumbai" AND post.content CONTAINS "Copernicus"
    RETURN post.ID
    """,
)
def q16(d: Data):
    "Q16 Copernicus posts by Mumbai persons (bag of IDs, as COUNT(post.ID))"
    df = d.hop(d.nodes("Place", "l", c("name") == "Mumbai"), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "postHasCreator", "post", "p")
    df = d.where(df, "Post", "post", c("content").str.contains("Copernicus", literal=True))
    return rows(df.select("post"))


@check(
    "B17",
    """
    MATCH (p:Person)-[:studyAt]->(o:Organisation), (p)-[:hasInterest]->(t:Tag)
    WHERE o.name = "Indian_Institute_of_Science"
    RETURN t.name, COUNT(*) AS tag_count
    """,
)
def q17(d: Data):
    "Q17 interest tag counts of Indian_Institute_of_Science students (all groups)"
    df = d.hop(d.nodes("Organisation", "o", c("name") == "Indian_Institute_of_Science"), "studyAt", "p", "o")
    df = d.hop(df, "hasInterest", "p", "t")
    df = d.props(df, "t", "Tag", "name").group_by("t.name").len("tag_count")
    return rows(df)


@check(
    "B18",
    """
    MATCH (p:Person)-[:studyAt]->(o:Organisation), (p)-[:hasInterest]->(t:Tag)
    WHERE o.name = "The_Oxford_Educational_Institutions"
      AND t.name = "William_Shakespeare"
    RETURN DISTINCT p.ID
    """,
)
def q18(d: Data):
    "Q18 Oxford students interested in William_Shakespeare"
    df = d.hop(d.nodes("Organisation", "o", c("name") == "The_Oxford_Educational_Institutions"), "studyAt", "p", "o")
    df = d.hop(df, "hasInterest", "p", "t")
    df = d.where(df, "Tag", "t", c("name") == "William_Shakespeare")
    return rows(df.select("p").unique())


@check(
    "B19",
    """
    MATCH (c:Comment)-[:commentHasTag]->(t:Tag), (c)-[:commentIsLocatedIn]->(l:Place)
    WHERE t.name CONTAINS "Copernicus"
    RETURN l.name, COUNT(c.ID) AS comment_count
    """,
)
def q19(d: Data):
    "Q19 comment counts per place for Copernicus-tagged comments (all groups)"
    df = d.hop(d.nodes("Tag", "t", c("name").str.contains("Copernicus", literal=True)), "commentHasTag", "c", "t")
    df = d.hop(df, "commentIsLocatedIn", "c", "l")
    df = d.props(df, "l", "Place", "name").group_by("l.name").len("comment_count")
    return rows(df)


@check(
    "B20",
    """
    MATCH (c:Comment)
    WHERE c.content CONTAINS "World War II" AND c.length > 1000
    RETURN c.ID
    """,
)
def q20(d: Data):
    "Q20 long comments containing World War II"
    df = d.nodes("Comment", "c", c("content").str.contains("World War II", literal=True) & (c("length") > 1000))
    return rows(df)


@check(
    "B21",
    """
    MATCH (p:Post)<-[:likePost]-(p2:Person)
    WHERE p2.firstName = "Bill" AND p2.lastName = "Moore"
      AND p.ID = 1649268446863
    RETURN p.ID
    """,
)
def q21(d: Data):
    "Q21 Bill Moore likes of post 1649268446863 (bag of post IDs)"
    df = d.hop(persons_named(d, "p2", "Bill", "Moore"), "likePost", "p2", "p")
    return rows(df.filter(c("p") == 1649268446863).select("p"))


@check(
    "B22",
    """
    MATCH (p:Person)-[:workAt]->(o:Organisation),
          (c:Comment)-[:replyOfPost]->(post:Post),
          (c)-[:commentHasCreator]->(p)
    WHERE o.name = "Linxair"
    RETURN DISTINCT c.ID
    """,
)
def q22(d: Data):
    "Q22 comments replying to posts by Linxair employees"
    df = d.hop(d.nodes("Organisation", "o", c("name") == "Linxair"), "workAt", "p", "o")
    df = d.hop(df, "commentHasCreator", "c", "p")
    df = d.hop(df, "replyOfPost", "c", "post")
    return rows(df.select("c").unique())


@check(
    "B23",
    """
    MATCH (p:Person)<-[:hasModerator]-(f:Forum)-[:forumHasTag]->(t:Tag)
    WHERE t.name = "Norah_Jones" AND p.lastName = "Gurung"
    RETURN DISTINCT p.ID
    """,
)
def q23(d: Data):
    "Q23 Gurung moderators of Norah_Jones forums"
    df = d.hop(d.nodes("Tag", "t", c("name") == "Norah_Jones"), "forumHasTag", "f", "t")
    df = d.hop(df, "hasModerator", "f", "p")
    df = d.where(df, "Person", "p", c("lastName") == "Gurung")
    return rows(df.select("p").unique())


Q24 = """
    MATCH (p:Person)-[:personIsLocatedIn]->(l:Place), (p)-[:hasInterest]->(t:Tag)
    WHERE l.name = "%s" AND t.name = "Cate_Blanchett"
    RETURN DISTINCT p.ID
    """


def q24_shape(d: Data, place: str) -> Rows:
    df = d.hop(d.nodes("Place", "l", c("name") == place), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "hasInterest", "p", "t")
    df = d.where(df, "Tag", "t", c("name") == "Cate_Blanchett")
    return rows(df.select("p").unique())


@check("B24", Q24 % "Paris")
def q24(d: Data):
    "Q24 Paris persons interested in Cate_Blanchett (empty)"
    return q24_shape(d, "Paris")


Q25 = """
    MATCH (amit:Person)-[:knows]->(p2:Person)-[:studyAt]->(o:Organisation)
    WHERE amit.firstName = "Amit" AND amit.lastName = "Singh"
      AND o.name = "%s"
    RETURN DISTINCT p2.ID
    """


def q25_shape(d: Data, org: str) -> Rows:
    df = d.hop(persons_named(d, "amit", "Amit", "Singh"), "knows", "amit", "p2")
    df = d.hop(df, "studyAt", "p2", "o")
    df = d.where(df, "Organisation", "o", c("name") == org)
    return rows(df.select("p2").unique())


@check("B25", Q25 % "MIT_School_of_Engineering")
def q25(d: Data):
    "Q25 friends of Amit Singh who studied at MIT_School_of_Engineering (empty)"
    return q25_shape(d, "MIT_School_of_Engineering")


Q26 = """
    MATCH (f:Forum)-[:hasMember]->(p:Person), (f)-[:forumHasTag]->(t:Tag)
    WHERE p.ID = 10995116287854 AND t.name = "%s"
    RETURN DISTINCT f.ID
    """


def q26_shape(d: Data, tag: str) -> Rows:
    df = d.hop(d.nodes("Person", "p", c("id") == 10995116287854), "hasMember", "f", "p")
    df = d.hop(df, "forumHasTag", "f", "t")
    df = d.where(df, "Tag", "t", c("name") == tag)
    return rows(df.select("f").unique())


@check("B26", Q26 % "Benjamin_Franklin")
def q26(d: Data):
    "Q26 Benjamin_Franklin forums of person 10995116287854 (empty)"
    return q26_shape(d, "Benjamin_Franklin")


@check(
    "B27",
    """
    MATCH (c:Comment)-[:commentHasCreator]->(p:Person),
          (p)-[:personIsLocatedIn]->(l:Place),
          (c)-[:commentHasTag]->(t:Tag)
    WHERE l.name = "Toronto" AND t.name = "Winston_Churchill"
    RETURN DISTINCT c.ID
    """,
)
def q27(d: Data):
    "Q27 Winston_Churchill comments by Toronto persons"
    df = d.hop(d.nodes("Place", "l", c("name") == "Toronto"), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "commentHasCreator", "c", "p")
    df = d.hop(df, "commentHasTag", "c", "t")
    df = d.where(df, "Tag", "t", c("name") == "Winston_Churchill")
    return rows(df.select("c").unique())


@check(
    "B28",
    """
    MATCH (t:Tag)-[:hasType]->(tc:Tagclass),
          (p:Person)-[:hasInterest]->(t),
          (p)-[:personIsLocatedIn]->(l:Place)
    WHERE tc.name = "BritishRoyalty" AND l.name = "Manila"
    RETURN DISTINCT p.ID
    """,
)
def q28(d: Data):
    "Q28 Manila persons interested in BritishRoyalty tags"
    df = d.hop(d.nodes("Tagclass", "tc", c("name") == "BritishRoyalty"), "hasType", "t", "tc")
    df = d.hop(df, "hasInterest", "p", "t")
    df = d.hop(df, "personIsLocatedIn", "p", "l")
    df = d.where(df, "Place", "l", c("name") == "Manila")
    return rows(df.select("p").unique())


Q29 = """
    MATCH (p:Person)<-[:postHasCreator]-(post:Post)
    WHERE p.firstName = "Justine" AND p.lastName = "Fenter"
      AND post.browserUsed CONTAINS "%s"
    RETURN post.ID
    """


def q29_shape(d: Data, browser: str) -> Rows:
    df = d.hop(persons_named(d, "p", "Justine", "Fenter"), "postHasCreator", "post", "p")
    df = d.where(df, "Post", "post", c("browserUsed").str.contains(browser, literal=True))
    return rows(df.select("post"))


@check("B29", Q29 % "Safari")
def q29(d: Data):
    "Q29 Safari posts by Justine Fenter (empty)"
    return q29_shape(d, "Safari")


@check(
    "B30",
    """
    MATCH (c:Comment)-[:commentHasCreator]->(creator:Person),
          (c)-[:replyOfPost]->(post:Post)-[:postHasCreator]->(creator)
    RETURN DISTINCT c.ID
    """,
)
def q30(d: Data):
    "Q30 comments replying to a post by their own creator"
    df = d.hop(None, "replyOfPost", "c", "post")
    df = d.hop(df, "postHasCreator", "post", "creator")
    df = d.hop(df, "commentHasCreator", "c", "creator")
    return rows(df.select("c").unique())


# ---------------------------------------------------------------------------
# N: non-empty variants of the empty-result benchmark queries
# ---------------------------------------------------------------------------


@check("N07", Q7 % (933, "Josip_Broz_Tito"))
def n7(d: Data):
    "Q7 shape with person 933 / tag Josip_Broz_Tito"
    return q7_shape(d, 933, "Josip_Broz_Tito")


@check("N24", Q24 % "Cenxi")
def n24(d: Data):
    "Q24 shape with place Cenxi"
    return q24_shape(d, "Cenxi")


@check("N25", Q25 % "Rajiv_Gandhi_University_of_Health_Sciences")
def n25(d: Data):
    "Q25 shape with Rajiv_Gandhi_University_of_Health_Sciences"
    return q25_shape(d, "Rajiv_Gandhi_University_of_Health_Sciences")


@check("N26", Q26 % "Herman_Melville")
def n26(d: Data):
    "Q26 shape with tag Herman_Melville"
    return q26_shape(d, "Herman_Melville")


@check("N29", Q29 % "Chrome")
def n29(d: Data):
    "Q29 shape with browser Chrome"
    return q29_shape(d, "Chrome")


# ---------------------------------------------------------------------------
# M: fixed-length multi-hop multiplicity and direction
# ---------------------------------------------------------------------------


def two_hop(d: Data, start: int, undirected: bool = False) -> pl.DataFrame:
    df = d.hop(d.nodes("Person", "p", c("id") == start), "knows", "p", "m", undirected)
    return d.hop(df, "knows", "m", "f", undirected)


@check(
    "M01",
    "MATCH (p:Person {ID: 933})-[:knows]->(m:Person)-[:knows]->(f:Person) RETURN count(*) AS n",
)
def m1(d: Data):
    "directed 2-hop knows from 933, named intermediate: count(*)"
    return count(two_hop(d, 933))


@check(
    "M02",
    "MATCH (p:Person {ID: 933})-[:knows]->(:Person)-[:knows]->(f:Person) RETURN count(*) AS n",
)
def m2(d: Data):
    "directed 2-hop knows from 933, anonymous intermediate: count(*)"
    return count(two_hop(d, 933))


@check(
    "M03",
    "MATCH (p:Person {ID: 933})-[:knows]->(m:Person)-[:knows]->(f:Person) RETURN DISTINCT f.ID",
)
def m3(d: Data):
    "directed 2-hop knows from 933: DISTINCT endpoints"
    return rows(two_hop(d, 933).select("f").unique())


@check("M04", "MATCH (p:Person {ID: 2783})-[:knows]-(f:Person) RETURN f.ID")
def m4(d: Data):
    "undirected 1-hop knows from 2783 (736 out, 10 in): bag of endpoints"
    df = d.hop(d.nodes("Person", "p", c("id") == 2783), "knows", "p", "f", undirected=True)
    return rows(df.select("f"))


@check(
    "M05",
    "MATCH (p:Person {ID: 2783})-[:knows]-(m:Person)-[:knows]-(f:Person) WHERE f.ID <> 2783 RETURN count(*) AS n",
)
def m5(d: Data):
    "undirected 2-hop knows from 2783 excluding start: count(*) (walk = trail)"
    return count(two_hop(d, 2783, undirected=True).filter(c("f") != 2783))


@check(
    "M06",
    "MATCH (p:Person {ID: 2783})-[:knows]-(m:Person)-[:knows]-(f:Person) RETURN count(*) AS n",
)
def m6(d: Data):
    "undirected 2-hop knows from 2783 without filter: count(*) (relationship uniqueness)"
    df = two_hop(d, 2783, undirected=True)
    return count(df.filter(c("f") != 2783))


def m6_walk(d: Data):
    "M06 under walk semantics, where a path may reuse a relationship"
    return count(two_hop(d, 2783, undirected=True))


# ---------------------------------------------------------------------------
# V: variable-length paths
# ---------------------------------------------------------------------------


def person(d: Data, pid: int) -> pl.DataFrame:
    return d.nodes("Person", "p", c("id") == pid)


@check(
    "V01",
    "MATCH (p:Person {ID: 933})-[:knows*1..2]->(f:Person) RETURN DISTINCT f.ID",
)
def v1(d: Data):
    "knows*1..2 directed from 933: DISTINCT endpoints"
    return rows(d.paths("knows", person(d, 933), 1, 2).select("end").unique())


@check("V02", "MATCH (p:Person {ID: 933})-[:knows*2..2]->(f:Person) RETURN f.ID")
def v2(d: Data):
    "knows*2..2 directed from 933, no endpoint filter: bag of endpoints (one per path)"
    return rows(d.paths("knows", person(d, 933), 2, 2).select("end"))


@check(
    "V03",
    "MATCH (p:Person {ID: 933})-[:knows*2..2]->(f:Person) WHERE f.ID <> 933 RETURN f.ID",
)
def v3(d: Data):
    "knows*2..2 directed from 933 with endpoint filter f.ID <> 933: bag of endpoints"
    return rows(d.paths("knows", person(d, 933), 2, 2).filter(c("end") != 933).select("end"))


@check(
    "V04",
    'MATCH (p:Person {ID: 933})-[:knows*3..3]->(f:Person) WHERE f.gender = "female" RETURN count(*) AS n',
)
def v4(d: Data):
    "knows*3..3 directed from 933 with endpoint property filter: count(*)"
    df = d.paths("knows", person(d, 933), 3, 3)
    return count(d.where(df, "Person", "end", c("gender") == "female"))


@check(
    "V05",
    "MATCH (p:Person {ID: 933})-[:knows*1..3]-(f:Person) WHERE f.ID <> 933 RETURN DISTINCT f.ID",
)
def v5(d: Data):
    "knows*1..3 undirected from 933 excluding start: DISTINCT endpoints"
    df = d.paths("knows", person(d, 933), 1, 3, undirected=True)
    return rows(df.filter(c("end") != 933).select("end").unique())


@check(
    "V06",
    "MATCH (p:Person {ID: 933})-[:knows*1..3]-(f:Person) WHERE f.ID <> 933 RETURN count(*) AS n",
)
def v6(d: Data):
    "knows*1..3 undirected from 933 excluding start: path count under TRAIL semantics"
    df = d.paths("knows", person(d, 933), 1, 3, undirected=True, trail=True)
    return count(df.filter(c("end") != 933))


@check(
    "V07",
    """
    MATCH (c:Comment)-[:replyOfComment*1..10]->(c2:Comment)-[:replyOfPost]->(post:Post {ID: 962075397334})
    RETURN c.ID, c2.ID
    """,
)
def v7(d: Data):
    "replyOfComment*1..10 chains into post 962075397334 (tree: path count unambiguous)"
    df = d.hop(d.nodes("Post", "post", c("id") == 962075397334), "replyOfPost", "c2", "post")
    paths = d.paths("replyOfComment", df.select("c2"), 1, 10, reverse=True)
    return rows(paths.select(pl.col("end").alias("c"), pl.col("start").alias("c2")))


@check(
    "V08",
    'MATCH (pl:Place {name: "Glasgow"})-[:isPartOf*1..3]->(x:Place) RETURN x.name',
)
def v8(d: Data):
    "isPartOf*1..3 from Glasgow"
    start = d.nodes("Place", "pl", c("name") == "Glasgow")
    df = d.paths("isPartOf", start, 1, 3).rename({"end": "x"})
    return rows(d.props(df, "x", "Place", "name").select("x.name"))


@check(
    "V09",
    'MATCH (tc:Tagclass)-[:isSubclassOf*1..10]->(root:Tagclass {name: "Thing"}) RETURN tc.name',
)
def v9(d: Data):
    "isSubclassOf*1..10 closure below Tagclass Thing"
    df = d.paths("isSubclassOf", d.nodes("Tagclass", "tc"), 1, 10).rename({"start": "tc", "end": "root"})
    df = d.where(df, "Tagclass", "root", c("name") == "Thing")
    return rows(d.props(df, "tc", "Tagclass", "name").select("tc.name"))


# ---------------------------------------------------------------------------
# O: OPTIONAL MATCH
# ---------------------------------------------------------------------------


@check(
    "O01",
    """
    MATCH (p:Person) WHERE p.lastName = "Johansson"
    OPTIONAL MATCH (p)-[:workAt]->(o:Organisation)
    RETURN p.ID, o.name
    """,
)
def o1(d: Data):
    "OPTIONAL MATCH workAt for Johanssons (nulls kept)"
    df = d.optional_hop(d.nodes("Person", "p", c("lastName") == "Johansson"), "workAt", "p", "o")
    return rows(d.props(df, "o", "Organisation", "name").select("p", "o.name"))


@check(
    "O02",
    """
    MATCH (p:Person) WHERE p.firstName = "Hans"
    OPTIONAL MATCH (p)-[:knows]->(k:Person)
    RETURN p.ID, count(k.ID) AS n
    """,
)
def o2(d: Data):
    "OPTIONAL MATCH knows for persons named Hans: count(k.ID) with zeros"
    df = d.optional_hop(d.nodes("Person", "p", c("firstName") == "Hans"), "knows", "p", "k")
    return rows(df.group_by("p").agg(pl.col("k").count().alias("n")))


@check(
    "O03",
    """
    MATCH (p:Person) WHERE p.lastName = "Choi"
    OPTIONAL MATCH (p)-[:studyAt]->(u:Organisation)
    OPTIONAL MATCH (p)-[:workAt]->(w:Organisation)
    RETURN p.ID, u.name, w.name
    """,
)
def o3(d: Data):
    "chained OPTIONAL MATCH studyAt and workAt for Chois"
    df = d.optional_hop(d.nodes("Person", "p", c("lastName") == "Choi"), "studyAt", "p", "u")
    df = d.optional_hop(df, "workAt", "p", "w")
    df = d.props(d.props(df, "u", "Organisation", "name"), "w", "Organisation", "name")
    return rows(df.select("p", "u.name", "w.name"))


# ---------------------------------------------------------------------------
# X: negation
# ---------------------------------------------------------------------------


@check(
    "X01",
    """
    MATCH (a:Person {ID: 933})-[:knows]-(b:Person)-[:knows]-(c:Person)
    WHERE c.ID <> 933 AND NOT (a)-[:knows]-(c)
    RETURN DISTINCT c.ID
    """,
)
def x1(d: Data):
    "friends-of-friends of 933 who are not friends (pattern predicate / NOT EXISTS)"
    fof = two_hop(d, 933, undirected=True).filter(c("f") != 933).select("f").unique()
    friends = d.hop(person(d, 933), "knows", "p", "f", undirected=True).select("f")
    return rows(fof.join(friends, on="f", how="anti"))


@check(
    "X02",
    """
    MATCH (p:Person)-[:personIsLocatedIn]->(l:Place)
    WHERE l.name = "Berlin" AND NOT (p)-[:workAt]->(:Organisation)
    RETURN p.ID
    """,
)
def x2(d: Data):
    "Berlin persons without a workAt relationship"
    df = d.hop(d.nodes("Place", "l", c("name") == "Berlin"), "personIsLocatedIn", "p", "l")
    workers = d.rel_table("workAt").select(pl.col("src").alias("p"))
    return rows(df.join(workers, on="p", how="anti").select("p"))


# ---------------------------------------------------------------------------
# W: WITH pipelines; G: grouped and ordered aggregates
# ---------------------------------------------------------------------------


@check(
    "W01",
    """
    MATCH (p:Person)-[:personIsLocatedIn]->(:Place {name: "Berlin"})
    WITH p
    MATCH (p)<-[:postHasCreator]-(post:Post)-[:postHasTag]->(t:Tag)
    WITH t, count(DISTINCT post.ID) AS n
    WHERE n >= 5
    RETURN t.name, n
    """,
)
def w1(d: Data):
    "WITH pipeline: tags used on >= 5 distinct posts by Berlin persons"
    df = d.hop(d.nodes("Place", "l", c("name") == "Berlin"), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "postHasCreator", "post", "p")
    df = d.hop(df, "postHasTag", "post", "t")
    df = d.props(df, "t", "Tag", "name").group_by("t.name").agg(pl.col("post").n_unique().alias("n"))
    return rows(df.filter(c("n") >= 5).select("t.name", "n"))


@check(
    "W02",
    """
    MATCH (f:Forum)-[:hasMember]->(p:Person)
    WITH f, count(p) AS members
    ORDER BY members DESC, f.ID
    LIMIT 3
    MATCH (f)-[:hasModerator]->(m:Person)
    RETURN f.ID, members, m.firstName
    """,
)
def w2(d: Data):
    "WITH ... ORDER BY ... LIMIT then MATCH: three largest forums and their moderators"
    df = d.hop(None, "hasMember", "f", "p").group_by("f").len("members")
    df = df.sort(["members", "f"], descending=[True, False]).head(3)
    df = d.hop(df, "hasModerator", "f", "m")
    return rows(d.props(df, "m", "Person", "firstName").select("f", "members", "m.firstName"))


@check(
    "G01",
    """
    MATCH (p:Person)-[:workAt]->(o:Organisation)
    WHERE o.type <> "university"
    RETURN o.name, COUNT(DISTINCT p.ID) AS n
    ORDER BY n DESC, o.name
    LIMIT 5
    """,
    ordered=True,
)
def g1(d: Data):
    "ORDER BY count DESC, name with LIMIT 5: top non-university employers (order-sensitive)"
    df = d.hop(d.nodes("Organisation", "o", c("type") != "university"), "workAt", "p", "o")
    df = d.props(df, "o", "Organisation", "name").group_by("o.name").agg(pl.col("p").n_unique().alias("n"))
    return rows(df.sort(["n", "o.name"], descending=[True, False]).head(5).select("o.name", "n"))


# ---------------------------------------------------------------------------
# C: cyclic patterns
# ---------------------------------------------------------------------------


@check(
    "C01",
    "MATCH (a:Person {ID: 933})-[:knows]->(b:Person)-[:knows]->(c:Person), (a)-[:knows]->(c) RETURN count(*) AS n",
)
def c1(d: Data):
    "directed knows triangles through 933: count(*)"
    df = d.hop(d.nodes("Person", "a", c("id") == 933), "knows", "a", "b")
    df = d.hop(df, "knows", "b", "c")
    return count(d.hop(df, "knows", "a", "c"))


@check(
    "C02",
    """
    MATCH (c:Comment)-[:commentHasCreator]->(p:Person)-[:personIsLocatedIn]->(l:Place),
          (c)-[:replyOfComment]->(c2:Comment)-[:commentHasCreator]->(p)
    WHERE l.name = "Berlin"
    RETURN DISTINCT c.ID
    """,
)
def c2(d: Data):
    "comments by Berlin persons replying to a comment by the same person"
    df = d.hop(d.nodes("Place", "l", c("name") == "Berlin"), "personIsLocatedIn", "p", "l")
    df = d.hop(df, "commentHasCreator", "c", "p")
    df = d.hop(df, "replyOfComment", "c", "c2")
    df = d.hop(df, "commentHasCreator", "c2", "p")
    return rows(df.select("c").unique())


@check(
    "C03",
    """
    MATCH (a:Person {ID: 1129})-[:knows]-(b:Person), (a)-[:hasInterest]->(t:Tag)<-[:hasInterest]-(b)
    RETURN b.ID, t.name
    """,
)
def c3(d: Data):
    "interests shared between 1129 and each friend"
    df = d.hop(d.nodes("Person", "a", c("id") == 1129), "knows", "a", "b", undirected=True)
    df = d.hop(df, "hasInterest", "a", "t")
    df = d.hop(df, "hasInterest", "b", "t")
    return rows(d.props(df, "t", "Tag", "name").select("b", "t.name"))
