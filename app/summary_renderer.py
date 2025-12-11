
# app/summary_renderer.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


# ------------------------------ Helpers ------------------------------ #

def _fmt_header(title: str, char: str = "=") -> str:
    bar = char * max(10, len(title) + 4)
    return f"\n{bar}\n{title}\n{bar}\n"

def _fmt_subheader(title: str, char: str = "-") -> str:
    bar = char * max(10, len(title) + 4)
    return f"\n{title}\n{bar}\n"

def _fmt_kv(k: str, v: Any) -> str:
    return f"{k}: {v}"

def _indent(text: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())

def _range_label(x: float) -> str:
    """
    Interpret motivation level per meta-model:
      -1..-0.5 : strong harm focused
      -0.5..0  : weak  harm focused
       0       : indifferent
       0..0.5  : weak  betterment focused
       0.5..1  : strong betterment focused
    """
    if x < -0.5: return "strong harm focused"
    if x < 0.0:  return "weak harm focused"
    if x == 0.0: return "indifferent"
    if x < 0.5:  return "weak betterment focused"
    return "strong betterment focused"


# ------------------------------ Data view ---------------------------- #

@dataclass
class OpportunityEventView:
    ko_id: str
    name: str
    timestamp: int
    giver_id: str
    receiver_id: str
    observer_id: str
    kindness_act_name: str
    is_ko: bool
    prompt_ready: bool
    # Optional diagnostics from API
    base_motivation_score: Optional[float] = None


# ------------------------------ Renderer ----------------------------- #

def render_event_summary(
    event: OpportunityEventView,
    ko_payload: Dict[str, Any],
    ko_response: Dict[str, Any],
    # snapshots_from_api: Optional[Dict[str, Any]] = None, 
) -> str:
    """
    Build a full summary string for one opportunity event:
      - context
      - actors (roles)
      - factors for Giver/Receiver (from actor_overrides)
      - motivations (Giver only)
      - supporting acts (MotivationAct, AbilityAct, PromptAct)
      - engine outcomes (is kindness opportunity? prompt ready?)
    ko_payload: the exact dict you POSTed to /opportunities (contains actor_overrides and supporting_acts)
    ko_response: the dict returned by /opportunities (contains flags)
    """
    name = f"[t={event.timestamp:03d}] {event.name}"
    out = [_fmt_header(name)]

    # --- Core IDs and roles ---
    out.append(_fmt_subheader("Actors"))
    out.append(_indent(_fmt_kv("Giver", event.giver_id)))
    out.append(_indent(_fmt_kv("Receiver", event.receiver_id)))
    out.append(_indent(_fmt_kv("Observer", event.observer_id)))

    # --- Context & Act ---
    ctx = ko_payload.get("context", {})
    act = ko_payload.get("kindness_act", {})
    out.append(_fmt_subheader("Context"))
    out.append(_indent(_fmt_kv("Location", ctx.get("location", "N/A"))))
    out.append(_indent(_fmt_kv("Time", ctx.get("time", "N/A"))))

    out.append(_fmt_subheader("Kindness Act"))
    out.append(_indent(_fmt_kv("Name", act.get("name", "N/A"))))
    if "pre" in act:
        out.append(_indent("Pre: " + json.dumps(act["pre"], ensure_ascii=False)))
    if "post" in act:
        out.append(_indent("Post: " + json.dumps(act["post"], ensure_ascii=False)))

    # --- Factors per actor (from overrides) ---
    overrides = ko_payload.get("actor_overrides", {})

    def _render_factors_for(actor_id: str, role_label: str) -> str:
        bundle = overrides.get(actor_id, {})
        lines = [f"{role_label} ({actor_id})"]
        # Psychological
        psych: List[Dict[str, Any]] = bundle.get("psychological", [])
        if psych:
            lines.append("  Psychological_Factors:")
            for pf in psych:
                lines.append(f"    - {pf['kind']}: {pf['value']} ({pf['level']})")
        # Social
        social: List[Dict[str, Any]] = bundle.get("social", [])
        if social:
            lines.append("  Social_Factors:")
            for sf in social:
                lines.append(f"    - {sf['kind']}: {sf['value']} ({sf['level']})")
        # Motivations (Giver only)
        motivations: List[Dict[str, Any]] = bundle.get("motivations", [])
        if motivations:
            lines.append("  Motivations (towards Receiver):")
            for m in motivations:
                lvl = m.get("level", 0.0)
                label = _range_label(lvl)
                lines.append(
                    f"    - {m['mtype']}: {lvl:.2f} [{label}]"
                    + (f" -> {m.get('towards_actor_id')}" if m.get("towards_actor_id") else "")
                )
        return "\n".join(lines)

    out.append(_fmt_subheader("Factors"))
    out.append(_indent(_render_factors_for(event.giver_id, "Giver")))
    out.append("")
    out.append(_indent(_render_factors_for(event.receiver_id, "Receiver")))

    # --- Supporting Acts ---
    out.append(_fmt_subheader("Supporting Acts"))
    acts: List[Dict[str, Any]] = ko_payload.get("supporting_acts", [])
    if not acts:
        out.append(_indent("None"))
    else:
        # Ensure PromptAct last for display order
        mot_acts = [a for a in acts if a.get("kind") == "MotivationAct"]
        abl_acts = [a for a in acts if a.get("kind") == "AbilityAct"]
        prm_acts = [a for a in acts if a.get("kind") == "PromptAct"]

        if mot_acts:
            out.append(_indent("MotivationActs:"))
            for a in mot_acts:
                out.append(_indent(
                    f"- {a.get('name','MotivationAct')} | type={a.get('type')} "
                    f"intensity={a.get('intensity')} value={a.get('value',0)} "
                    f"increase_other_betterment={a.get('increase_other_betterment',False)} "
                    f"decrease_self_betterment={a.get('decrease_self_betterment',False)}", 4
                ))

        if abl_acts:
            out.append(_indent("AbilityActs:"))
            for a in abl_acts:
                out.append(_indent(
                    f"- {a.get('name','AbilityAct')} | domain={a.get('domain')} "
                    f"intensity={a.get('intensity')} effect={a.get('effect')} value={a.get('value',0)} "
                    f"effort_target={a.get('effort_target')}", 4
                ))

        if prm_acts:
            out.append(_indent("PromptActs (last):"))
            for a in prm_acts:
                out.append(_indent(
                    f"- {a.get('name','PromptAct')} | channel={a.get('channel')} "
                ))

    # --- Engine results ---
    out.append(_fmt_subheader("Engine Results"))
    out.append(_indent(_fmt_kv("KindnessOpportunity", "YES" if event.is_ko else "NO")))
    out.append(_indent(_fmt_kv("Prompt Ready", "YES" if event.prompt_ready else "NO")))
    if event.base_motivation_score is not None:
        out.append(_indent(_fmt_kv("Base Motivation Score (other - self)", f"{event.base_motivation_score:.3f}")))

    # Final trailing bar
    out.append("\n" + ("=" * 60) + "\n")
    return "\n".join(out)
