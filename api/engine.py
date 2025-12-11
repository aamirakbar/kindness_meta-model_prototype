
# api/engine.py

# Currently Impements the two algorithms of the meta-model


#Classify kindness opportunity (Algorithm 1)

from typing import List
from .models import Motivation, MotivationAct, MotivationType, AbilityAct

def is_kindness_opportunity(
    motivations: List[Motivation],
    motivation_acts: List[MotivationAct],
) -> bool:
    other_betterment = 0.0
    self_betterment  = 0.0

    # Giver's own motivations
    for m in motivations:
        if m.mtype == MotivationType.OTHER_BETTERMENT:
            other_betterment += m.level
        elif m.mtype == MotivationType.SELF_BETTERMENT:
            self_betterment += m.level

    # Effects of MotivationActs
    for act in motivation_acts:
        if act.increase_other_betterment:
            other_betterment += act.value
        #if act.decrease_self_betterment:
            #self_betterment -= act.value

    return other_betterment > self_betterment

# Triggering prompts (Algorithm 2)

def can_trigger_prompt(
    base_motivation_score: float,
    motivation_acts: List[MotivationAct],
    ability_acts: List[AbilityAct],
    action_line: float = 0.5,
) -> bool:
    total_motivation = base_motivation_score
    for act in motivation_acts:
        if act.increase_other_betterment:
            total_motivation += act.value
        #if act.decrease_self_betterment:
            #total_motivation += act.value  # subtracting self-betterment increases effective motivation

    total_ability = 0.0
    for act in ability_acts:
        total_ability += act.value if act.effect == "positive" else -act.value

    # Choose a simple, monotone action score; can be swapped later:
    action_score = 0.6 * total_motivation + 0.4 * total_ability
    return action_score >= action_line