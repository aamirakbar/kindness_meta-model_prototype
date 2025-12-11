from __future__ import annotations

import argparse
import json
import random
import http.client
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .random_helper import build_overrides_for_actor 


try:
    from app.summary_renderer import OpportunityEventView, render_event_summary
except ImportError:
    from summary_renderer import OpportunityEventView, render_event_summary



BASE_HOST = "localhost"
BASE_PORT = 8000


# --------------------------- HTTP helpers --------------------------- #

def post_json(path: str, payload: dict | None) -> tuple[int, str]:
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    headers = {"Content-type": "application/json"}
    body = json.dumps(payload) if payload is not None else None
    conn.request("POST", path, body, headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data


def get_json(path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data

# --------------------------- Simulation ----------------------------- #

class CommunityEnergySimulation:
    """
    Text-based simulation that creates kindness opportunities between residents
    in the community energy and prints the outcomes to stdout.
    Drives the FastAPI service:
      1) Upserts canonical actors
      2) Upserts social links
      3) Each step: updates relatedness + posts a new opportunity
    """

    def __init__(
        self,
        actors_path: Path,
        links_path: Path,
        seed: Optional[int] = None,
    ) -> None:
        
        self.rand = random.Random(seed) if seed is not None else random.Random()
        self.actors_path = actors_path
        self.links_path = links_path
        self.actor_ids: List[str] = []
        self.tie_strength: Dict[Tuple[str, str], float] = {}
        self.time_step = 0
        self.history: List[str] = []

        # Load and seed into API
        self._seed_actors()
        self._seed_relationships()

    # ------------------------------------------------------------------ #
    # Seeding helpers
    # ------------------------------------------------------------------ #
    def _seed_actors(self) -> None:
        payload = json.loads(self.actors_path.read_text(encoding="utf-8"))
        for a in payload:
            a.setdefault("role", None)
            a.setdefault("psychological", [])
            a.setdefault("social", [])
            a.setdefault("motivations", [])
            status, body = post_json("/actors", a)
            if status != 200:
                raise RuntimeError(f"POST /actors failed ({status}): {body}")
        # Keep the list of IDs for sampling
        self.actor_ids = [a["id"] for a in payload]


    def _seed_relationships(self) -> None:
        links = json.loads(self.links_path.read_text(encoding="utf-8"))
        for link in links:
            relatedness = link.get("relatedness", "Neighbour")
            path = f"/social/relate/{link['a_id']}/{link['b_id']}?relatedness={relatedness}"
            status, body = post_json(path, {})
            if status != 200:
                raise RuntimeError(f"POST {path} failed ({status}): {body}")

        
        # Initialize a continuous tie-strength, can evolve over time
        for link in links:
            key = tuple(sorted((link["a_id"], link["b_id"])))
            self.tie_strength[key] = self.rand.uniform(0.25, 0.4)



    # ------------------------------------------------------------------ #
    # Relationship dynamics
    # ------------------------------------------------------------------ #
    def _update_relationships(self) -> None:        
        """
        Evolve tie strengths; map to discrete relatedness categories;
        call /social/relate to reflect changes in the API.
        """        
        for (a_id, b_id), strength in list(self.tie_strength.items()):
            delta = self.rand.uniform(-0.05, 0.05)  # dispute/bonding
            new_strength = max(0.1, min(1.0, strength + delta))
            self.tie_strength[(a_id, b_id)] = new_strength

            # Map continuous strength to a discrete relatedness label
            relatedness = self._strength_to_relatedness(new_strength)
            path = f"/social/relate/{a_id}/{b_id}?relatedness={relatedness}"
            status, body = post_json(path, {})
            if status != 200:
                print(f"[warn] POST {path} -> {status}: {body}")


        
    @staticmethod
    def _strength_to_relatedness(value: float) -> str:
        """
        Map a continuous [0.1,1.0] strength to one of your categories.
        """
        if value < 0.25:
            return "New_Comer"
        elif value < 0.5:
            return "Neighbour"
        elif value < 0.75:
            return "Colleague"
        elif value < 0.9:
            return "Friend"
        else:
            return "Family"

    # ------------------------------------------------------------------ #
    # Supporting Acts Creations
    # ------------------------------------------------------------------ #
    def _make_supporting_acts(self) -> list[dict]:
        # MotivationAct: sometimes increase other-betterment
        increase = self.rand.random() < 0.5  # 50% chance to boost
        mot_value = round(self.rand.uniform(0.1, 0.5), 2) if increase else 0.0
        mot_intensity = "High" if mot_value >= 0.4 else ("Medium" if mot_value >= 0.2 else "Low")

        mot = {
            "kind": "MotivationAct",
            "name": "Highlight benefits of kindness",
            "type": "personal",
            "intensity": mot_intensity,
            "pre":  {"name": "pre",  "value": ""},
            "post": {"name": "post", "value": ""},
            "value": mot_value,
            "increase_other_betterment": increase,
        }

        # AbilityAct: grant ability (positive effect)
        ability_value = round(self.rand.uniform(0.2, 0.6), 2)
        ability = {
            "kind": "AbilityAct",
            "name": "Provide energy sharing facility",
            "domain": "digital",
            "effort_target": "EffortToShareSurplus",
            "pre":  {"name": "pre",  "value": ""},
            "post": {"name": "post", "value": ""},
            "effect": "positive",
            "value": ability_value

        }

        # PromptAct: last in sequence
        prompt = {
            "kind": "PromptAct",
            "name": "Send dashboard notification",
            "channel": "dashboard_notification",
            "message": "Share energy with your neighbour.",
            "pre":  {"name": "pre",  "value": ""},
            "post": {"name": "post", "value": ""},
        }

        return [mot, ability, prompt]  # PromptAct last

    # ------------------------------------------------------------------ #
    # Opportunity creation
    # ------------------------------------------------------------------ #
    def _post_random_opportunity(self) -> Optional[str]:
        if len(self.actor_ids) < 2:
            return None

        
        giver_id, receiver_id = self.rand.sample(self.actor_ids, 2)
        remaining = [aid for aid in self.actor_ids if aid not in {giver_id, receiver_id}]
        observer_id = self.rand.choice(remaining) if remaining else giver_id

        ko_id = f"KO-{self.time_step:03d}"
        name = f"Kindness Opportunity #{self.time_step}"

        # Optional: derive social signals from tie strength between giver and receiver
        key = tuple(sorted((giver_id, receiver_id)))
        strength = self.tie_strength.get(key, 0.6)
        relatedness = self._strength_to_relatedness(strength)
        trust_signal = "Familiarity"  # meta-model's trust value
        
        # Build per-actor overrides
        overrides = {
            giver_id: build_overrides_for_actor(
                                self.rand,
                                role="Giver",
                                target_id=receiver_id,
                                inject_social_signals={"Relatedness": relatedness, "Trust": trust_signal},
                            ),
            receiver_id: build_overrides_for_actor(
                                self.rand,
                                role="Receiver",
                                target_id=None,
                                inject_social_signals={"Relatedness": relatedness, "Trust": trust_signal},
                            ),
        }

        # Generate Supporting Acts
        supporting_acts = self._make_supporting_acts()
        
        payload = {
            "id": ko_id,
            "name": name,
            "actors": [
                {"actor_id": giver_id,    "role": "Giver"},
                {"actor_id": receiver_id, "role": "Receiver"},
                {"actor_id": observer_id, "role": "Observer"},
            ],
            "context": {
                "name": "Community Energy",
                "location": "Dashboard",
                "time": f"T+{self.time_step:02d}",
            },
            "kindness_act": {
                "name": "Energy Sharing",
                "pre":  {"name": "pre",  "value": ""},
                "post": {"name": "post", "value": ""},
            },
            "supporting_acts": supporting_acts,
            "actor_overrides": overrides,
        }

        #print(payload)
        
        status, body = post_json("/opportunities", payload)
        if status != 200:
            print(f"[warn] POST /opportunities -> {status}: {body}")
            return None

        resp = json.loads(body)
        event_view = OpportunityEventView(
                    ko_id=ko_id,
                    name=name,
                    timestamp=self.time_step,
                    giver_id=giver_id,
                    receiver_id=receiver_id,
                    observer_id=observer_id,
                    kindness_act_name="Energy Sharing",
                    is_ko=bool(resp.get("is_kindness_opportunity", False)),
                    prompt_ready=bool(resp.get("prompt_ready", False))
                )
        return render_event_summary(
                event=event_view,
                ko_payload=payload,    # the dict you posted
                ko_response=resp,      # flags from API
            )


    
    # ------------------------------------------------------------------ #
    # Simulation lifecycle
    # ------------------------------------------------------------------ #    
    def run(self, steps: int = 10, verbose: bool = True) -> List[str]:
            for _ in range(steps):
                self.time_step += 1
                self._update_relationships()
                event = self._post_random_opportunity()
                if verbose:
                    if event:
                        print(event)
                    else:
                        print(f"[t={self.time_step:03d}] No eligible opportunity.")
                if event:
                    self.history.append(event)
            return self.history

# --------------------------- CLI glue ------------------------------ #

def parse_args() -> argparse.Namespace:
    base_dir = Path(__file__).resolve().parent
    default_actors = base_dir / "data" / "scenarios" / "actors.json"
    default_links = base_dir / "data" / "scenarios" / "social_links.json"

    parser = argparse.ArgumentParser(description="Community energy API-driven simulation.")
    parser.add_argument("--actors-path", type=Path, default=default_actors, help="Path to actors.json")
    parser.add_argument("--links-path", type=Path, default=default_links, help="Path to social_links.json")
    parser.add_argument("--steps", type=int, default=10, help="Number of simulation steps to run")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output")
    return parser.parse_args()



def main() -> None:
    args = parse_args()
    sim = CommunityEnergySimulation(
        actors_path=args.actors_path,
        links_path=args.links_path,
        seed=args.seed,
    )
    sim.run(steps=args.steps, verbose=not args.quiet)


if __name__ == "__main__":
    main()