"""LDBC SNB Interactive v1 complex queries Q1-Q14 for FalkorDB.

Port of the official Neo4j queries
(https://github.com/ldbc/ldbc_snb_interactive_v1_impls/tree/main/cypher/queries,
interactive-complex-{1..14}.cypher) to this graph's schema, with the parameters
of ladybugdb/query_complex14.py. Each query is one statement with the official
clause structure. Adaptations:

Schema:
- Labels and relationship types as in query.py (``knows`` traversed undirected,
  ``Tagclass``, ``Place.type``/``Organisation.type`` instead of the
  City/Country/Company/University labels).
- There is no ``Message`` label. ``HAS_CREATOR``, ``IS_LOCATED_IN``, ``LIKES``
  and ``REPLY_OF`` on a Message become type alternations such as
  ``[:postHasCreator|commentHasCreator]`` to an unlabelled node; each type
  connects only Posts or only Comments, so the alternation matches exactly the
  Message edges.
- Dates are stored as ``2010-10-16T12:00:00.000+0000`` strings, which order
  like the timestamps, so date parameters use the same format.
- ``Person.email``/``Person.speaks`` are not loaded: Q1 omits
  ``friendEmails``/``friendLanguages``.

Dialect:
- ``shortestPath()`` is only allowed in WITH/RETURN (Q1, Q13).
- Pattern predicates are only allowed in WHERE, so Q7's ``isNew`` counts the
  ``knows`` edges with a pattern comprehension.
- Datetime subtraction and ``epochMillis`` do not exist, and ``localdatetime()``
  drops milliseconds, so Q7 computes the epoch milliseconds from the date string.
- Q14 collects the replies between the persons on any shortest path once and
  sums them per path edge with reduce(), instead of the official per-edge
  pattern comprehensions anchored on every Person. Each reply hop is its own
  OPTIONAL MATCH: written as one pattern, the planner anchors it on the unbound
  replied-to person.

FalkorDB 6.0.1 planner workarounds (same results, different clause split):
- A WHERE on a variable bound by a MATCH after UNWIND, LIMIT or an aggregating
  WITH runs before the traversal that binds it and drops every row
  (https://github.com/FalkorDB/FalkorDB/issues/2557,
  https://github.com/FalkorDB/FalkorDB/issues/3082), and an inline property map
  there fails with a type error (https://github.com/FalkorDB/FalkorDB/issues/2556).
  Q1, Q6 and Q9 move these filters into a following WITH ... WHERE. In Q1's
  second OPTIONAL MATCH any filter drops every company, so the type checks
  move into the collected CASE.
- An OPTIONAL MATCH whose pattern starts at an unbound variable is anchored on it
  instead of the bound one (https://github.com/FalkorDB/FalkorDB/issues/3037):
  Q5 counts zero posts per forum. Q5 traverses from the forum and filters the
  authors in the aggregation.
- A variable-length knows traversal followed by a location hop in the same MATCH
  starts from every city instead of the indexed person (Q3: 73 s, Q10: over
  10 minutes). Q3 and Q10 split the location hop into its own MATCH.
"""

import os
import sys
import time
from typing import Any, Callable

from dotenv import load_dotenv
from falkordb import FalkorDB, Graph

load_dotenv()

FALKORDB_HOST = os.environ.get("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
FALKORDB_GRAPH = os.environ.get("FALKORDB_GRAPH", "ldbc_snb_sf1")

SAMIR = 2199023262543
RAFAEL = 2783

PARAMS: dict[int, dict[str, Any]] = {
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


def _execute(graph: Graph, idx: int, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    print(f"\nQuery {idx} {params}:\n{query}")
    result = graph.ro_query(query, params)
    names = [name for _, name in result.header]
    records = [dict(zip(names, row)) for row in result.result_set]
    print(records)
    return records


def _epoch_ms(date: str) -> str:
    """Cypher expression: milliseconds since 0001-01-01 of a stored date string."""
    day = f"date(substring({date}, 0, 10))"
    year = f"({day}.year - 1)"
    days = f"(365 * {year} + {year} / 4 - {year} / 100 + {year} / 400 + {day}.ordinalDay)"
    return (
        f"({days} * 86400000"
        f" + toInteger(substring({date}, 11, 2)) * 3600000"
        f" + toInteger(substring({date}, 14, 2)) * 60000"
        f" + toInteger(substring({date}, 17, 2)) * 1000"
        f" + toInteger(substring({date}, 20, 3)))"
    )


def run_query1(graph: Graph):
    "Q1. Transitive friends with a certain name"
    query = """
        MATCH (p:Person {ID: $personId}), (friend:Person {firstName: $firstName})
        WHERE NOT p = friend
        WITH p, friend, shortestPath((p)-[:knows*1..3]-(friend)) AS path
        WHERE path IS NOT NULL
        WITH min(length(path)) AS distance, friend
        ORDER BY distance ASC, friend.lastName ASC, friend.ID ASC
        LIMIT 20
        MATCH (friend)-[:personIsLocatedIn]->(friendCity:Place)
        WITH friend, friendCity, distance
        WHERE friendCity.type = 'city'
        OPTIONAL MATCH (friend)-[studyAt:studyAt]->(uni:Organisation {type: 'university'})
                       -[:organisationIsLocatedIn]->(uniCity:Place {type: 'city'})
        WITH friend, collect(
            CASE WHEN uni.name IS NULL THEN null
                 ELSE [uni.name, studyAt.classYear, uniCity.name] END) AS unis, friendCity, distance
        OPTIONAL MATCH (friend)-[workAt:workAt]->(company:Organisation)
                       -[:organisationIsLocatedIn]->(companyCountry:Place)
        WITH friend, collect(
            CASE WHEN company.type = 'company' AND companyCountry.type = 'country'
                 THEN [company.name, workAt.workFrom, companyCountry.name] END) AS companies,
             unis, friendCity, distance
        RETURN friend.ID AS friendId, friend.lastName AS friendLastName,
               distance AS distanceFromPerson, friend.birthday AS friendBirthday,
               friend.creationDate AS friendCreationDate, friend.gender AS friendGender,
               friend.browserUsed AS friendBrowserUsed, friend.locationIP AS friendLocationIp,
               friendCity.name AS friendCityName, unis AS friendUniversities,
               companies AS friendCompanies
        ORDER BY distanceFromPerson ASC, friendLastName ASC, friendId ASC
        LIMIT 20
    """
    return _execute(graph, 1, query, PARAMS[1])


def run_query2(graph: Graph):
    "Q2. Recent messages by your friends"
    query = """
        MATCH (:Person {ID: $personId})-[:knows]-(friend:Person)
              <-[:postHasCreator|commentHasCreator]-(message)
        WHERE message.creationDate <= $maxDate
        RETURN friend.ID AS personId, friend.firstName AS personFirstName,
               friend.lastName AS personLastName, message.ID AS postOrCommentId,
               coalesce(message.content, message.imageFile) AS postOrCommentContent,
               message.creationDate AS postOrCommentCreationDate
        ORDER BY postOrCommentCreationDate DESC, postOrCommentId ASC
        LIMIT 20
    """
    return _execute(graph, 2, query, PARAMS[2])


def run_query3(graph: Graph):
    "Q3. Friends and friends of friends that have been to given countries"
    query = """
        MATCH (countryX:Place {name: $countryXName}),
              (countryY:Place {name: $countryYName}),
              (person:Person {ID: $personId})
        WITH person, countryX, countryY
        LIMIT 1
        MATCH (city:Place {type: 'city'})-[:isPartOf]->(country:Place {type: 'country'})
        WHERE country IN [countryX, countryY]
        WITH person, countryX, countryY, collect(city) AS cities
        MATCH (person)-[:knows*1..2]-(friend:Person)
        WITH person, friend, cities, countryX, countryY
        MATCH (friend)-[:personIsLocatedIn]->(friendCity:Place)
        WITH person, friend, friendCity, cities, countryX, countryY
        WHERE NOT person = friend AND NOT friendCity IN cities
        WITH DISTINCT friend, countryX, countryY
        MATCH (friend)<-[:postHasCreator|commentHasCreator]-(message),
              (message)-[:postIsLocatedIn|commentIsLocatedIn]->(country:Place)
        WHERE $endDate > message.creationDate AND message.creationDate >= $startDate
          AND country IN [countryX, countryY]
        WITH friend,
             CASE WHEN country = countryX THEN 1 ELSE 0 END AS messageX,
             CASE WHEN country = countryY THEN 1 ELSE 0 END AS messageY
        WITH friend, sum(messageX) AS xCount, sum(messageY) AS yCount
        WHERE xCount > 0 AND yCount > 0
        RETURN friend.ID AS friendId, friend.firstName AS friendFirstName,
               friend.lastName AS friendLastName, xCount, yCount,
               xCount + yCount AS xyCount
        ORDER BY xyCount DESC, friendId ASC
        LIMIT 20
    """
    return _execute(graph, 3, query, PARAMS[3])


def run_query4(graph: Graph):
    "Q4. New topics"
    query = """
        MATCH (person:Person {ID: $personId})-[:knows]-(friend:Person),
              (friend)<-[:postHasCreator]-(post:Post)-[:postHasTag]->(tag:Tag)
        WITH DISTINCT tag, post
        WITH tag,
             CASE WHEN $endDate > post.creationDate AND post.creationDate >= $startDate
                  THEN 1 ELSE 0 END AS valid,
             CASE WHEN $startDate > post.creationDate THEN 1 ELSE 0 END AS inValid
        WITH tag, sum(valid) AS postCount, sum(inValid) AS inValidPostCount
        WHERE postCount > 0 AND inValidPostCount = 0
        RETURN tag.name AS tagName, postCount
        ORDER BY postCount DESC, tagName ASC
        LIMIT 10
    """
    return _execute(graph, 4, query, PARAMS[4])


def run_query5(graph: Graph):
    "Q5. New groups"
    query = """
        MATCH (person:Person {ID: $personId})-[:knows*1..2]-(friend:Person)
        WHERE NOT person = friend
        WITH DISTINCT friend
        MATCH (friend)<-[membership:hasMember]-(forum:Forum)
        WHERE membership.joinDate > $minDate
        WITH forum, collect(friend) AS friends
        OPTIONAL MATCH (forum)-[:containerOf]->(post:Post)
        OPTIONAL MATCH (post)-[:postHasCreator]->(author:Person)
        WITH forum, count(CASE WHEN author IN friends THEN post END) AS postCount
        RETURN forum.title AS forumName, postCount
        ORDER BY postCount DESC, forum.ID ASC
        LIMIT 20
    """
    return _execute(graph, 5, query, PARAMS[5])


def run_query6(graph: Graph):
    "Q6. Tag co-occurrence"
    query = """
        MATCH (knownTag:Tag {name: $tagName})
        WITH knownTag.ID AS knownTagId
        MATCH (person:Person {ID: $personId})-[:knows*1..2]-(friend:Person)
        WHERE NOT person = friend
        WITH knownTagId, collect(DISTINCT friend) AS friends
        UNWIND friends AS f
        MATCH (f)<-[:postHasCreator]-(post:Post),
              (post)-[:postHasTag]->(t:Tag),
              (post)-[:postHasTag]->(tag:Tag)
        WITH post, t, tag, knownTagId
        WHERE t.ID = knownTagId AND NOT t = tag
        WITH tag.name AS tagName, count(post) AS postCount
        RETURN tagName, postCount
        ORDER BY postCount DESC, tagName ASC
        LIMIT 10
    """
    return _execute(graph, 6, query, PARAMS[6])


def run_query7(graph: Graph):
    "Q7. Recent likers"
    query = f"""
        MATCH (person:Person {{ID: $personId}})<-[:postHasCreator|commentHasCreator]-(message)
              <-[like:likePost|likeComment]-(liker:Person)
        WITH liker, message, like.creationDate AS likeTime, person
        ORDER BY likeTime DESC, message.ID ASC
        WITH liker, head(collect({{msg: message, likeTime: likeTime}})) AS latestLike, person
        WITH liker, person, latestLike, latestLike.msg AS msg
        RETURN liker.ID AS personId, liker.firstName AS personFirstName,
               liker.lastName AS personLastName, latestLike.likeTime AS likeCreationDate,
               msg.ID AS commentOrPostId,
               coalesce(msg.content, msg.imageFile) AS commentOrPostContent,
               ({_epoch_ms("latestLike.likeTime")} - {_epoch_ms("msg.creationDate")}) / 60000 AS minutesLatency,
               size([(liker)-[:knows]-(person) | 1]) = 0 AS isNew
        ORDER BY likeCreationDate DESC, personId ASC
        LIMIT 20
    """
    return _execute(graph, 7, query, PARAMS[7])


def run_query8(graph: Graph):
    "Q8. Recent replies"
    query = """
        MATCH (start:Person {ID: $personId})<-[:postHasCreator|commentHasCreator]-()
              <-[:replyOfPost|replyOfComment]-(comment:Comment)-[:commentHasCreator]->(person:Person)
        RETURN person.ID AS personId, person.firstName AS personFirstName,
               person.lastName AS personLastName,
               comment.creationDate AS commentCreationDate, comment.ID AS commentId,
               comment.content AS commentContent
        ORDER BY commentCreationDate DESC, commentId ASC
        LIMIT 20
    """
    return _execute(graph, 8, query, PARAMS[8])


def run_query9(graph: Graph):
    "Q9. Recent messages by friends or friends of friends"
    query = """
        MATCH (root:Person {ID: $personId})-[:knows*1..2]-(friend:Person)
        WHERE NOT friend = root
        WITH collect(DISTINCT friend) AS friends
        UNWIND friends AS friend
        MATCH (friend)<-[:postHasCreator|commentHasCreator]-(message)
        WITH friend, message
        WHERE message.creationDate < $maxDate
        RETURN friend.ID AS personId, friend.firstName AS personFirstName,
               friend.lastName AS personLastName, message.ID AS commentOrPostId,
               coalesce(message.content, message.imageFile) AS commentOrPostContent,
               message.creationDate AS commentOrPostCreationDate
        ORDER BY commentOrPostCreationDate DESC, commentOrPostId ASC
        LIMIT 20
    """
    return _execute(graph, 9, query, PARAMS[9])


def run_query10(graph: Graph):
    "Q10. Friend recommendation"
    query = """
        MATCH (person:Person {ID: $personId})-[:knows*2..2]-(friend:Person)
        WHERE NOT friend = person AND NOT (friend)-[:knows]-(person)
        WITH person, friend
        MATCH (friend)-[:personIsLocatedIn]->(city:Place)
        WITH person, city, friend, date(friend.birthday) AS birthday
        WHERE city.type = 'city'
          AND ((birthday.month = $month AND birthday.day >= 21)
               OR (birthday.month = ($month % 12) + 1 AND birthday.day < 22))
        WITH DISTINCT friend, city, person
        OPTIONAL MATCH (friend)<-[:postHasCreator]-(post:Post)
        WITH friend, city, collect(post) AS posts, person
        WITH friend, city, size(posts) AS postCount,
             size([p IN posts WHERE (p)-[:postHasTag]->(:Tag)<-[:hasInterest]-(person)]) AS commonPostCount
        RETURN friend.ID AS personId, friend.firstName AS personFirstName,
               friend.lastName AS personLastName,
               commonPostCount - (postCount - commonPostCount) AS commonInterestScore,
               friend.gender AS personGender, city.name AS personCityName
        ORDER BY commonInterestScore DESC, personId ASC
        LIMIT 10
    """
    return _execute(graph, 10, query, PARAMS[10])


def run_query11(graph: Graph):
    "Q11. Job referral"
    query = """
        MATCH (person:Person {ID: $personId})-[:knows*1..2]-(friend:Person)
        WHERE NOT person = friend
        WITH DISTINCT friend
        MATCH (friend)-[workAt:workAt]->(company:Organisation {type: 'company'})
              -[:organisationIsLocatedIn]->(:Place {name: $countryName, type: 'country'})
        WHERE workAt.workFrom < $workFromYear
        RETURN friend.ID AS personId, friend.firstName AS personFirstName,
               friend.lastName AS personLastName, company.name AS organizationName,
               workAt.workFrom AS organizationWorkFromYear
        ORDER BY organizationWorkFromYear ASC, personId ASC, organizationName DESC
        LIMIT 10
    """
    return _execute(graph, 11, query, PARAMS[11])


def run_query12(graph: Graph):
    "Q12. Expert search"
    query = """
        MATCH (tag:Tag)-[:hasType|isSubclassOf*0..]->(baseTagClass:Tagclass)
        WHERE tag.name = $tagClassName OR baseTagClass.name = $tagClassName
        WITH collect(tag.ID) AS tags
        MATCH (:Person {ID: $personId})-[:knows]-(friend:Person)
              <-[:commentHasCreator]-(comment:Comment)-[:replyOfPost]->(:Post)-[:postHasTag]->(tag:Tag)
        WHERE tag.ID IN tags
        RETURN friend.ID AS personId, friend.firstName AS personFirstName,
               friend.lastName AS personLastName,
               collect(DISTINCT tag.name) AS tagNames,
               count(DISTINCT comment) AS replyCount
        ORDER BY replyCount DESC, personId ASC
        LIMIT 20
    """
    return _execute(graph, 12, query, PARAMS[12])


def run_query13(graph: Graph):
    "Q13. Single shortest path"
    query = """
        MATCH (person1:Person {ID: $person1Id}), (person2:Person {ID: $person2Id})
        WITH shortestPath((person1)-[:knows*]-(person2)) AS path
        RETURN CASE path IS NULL WHEN true THEN -1 ELSE length(path) END AS shortestPathLength
    """
    return _execute(graph, 13, query, PARAMS[13])


def run_query14(graph: Graph):
    "Q14. Trusted connection paths"
    query = """
        MATCH (person1:Person {ID: $person1Id}), (person2:Person {ID: $person2Id})
        WITH person1, person2
        MATCH path = allShortestPaths((person1)-[:knows*]-(person2))
        WITH collect(path) AS paths
        UNWIND paths AS path
        UNWIND nodes(path) AS person
        WITH paths, collect(DISTINCT person) AS people
        UNWIND people AS a
        OPTIONAL MATCH (a)<-[:commentHasCreator]-(comment:Comment)
        OPTIONAL MATCH (comment)-[reply:replyOfPost|replyOfComment]->(parent)
        OPTIONAL MATCH (parent)-[:postHasCreator|commentHasCreator]->(b:Person)
        WITH paths, collect(
            CASE WHEN b IN people
                 THEN [a.ID, b.ID, CASE type(reply) WHEN 'replyOfPost' THEN 1.0 ELSE 0.5 END] END) AS replies
        UNWIND paths AS path
        WITH [n IN nodes(path) | n.ID] AS personIdsInPath, replies
        RETURN personIdsInPath,
               reduce(weight = 0.0, i IN range(0, size(personIdsInPath) - 2) |
                   weight + reduce(w = 0.0, r IN replies |
                       w + CASE WHEN (r[0] = personIdsInPath[i] AND r[1] = personIdsInPath[i + 1])
                                  OR (r[0] = personIdsInPath[i + 1] AND r[1] = personIdsInPath[i])
                                THEN r[2] ELSE 0.0 END)) AS pathWeight
        ORDER BY pathWeight DESC
    """
    return _execute(graph, 14, query, PARAMS[14])


QUERY_FUNCTIONS: dict[int, Callable[[Graph], list[dict[str, Any]]]] = {
    1: run_query1,
    2: run_query2,
    3: run_query3,
    4: run_query4,
    5: run_query5,
    6: run_query6,
    7: run_query7,
    8: run_query8,
    9: run_query9,
    10: run_query10,
    11: run_query11,
    12: run_query12,
    13: run_query13,
    14: run_query14,
}


def main(graph: Graph, selected: list[int]) -> None:
    start = time.perf_counter()
    for idx in selected:
        QUERY_FUNCTIONS[idx](graph)
    print(f"\nCompleted {len(selected)} query(ies) in {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    selected = [int(i) for i in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(QUERY_FUNCTIONS)
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    main(db.select_graph(FALKORDB_GRAPH), selected)
