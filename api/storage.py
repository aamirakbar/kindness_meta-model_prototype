# api/storage.py

from typing import Dict
from .models import Actor, KindnessOpportunity

class MemoryStore:
    def __init__(self):
        self.actors: Dict[str, Actor] = {}
        self.opportunities: Dict[str, KindnessOpportunity] = {}

    def upsert_actor(self, a: Actor):
        self.actors[a.id] = a

    def upsert_opportunity(self, ko: KindnessOpportunity):
        self.opportunities[ko.id] = ko

    def get_actor(self, actor_id: str) -> Actor:
        return self.actors[actor_id]

    def get_opportunity(self, ko_id: str) -> KindnessOpportunity:
        return self.opportunities[ko_id]

    def list_opportunities(self):
        return list(self.opportunities.values())

    def delete_opportunity(self, ko_id: str) -> bool:
        if ko_id in self.opportunities:
            del self.opportunities[ko_id]
            return True
        return False