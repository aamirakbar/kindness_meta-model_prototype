# models.py
from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

# --- Enums matching the meta-model ---
class MotivationType(str, Enum):
    OTHER_BETTERMENT = "Other_Betterment"
    SELF_BETTERMENT  = "Self_Betterment"

class FactorIntensity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# --- Core factors ---
class PsychologicalFactor(BaseModel):
    kind: str              # e.g., "Emotion", "SelfEfficacy", "CharacterTrait", "HumanValue"
    value: str             # e.g., "Empathy", "Agreeableness", "Benevolence"
    level: FactorIntensity

class SocialFactor(BaseModel):
    kind: str              # e.g., "LevelOfNeed", "OpportunityToConnect", "Relatedness", "Trust"
    value: str             # e.g., "HealthRelated", "Friend", "High"
    level: FactorIntensity

# --- Motivations ---
class Motivation(BaseModel):
    mtype: MotivationType
    level: float = Field(ge=-1.0, le=1.0)  # as defined in the meta-model: -1..1 for negative..positive 
    towards_actor_id: str | None = Field(default=None)  # capture the target of the motivation (Receiver)

# --- Actors & roles ---

class Role(str, Enum):
    GIVER = "Giver"
    RECEIVER = "Receiver"
    OBSERVER = "Observer"

class Actor(BaseModel):
    id: str
    name: str
    type: str = "Human"  # or "Software"
    role: Role | None = Field(default=None)
    base_other_betterment: float = Field(default=0.0, ge=-1.0, le=1.0)
    base_self_betterment: float = Field(default=0.0, ge=-1.0, le=1.0)
    motivations: List[Motivation] = Field(default_factory=list)
    psychological: List[PsychologicalFactor] = Field(default_factory=list)
    social: List[SocialFactor] = Field(default_factory=list)


# --- Acts ---
class Condition(BaseModel):
    name: str     # pre-condition or post-condition
    value: str    # could embed BRS-like strings

class Act(BaseModel):
    name: str
    pre: Optional[Condition] = None
    post: Optional[Condition] = None

class KindnessAct(Act):
    pass

class SupportingAct(Act):
    kind: str = Field(default="SupportingAct")  # helpful for client payload

class MotivationAct(SupportingAct):    
    kind: str = Field(default="MotivationAct")
    # meta-model attributes
    type: str = Field(default="personal", description="e.g., personal|social|functional")
    time: Optional[str] = None
    frequency: Optional[str] = None
    intensity: str = Field(default="Weak", description="Weak|Strong")
    # engine-facing fields
    value: float = Field(default=0.0, ge=0.0, le=1.0)  # non-negative (magnitude of effect)
    increase_other_betterment: bool = Field(
        default=True,
        description="If true, this act boosts the giver's other-betterment motivation.",
    )
    decrease_self_betterment: bool = Field(
        default=False,
        description="If true, this act reduces the giver's self-betterment motivation.",
    )


class AbilityAct(SupportingAct):
    kind: str = Field(default="AbilityAct")
    # meta-model attributes
    domain: str = Field(default="physical", description="physical|digital")
    effort_target: Optional[str] = Field(default=None, description="what effort this reduces")
    #intensity: str = Field(default="Medium", description="Low|Medium|High")
    # engine-facing fields
    effect: str = Field(default="positive", pattern="^(positive|negative)$")
    value: float = Field(default=0.0, ge=0.0, le=1.0)


class PromptAct(SupportingAct):
    kind: str = Field(default="PromptAct")
    channel: str = Field(default="app_notification")
    message: str = Field(default="Please perform the kindness act now.")
    #when: Optional[str] = None  # time


# --- Context ---
class Context(BaseModel):
    name: str # name of the context
    location: str  # physical or digital
    time: str  # absolute or relative

# --- The core opportunity ---
class KindnessOpportunity(BaseModel):
    id: str
    name: str
    actors: List[Actor]
    context: Context
    kindness_act: KindnessAct
    supporting_acts: List[SupportingAct] = []
