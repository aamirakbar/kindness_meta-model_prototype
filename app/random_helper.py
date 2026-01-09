# random_helper.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

#--------------------------- Random helpers ------------------------- #


# FactorIntensity (strings must match Model Enum): "Low" | "Medium" | "High"
def pick_intensity(rand, weights=(0.2, 0.5, 0.3)) -> str:
    """Weighted choice for intensity: Low/Medium/High."""
    r = rand.random()
    if r < weights[0]:
        return "Low"
    elif r < weights[0] + weights[1]:
        return "Medium"
    else:
        return "High"

def pick_emotion(rand) -> tuple[str, str]:
    """Return (value, level). Values per meta-model."""
    value = rand.choice(["Happiness", "Sadness"])
    level = pick_intensity(rand)
    return value, level

def pick_self_efficacy(rand) -> tuple[str, str]:
    value = rand.choice([
        "ExpressPositiveEmotions",
        "ControlNegativeEmotions",
        "MeetOthersNeeds",
        "AbbilityToShare",
    ])
    level = pick_intensity(rand)
    return value, level

def pick_character_trait(rand) -> tuple[str, str]:
    value = rand.choice(["Openness", "Agreeableness"])
    level = pick_intensity(rand)
    return value, level

def pick_human_value(rand) -> tuple[str, str]:
    value = rand.choice(["Benevolence", "Universalism"])
    level = pick_intensity(rand)
    return value, level

def pick_level_of_need(rand) -> tuple[str, str]:
    value = rand.choice(["Emotional", "Instrumental", "HealthRelated"])
    level = pick_intensity(rand)
    return value, level

def pick_opportunity_to_connect(rand) -> tuple[str, str]:
    value = rand.choice([
        "StartRelationship",
        "KeepRelationship",
        "StrengthenRelationship",
        "KeepOldFriend",
        "StrengthenFamilyTies",
    ])
    level = pick_intensity(rand)
    return value, level

def pick_relatedness(rand) -> tuple[str, str]:
    """Relatedness as SocialFactor.value; intensity used as signal strength."""
    value = rand.choice(["Family", "Friend", "Neighbour", "Colleague", "Stranger"])
    level = pick_intensity(rand)
    return value, level

def pick_trust(rand) -> tuple[str, str]:
    """Trust value 'Familiarity' per your meta-model, with intensity."""
    value = "Familiarity"
    level = pick_intensity(rand)
    return value, level


# --------------------------- Motivation heuristic ------------------- #

def compute_motivation_levels(rand, psych: List[dict], social: List[dict]) -> tuple[float, float]:
    """
    Return (other_betterment, self_betterment) ∈ [-1.0, 1.0], derived from factors.

    This heuristic is tuned to produce a MIX of cases where:
      - other_betterment > self_betterment
      - self_betterment > other_betterment
    """
    # Extract useful signals
    emotion = next((f for f in psych if f["kind"] == "Emotion"), None)
    seff   = next((f for f in psych if f["kind"] == "SelfEfficacy"), None)
    related = next((f for f in social if f["kind"] == "Relatedness"), None)
    trust   = next((f for f in social if f["kind"] == "Trust"), None)
    need    = next((f for f in social if f["kind"] == "LevelOfNeed"), None)

    # Base scores: small random offset so we naturally get a mix of cases
    other = rand.uniform(-0.1, 0.1)
    self_ = rand.uniform(-0.1, 0.1)

    # Emotion signal (balanced effect on self and other)
    if emotion:
        lvl = {"Low": 0.15, "Medium": 0.35, "High": 0.6}.get(emotion["level"], 0.25)
        if emotion["value"].lower() == "happiness":
            other += 0.25 * lvl
            self_ += 0.25 * lvl
        else:  # sadness
            other -= 0.25 * lvl
            self_ -= 0.25 * lvl

    # Trust signal (primarily other-oriented, slightly self-protective)
    if trust:
        lvl_other = {"Low": -0.15, "Medium": 0.10, "High": 0.25}.get(trust["level"], 0.0)
        other += lvl_other
        if trust["level"] == "Low":
            self_ -= 0.05  # withdrawal when trust is low

    # Relatedness closeness (reduced weight so other isn't almost always higher)
    if related:
        closeness = {
            "Family": 0.25, "Friend": 0.20, "Neighbour": 0.10,
            "Colleague": 0.05, "Stranger": -0.15,
        }.get(related["value"], 0.0)
        mult = {"Low": 0.5, "Medium": 0.8, "High": 1.0}.get(related["level"], 0.7)
        other += closeness * mult

    # Self-efficacy → primarily self-betterment, with a small prosocial spillover
    if seff:
        lvl = {"Low": -0.10, "Medium": 0.15, "High": 0.30}.get(seff["level"], 0.0)
        self_ += lvl
        other += 0.1 * lvl

    # Level of need → modest altruism tilt
    if need:
        lvl = {"Low": 0.03, "Medium": 0.10, "High": 0.18}.get(need["level"], 0.0)
        other += lvl

    # Additional small noise for variety
    other += rand.uniform(-0.1, 0.1)
    self_ += rand.uniform(-0.1, 0.1)

    # Clamp to [-1, 1]
    other = max(-1.0, min(1.0, other))
    self_ = max(-1.0, min(1.0, self_))
    return other, self_


def build_overrides_for_actor(
        rand, 
        role: str, 
        target_id: str | None = None,
        inject_social_signals: Dict[str, str] | None = None,
    ) -> dict:
    """
    build per-actor overrides aligned with the meta-model:
    - Giver: psych + social + motivations (towards target_id)
    - Receiver: psych + social
    Create psychological + social factors, and motivation levels derived from them.
    Output shape matches the API's expected 'actor_overrides' bundle.
    """    
    # Observer: no overrides
    if role == "Observer":
        return {}

    # Psychological factors
    emo_v, emo_lvl = pick_emotion(rand)
    se_v, se_lvl   = pick_self_efficacy(rand)
    ct_v, ct_lvl   = pick_character_trait(rand)
    hv_v, hv_lvl   = pick_human_value(rand)

    psych = [
        {"kind": "Emotion",        "value": emo_v, "level": emo_lvl},
        {"kind": "SelfEfficacy",   "value": se_v,  "level": se_lvl},
        {"kind": "CharacterTrait", "value": ct_v,  "level": ct_lvl},
        {"kind": "HumanValue",     "value": hv_v,  "level": hv_lvl},
    ]

    # Social factors
    # Allow the simulation to inject relationship-derived signals (e.g., Relatedness, Trust)
    if inject_social_signals and "Relatedness" in inject_social_signals:
        rel_v = inject_social_signals["Relatedness"]
        rel_lvl = pick_intensity(rand)    
    else:
        rel_v, rel_lvl = pick_relatedness(rand)

    
    if inject_social_signals and "Trust" in inject_social_signals:
        trust_v = inject_social_signals["Trust"]
        trust_lvl = pick_intensity(rand)
    else:
        trust_v, trust_lvl = pick_trust(rand)

    need_v, need_lvl   = pick_level_of_need(rand)
    otc_v, otc_lvl     = pick_opportunity_to_connect(rand)
    

    social = [
        {"kind": "LevelOfNeed",        "value": need_v,   "level": need_lvl},
        {"kind": "OpportunityToConnect","value": otc_v,   "level": otc_lvl},
        {"kind": "Relatedness",        "value": rel_v,    "level": rel_lvl},
        {"kind": "Trust",              "value": trust_v,  "level": trust_lvl},
    ]

    # Motivations derived from factors    
    motivations: List[dict] = []
    if role == "Giver":
        other, self_ = compute_motivation_levels(rand, psych, social)
        motivations = [
            {"mtype": "Other_Betterment", "level": round(other, 2),  "towards_actor_id": target_id},
            {"mtype": "Self_Betterment",  "level": round(self_, 2), "towards_actor_id": target_id},
        ]

    return {
        "psychological": psych,
        "social": social,
        "motivations": motivations,
    }
