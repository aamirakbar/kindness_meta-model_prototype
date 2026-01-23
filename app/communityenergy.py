from __future__ import annotations

import argparse
import json
import random
import http.client
from collections import Counter
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
        self.actor_base_motivations: Dict[str, Tuple[float, float]] = {}
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
            # Assign baseline motivations if not present, default to 0.0
            base_other = a.setdefault("base_other_betterment", 0.0)
            base_self = a.setdefault("base_self_betterment", 0.0)
            self.actor_base_motivations[a["id"]] = (base_other, base_self)

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
    def _make_supporting_acts(self, base_other: float, base_self: float) -> list[dict]:
        """
        Create supporting acts for a given opportunity.

        MotivationAct is only included when the Giver's other-betterment is
        not already higher than self-betterment (i.e., when a motivational
        boost towards others is actually needed). Ability and Prompt acts
        are always included.
        """
        acts: list[dict] = []

        # MotivationAct: only when other-betterment is not already higher
        if base_other <= base_self:
            mot_value = round(self.rand.uniform(0.05, 0.2), 2)
            mot_intensity = "High" if mot_value >= 0.4 else ("Medium" if mot_value >= 0.2 else "Low")

            mot = {
                "kind": "MotivationAct",
                "name": "Highlight benefits of kindness",
                "type": "personal",
                "intensity": mot_intensity,
                "pre":  {"name": "pre",  "value": ""},
                "post": {"name": "post", "value": ""},
                "value": mot_value,
                "increase_other_betterment": True,
                "decrease_self_betterment": True,
            }
            acts.append(mot)

        # AbilityAct and PromptAct: either both included or both omitted (random)
        include_ability_and_prompt = self.rand.random() < 0.5  # 50% chance to include
        if include_ability_and_prompt:
            # AbilityAct
            raw_ability_value = round(self.rand.uniform(0.2, 0.6), 2)
            is_positive = self.rand.random() < 0.7  # e.g. 70% positive effect, 30% negative effect
            ability_effect = "positive" if is_positive else "negative"
            ability_value = raw_ability_value
            ability = {
                "kind": "AbilityAct",
                "name": "Provide energy sharing facility",
                "domain": "digital",
                "effort_target": "EffortToShareSurplus",
                "pre":  {"name": "pre",  "value": ""},
                "post": {"name": "post", "value": ""},
                "effect": ability_effect,
                "value": ability_value
            }
            acts.append(ability)

            # PromptAct: last in sequence
            prompt = {
                "kind": "PromptAct",
                "name": "Send dashboard notification",
                "channel": "dashboard_notification",
                "message": "Share energy with your neighbour.",
                "pre":  {"name": "pre",  "value": ""},
                "post": {"name": "post", "value": ""},
            }
            acts.append(prompt)

        return acts  # PromptAct last

    # ------------------------------------------------------------------ #
    # Opportunity creation
    # ------------------------------------------------------------------ #
    def _post_random_opportunity(self, detailed_summary: bool = False) -> Optional[str]:
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
        
        # Get base motivations
        giver_base_motivations = self.actor_base_motivations.get(giver_id, (0.0, 0.0))
        receiver_base_motivations = self.actor_base_motivations.get(receiver_id, (0.0, 0.0))

        # Build per-actor overrides
        overrides = {
            giver_id: build_overrides_for_actor(
                self.rand,
                role="Giver",
                target_id=receiver_id,
                base_motivations=giver_base_motivations,
                inject_social_signals={"Relatedness": relatedness, "Trust": trust_signal},
            ),
            receiver_id: build_overrides_for_actor(
                self.rand,
                role="Receiver",
                target_id=None,
                base_motivations=receiver_base_motivations,
                inject_social_signals={"Relatedness": relatedness, "Trust": trust_signal},
            ),
        }

        # Derive the Giver's base motivation scores from overrides
        giver_bundle = overrides.get(giver_id, {})
        giver_mots = giver_bundle.get("motivations", [])
        base_other = sum(m.get("level", 0.0) for m in giver_mots if m.get("mtype") == "Other_Betterment")
        base_self = sum(m.get("level", 0.0) for m in giver_mots if m.get("mtype") == "Self_Betterment")

        # Generate Supporting Acts, conditioned on base motivations
        supporting_acts = self._make_supporting_acts(base_other=base_other, base_self=base_self)
        
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
        
        if detailed_summary:
            return render_event_summary(
                event=event_view,
                ko_payload=payload,    # the dict posted
                ko_response=resp,      # flags from API
            )
        else:
            return str(bool(resp.get("is_kindness_opportunity", False))) + " " +  str(bool(resp.get("prompt_ready", False)))



    
    # ------------------------------------------------------------------ #
    # Simulation lifecycle
    # ------------------------------------------------------------------ #    
    def run(self, steps: int = 10, verbose: bool = False, detailed_summary: bool = False) -> List[str]:
            for _ in range(steps):
                self.time_step += 1
                self._update_relationships()
                event = self._post_random_opportunity(detailed_summary=detailed_summary)
                if detailed_summary: # If detailed_summary is true, print the event immediately
                    if event:
                        print(event)
                    else:
                        print(f"[t={self.time_step:03d}] No eligible opportunity.")
                elif verbose: # If not detailed_summary but verbose is true, print the basic event
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
    parser.add_argument("--summary", action="store_true", help="Print detailed summary for each step instead of the final count table")
    return parser.parse_args()



def main() -> None:
    args = parse_args()
    sim = CommunityEnergySimulation(
        actors_path=args.actors_path,
        links_path=args.links_path,
        seed=args.seed,
    )
    history = sim.run(
        steps=args.steps,
        verbose=not args.quiet,
        detailed_summary=args.summary
    )

    # Only print the count table if we are not in detailed summary mode
    if not args.summary:
        # Count occurrences of each combination
        counts = Counter(history)
        
        # Define the combinations in order
        combinations = ['True True', 'True False', 'False True', 'False False']
        
        # Print table header
        print("\n" + "=" * 40)
        print("Combination Count Table")
        print("=" * 40)
        print(f"{'is_KO | AS >= AL':<20} {'Count':<10}")
        print("-" * 40)
        
        # Print each combination with its count
        for combo in combinations:
            count = counts.get(combo, 0)
            print(f"{combo:<20} {count:<10}")
        
        print("=" * 40)
        print(f"Total: {len(history)}")
        print("=" * 40 + "\n")


if __name__ == "__main__":
    main()