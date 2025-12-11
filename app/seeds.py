# app/seeds.py
import json
import http.client
import copy

BASE = "localhost"
PORT = 8000

def post(path, payload):
    conn = http.client.HTTPConnection(BASE, PORT)
    headers = {"Content-type": "application/json"}
    body = json.dumps(payload) if payload else None
    conn.request("POST", path, body, headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    print(f"POST {path} -> {resp.status} {resp.reason}\n{data}\n")
    conn.close()


def upsert_actor_with_overrides(baseline_actor: dict, overrides: dict):
    """
    Merge 'overrides' (psychological, social, motivations) into a baseline actor dict
    and POST to /actors (upsert).
    """
    merged = copy.deepcopy(baseline_actor)
    for key in ("psychological", "social", "motivations"):
        if key in overrides:
            merged[key] = overrides[key]  # replace lists entirely for simplicity
    post("/actors", merged)


def load_json(fp):
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    # 1) canonical actors
    actors_list = load_json("app/data/scenarios/actors.json")
    for a in actors_list:
        a.setdefault("role", None)
        a.setdefault("psychological", [])
        a.setdefault("social", [])
        a.setdefault("motivations", [])
        post("/actors", a)

    # 2) social relations (unchanged)
    links = load_json("app/data/scenarios/social_links.json")
    for l in links:
        path = f"/social/relate/{l['a_id']}/{l['b_id']}?relatedness={l.get('relatedness','Neighbour')}"
        post(path, {})

    # 3) opportunities (post raw; server deep-copies actors)
    files = ["natural_kindness.json"]
    for name in files:
        ko = load_json(f"app/data/scenarios/{name}")
        post("/opportunities", ko)

if __name__ == "__main__":
    main()



'''"kindness_alignment_social.json",
        "kindness_alignment_cultural.json",
        "kindness_on_the_edge_maria.json",
        "kindness_on_the_edge_li.json",'''