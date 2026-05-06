from elasticsearch_dsl import Q
from elasticsearch_dsl.connections import connections
from .documents import MessageDocument

connections.create_connection(
    alias="default",
    hosts=["http://localhost:9200"]
)


def search_messages(q):
    if not q:
        return []

    s = MessageDocument.search()

    query = Q(
        "bool",
        should=[

            # 🔥 substring (loan number / ID)
            Q("wildcard", **{
                "sent_text_message.raw": {
                    "value": f"*{q}*",
                    "boost": 5
                }
            }),

            # 🔥 fuzzy text search (fixed syntax)
            Q("match", sent_text_message={
                "query": q,
                "fuzziness": "AUTO",
                "boost": 2
            }),

            # 🔥 mobile search
            Q("wildcard", **{
                "mobile": {
                    "value": f"*{q}*",
                    "boost": 4
                }
            }),
        ]
    )

    s = s.query(query)
    s = s.sort("-sent_at")[:200]

    response = s.execute()

    return list({hit.mobile for hit in response})
