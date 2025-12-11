# app/evaluators/social.py
from __future__ import annotations

from typing import Optional, Dict, Any
import networkx as nx

# If you want to validate actor IDs or pull names for display,
# we import the Actor type for reference (not strictly required in runtime).
try:
    from ...api.models import Actor  # noqa: F401
except Exception:
    # The graph works without importing models at runtime,
    # but having the type available is helpful when developing.
    pass


class SocialGraph:
    """
    A thin wrapper around a networkx.Graph that stores relationships between
    actors and computes a simple 'tie strength' score.

    Nodes: actor IDs (strings)
    Edge attributes:
      - relatedness: str (e.g., 'Friend', 'Neighbour')
    """

    def __init__(self) -> None:
        self.g = nx.Graph()

    # ---------------------- Node / Actor management -------------------------

    def upsert_actor(self, actor: "Actor | Dict[str, Any]") -> None:
        """
        Ensure an actor node exists in the graph.

        Parameters
        ----------
        actor : Actor | dict
            Must contain at least 'id' and ideally a 'name' for readability.
        """
        if isinstance(actor, dict):
            a_id = actor.get("id")
            a_name = actor.get("name", a_id)
        else:
            a_id = getattr(actor, "id", None)
            a_name = getattr(actor, "name", a_id)

        if not a_id:
            raise ValueError("Actor must have an 'id' field.")

        if not self.g.has_node(a_id):
            self.g.add_node(a_id, name=a_name)
        else:
            # Update name if provided
            self.g.nodes[a_id]["name"] = a_name or self.g.nodes[a_id].get("name", a_id)

    # ---------------------- Relationship management -------------------------

    def relate(
        self,
        a_id: str,
        b_id: str,
        relatedness: str = "Neighbour",
    ) -> None:
        """
        Create or update a relationship between two actors.

        Parameters
        ----------
        a_id, b_id : str
            Actor IDs for the relationship endpoints.
        relatedness : str
            Defaults to 'Neighbour'.
        """
        if not self.g.has_node(a_id):
            self.g.add_node(a_id, name=a_id)
        if not self.g.has_node(b_id):
            self.g.add_node(b_id, name=b_id)

        self.g.add_edge(a_id, b_id, relatedness=relatedness)

    def update_relation(self, a_id: str, b_id: str, **attrs: Any) -> None:
        """
        Update one or more attributes on an existing edge.
        """
        if not self.g.has_edge(a_id, b_id):
            raise KeyError(f"No relation exists between '{a_id}' and '{b_id}'.")

        # Normalize attributes if present
        if "relatedness" in attrs:
            rel = attrs["relatedness"]
            attrs["relatedness"] = rel

        self.g[a_id][b_id].update(attrs)


    def get_relation(self, a_id: str, b_id: str) -> Optional[Dict[str, Any]]:
        """
        Return a copy of the relation attributes between two actors.
        """
        if not self.g.has_edge(a_id, b_id):
            return None
        return dict(self.g.get_edge_data(a_id, b_id))

    # ---------------------- Utilities ---------------------------------------

    def to_edge_list(self) -> Dict[str, Any]:
        """
        Export a simple edge list (useful for debugging or visualization).
        """
        edges = []
        for u, v, attrs in self.g.edges(data=True):
            edges.append({"a_id": u, "b_id": v, **attrs})
        return {"edges": edges}

    def to_node_list(self) -> Dict[str, Any]:
        """
        Export node metadata (id + name).
        """
        nodes = []
        for n, attrs in self.g.nodes(data=True):
            nodes.append({"id": n, "name": attrs.get("name", n)})
        return {"nodes": nodes}
    
    def edges_for(self, actor_id: str) -> Dict[str, Any]: 
        edges = []
        if not self.g.has_node(actor_id):
            return {"edges": []}
        for n in self.g.neighbors(actor_id):
            attrs = self.g.get_edge_data(actor_id, n)
            edges.append({"a_id": actor_id, "b_id": n, **attrs})
        return {"edges": edges}
