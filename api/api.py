import traceback
from fastapi import FastAPI, HTTPException, Query
import json
from fastapi.responses import PlainTextResponse

from .models import (
    Actor, KindnessOpportunity, Role, Motivation, MotivationType, 
    PsychologicalFactor, SocialFactor, Context, KindnessAct,
    MotivationAct, AbilityAct, PromptAct
)
from .engine import is_kindness_opportunity, can_trigger_prompt
from .storage import MemoryStore

from .evaluators.social import SocialGraph

app = FastAPI(title="Kindness Meta-Model Prototype (Community Energy)")
DB = MemoryStore()
SG = SocialGraph()


@app.get("/health")
def health():
    return {"status": "ok", "actors": len(DB.actors), "opportunities": len(DB.opportunities)}


@app.post("/actors")
def upsert_actor(a: Actor):
    try:
        DB.upsert_actor(a)
        SG.upsert_actor(a)
        return {"status": "ok"}
    except Exception as e:
        print(f"ERROR in /actors:", e)
        traceback.print_exc()
        raise  # FastAPI will surface the stack


@app.get("/actors", response_class=PlainTextResponse, tags=["actors"])
def list_actors_pretty() -> PlainTextResponse:
    """
    Return all actors as pretty-printed JSON (indent=2).
    """
    actors_list = list(DB.actors.values())  # pydantic models are JSON-serializable via .model_dump()
    # Convert Pydantic models to Python dicts first
    actors_dicts = [a.model_dump() for a in actors_list]
    pretty = json.dumps(actors_dicts, indent=2, ensure_ascii=False)
    return PlainTextResponse(pretty, media_type="application/json")


# ---------------------- SOCIAL RELATIONS ----------------------
@app.post("/social/relate/{a_id}/{b_id}", tags=["social"])
def relate(
    a_id: str,
    b_id: str,
    relatedness: str = Query("Neighbour", description="e.g., Stranger|Neighbour|Colleague|Friend|Family"),
    ):
    try:
        # Optional: validate that actors exist in our store
        if a_id not in DB.actors or b_id not in DB.actors:
            raise HTTPException(status_code=404, detail="Actor not found")
        SG.relate(a_id, b_id, relatedness=relatedness)
        return {"status": "ok", "a_id": a_id, "b_id": b_id, "relatedness": relatedness}
    except Exception as e:
        print(f"ERROR in /social/relate/{a_id}/{b_id}/", e)
        traceback.print_exc()
        raise  # FastAPI will surface the stack

@app.get("/social/relations", tags=["social"])
def list_relations():
    """Return all relations (edge list)."""
    return SG.to_edge_list()

@app.get("/social/relations/{actor_id}", tags=["social"])
def relations_for_actor(actor_id: str):
    """Return relations for a specific actor."""
    if actor_id not in DB.actors:
        raise HTTPException(status_code=404, detail="Actor not found")
    return SG.edges_for(actor_id) if hasattr(SG, "edges_for") else {
        "edges": [e for e in SG.to_edge_list()["edges"] if e["a_id"] == actor_id or e["b_id"] == actor_id]
    }

@app.post("/opportunities")
def create_ko(raw: dict):
    """
    Accept JSON:
    - actors: [{ actor_id: str, role: Role }]
    - actor_overrides: { actor_id: { psychological|social|motivations: [...] } }
    Build deep-copied Actor snapshots per opportunity and store them.
    """    
    try:
        # Basic validation
        if "id" not in raw or "name" not in raw or "actors" not in raw or "context" not in raw or "kindness_act" not in raw:
            raise HTTPException(status_code=422, detail="Missing required fields in opportunity payload")

        # Prepare lists and overrides
        actor_refs = raw.get("actors", [])
        overrides_by_actor = raw.pop("actor_overrides", {})  # remove from KO payload
        supporting_acts_raw = raw.get("supporting_acts", [])

        # Build deep copies (snapshots) as plain Actor instances
        snapshots: list[Actor] = []

        for ref in actor_refs:
            actor_id = ref.get("actor_id")
            role_value = ref.get("role")
            if not actor_id or not role_value:
                raise HTTPException(status_code=422, detail="Each actor entry must have actor_id and role")

            master = DB.get_actor(actor_id)
            if not master:
                raise HTTPException(status_code=404, detail=f"Actor '{actor_id}' not found")

            # Deep copy canonical Actor to create the per-opportunity snapshot
            snap: Actor = master.model_copy(deep=True)  # Pydantic v2; use .copy(deep=True) for v1
            snap.role = Role(role_value)  # set role for this opportunity

            # Apply overrides for this actor_id
            bundle = overrides_by_actor.get(actor_id, {})
            # psychological
            snap.psychological = [PsychologicalFactor(**pf) for pf in bundle.get("psychological", [])]
            # social
            snap.social = [SocialFactor(**sf) for sf in bundle.get("social", [])]

            #Motivations only for Giver; enforce towards_actor_id
            if snap.role == Role.GIVER:
                raw_mots = bundle.get("motivations", [])
                # Ensure there is a receiver in this opportunity to point to
                receiver_ref = next((a for a in actor_refs if a["role"] == "Receiver"), None)
                receiver_id  = receiver_ref["actor_id"] if receiver_ref else None

                validated = []
                for m in raw_mots:
                    m.setdefault("towards_actor_id", receiver_id)
                    validated.append(Motivation(**m))
                snap.motivations = validated
            else:
                snap.motivations = []

            snapshots.append(snap)

        
        # Convert supporting acts
        motivation_acts: list[MotivationAct] = []
        ability_acts: list[AbilityAct] = []
        prompt_acts: list[PromptAct] = []
        
        for act in supporting_acts_raw:
            kind = act.get("kind")
            if kind == "MotivationAct":
                motivation_acts.append(MotivationAct(**act))
            elif kind == "AbilityAct":
                ability_acts.append(AbilityAct(**act))
            elif kind == "PromptAct":
                prompt_acts.append(PromptAct(**act))
            else:
                # ignore unknown kinds or raise
                pass

        # Construct the domain opportunity object (actors = deep-copied Actor instances)
        ko = KindnessOpportunity(
            id=raw["id"],
            name=raw["name"],
            context=Context(**raw["context"]),
            kindness_act=KindnessAct(**raw["kindness_act"]),
            supporting_acts=supporting_acts_raw,
            actors=snapshots,
        )

        DB.upsert_opportunity(ko)

        # --- Engine checks ---
        giver = next((a for a in snapshots if a.role == Role.GIVER), None)
        if not giver:
            raise HTTPException(status_code=422, detail="Opportunity lacks a Giver")

        # Check kindness opportunity (Algorithm 1)
        is_ko = is_kindness_opportunity(
            motivations=giver.motivations,
            motivation_acts=motivation_acts,
        )
        
        # Base motivation score = other - self (from giver motivations)
        other = sum(m.level for m in giver.motivations if m.mtype == MotivationType.OTHER_BETTERMENT)
        self_ = sum(m.level for m in giver.motivations if m.mtype == MotivationType.SELF_BETTERMENT)
        base_motivation_score = other - self_

        # Check prompt readiness (Algorithm 2)
        prompt_ready = can_trigger_prompt(
            base_motivation_score=base_motivation_score,
            motivation_acts=motivation_acts,
            ability_acts=ability_acts,
            action_line=0.2,  # tweakable
        )        
        return {
                "status": "ok",
                "opportunity_id": ko.id,
                "is_kindness_opportunity": is_ko,
                "prompt_ready": prompt_ready,
            }
    except Exception as e:
        print("ERROR in /opportunities:", e)
        traceback.print_exc()
        raise  # FastAPI will surface the stack


@app.get("/opportunities/")
def list_ko():
    kos = DB.list_opportunities()
    if not kos:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return { "opportunities": kos}

@app.get("/opportunities/{ko_id}")
def get_ko(ko_id: str):
    ko = DB.get_opportunity(ko_id)
    if not ko:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return ko.model_dump()

@app.delete("/opportunities/{ko_id}")
def delete_ko(ko_id: str):
    deleted = DB.delete_opportunity(ko_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {"status": "ok", "deleted": ko_id}
