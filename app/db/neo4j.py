"""Neo4j (route network, eventually consistent, rebuilt periodically by workers/graph_loader.py)."""


def create_neo4j(s):
    if not s.neo4j_url:
        return None
    from neo4j import AsyncGraphDatabase
    return AsyncGraphDatabase.driver(s.neo4j_url, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=2, max_connection_lifetime=600)
