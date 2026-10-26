"""Builds scripts\\data\\eft\\eft_quests.txt for eft_v2's Quests tab.

    python tools\\fetch_quests.py [output-path]

Data sources ( all public, no keys ):
    json.tarkov.dev/regular/tasks   tasks with BSG MongoIDs, objective zones with world
                                    positions + outlines, quest item spawn spots, item links
    json.tarkov.dev/regular/maps    map MongoID -> nameId ( "TarkovStreets", "RezervBase", ... )
    SPT server repo locales         readable names for tasks / traders / quest items
    json.tarkov.dev/regular/tasks_en
                                    tarkov.dev's own English task locale - fresher than the SPT
                                    repo, carries the description keys GraphQL would give
    api.tarkov.dev/graphql          objective descriptions ( best effort, retried )

One record per line, TAB separated ( the script parses it in one pass, no JSON ):
    eft-quests 2
    T  task id  name  trader  map nameId ( or "" )
    Z  task id  objective id  map nameId  x  y  z  type  description      a place to go / mark / plant / visit
    P  x  y  z                                                          outline point of the last Z
    N  item id  English name                                            any item an objective refers to
    Q  task id  objective id  item id  item name  map nameId  x  y  z    a quest item and where it can spawn
    I  task id  objective id  item id                                   an item the quest wants ( find / hand over )
    O  task id  objective id  count  type  description                  objective list line, for the panel

Task and objective ids are the game's own MongoIDs, the same values the client stores in
Profile.QuestsData, so "only accepted quests" and "hide completed objectives" match exactly.
"""
import json, os, re, sys, time, urllib.request, urllib.error

TASKS_URL  = "https://json.tarkov.dev/regular/tasks"
MAPS_URL   = "https://json.tarkov.dev/regular/maps"
TASKS_EN_URL = "https://json.tarkov.dev/regular/tasks_en"
LOCALES_URL = "https://raw.githubusercontent.com/sp-tarkov/server/master/project/assets/database/locales/global/en.json"
GRAPHQL_URL = "https://api.tarkov.dev/graphql"

DESC_QUERY = '{ tasks(lang: en) { id objectives { id description } } }'

UA = {"user-agent": "eft_v2-quests/2"}


def fetch_json(url, what, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        sys.exit("%s: HTTP %s %s" % (what, e.code, e.read().decode("utf-8", "replace")[:300]))
    except Exception as e:
        sys.exit("%s: %s" % (what, e))


def graphql_descriptions():
    """objective id -> description, from the GraphQL API. Best effort - it rate limits."""
    body = json.dumps({"query": DESC_QUERY}).encode()
    for attempt in range(2):
        try:
            req = urllib.request.Request(GRAPHQL_URL, body,
                                         {"content-type": "application/json", "user-agent": UA["user-agent"]})
            data = json.loads(urllib.request.urlopen(req, timeout=60).read())
            out = {}
            for t in (data.get("data") or {}).get("tasks") or []:
                for o in t.get("objectives") or []:
                    if o.get("description"):
                        out[o["id"]] = o["description"]
            if out:
                return out
        except Exception:
            pass
        time.sleep(2)
    return {}


def clean(s):
    return re.sub(r"[\t\r\n]+", " ", s or "").strip()


def prettify_key(s):
    """'bronze-pocket-watch-on-a-chain' -> 'Bronze pocket watch on a chain'"""
    words = re.split(r"[-_ ]+", (s or "").strip())
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def prettify_zone(zone_id):
    """'Sandbox_1_MedicalArea_exploration' -> 'Medical Area'"""
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]+|[a-z0-9]+", zone_id or "")
    drop = { "exploration", "zone", "place", "spawn", "area" }
    words = [w for w in words if w.lower() not in drop]
    while len(words) > 1 and words[0].lower() in { "sandbox", "factory", "customs", "woods", "shoreline", "interchange",
                                                  "laboratory", "lighthouse", "rezervbase", "tarkovstreets",
                                                  "bigmap", "terminal", "labyrinth", "icebreaker" }:
        words = words[1:]
    return " ".join(words) if words else (zone_id or "zone")


def fallback_text(o, type_names):
    t = o.get("type", "")
    zone = ""
    for z in o.get("zones") or []:
        zone = prettify_zone(z.get("id") or "")
        break
    n = o.get("count") or 1
    label = type_names.get(t, t)
    if t == "shoot":
        names = ", ".join(prettify_key(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)) for s in o.get("targetNames") or [])
        return "Kill %d%s" % (n, " (" + names + ")" if names else "")
    if t == "extract":
        return "%s%s" % (label, (": " + o.get("exitName")) if o.get("exitName") else "")
    if t in ("visit", "mark", "useItem", "plantItem", "plantQuestItem", "experience", "skill") and zone:
        return "%s: %s" % (label, zone)
    if zone:
        return "%s: %s" % (label, zone)
    if t in ("giveItem", "findItem", "sellItem"):
        return "%s %s item%s" % (label, n, "" if n == 1 else "s")
    return label


def resolve_desc(oid, raw, loc):
    """The dump's description fields are raw locale keys ('65732ac3...'), the readable text sits in
    the GraphQL reply. When that's down, try the SPT locale, then compose from the objective data."""
    if raw and not re.match(r"^[0-9a-f]{24}(\s|$)", raw):
        return clean(raw)
    for key in (oid + " description", oid + " Name", oid):
        hit = loc.get(key)
        if hit:
            return clean(hit)
    return ""


def main():
    tasks_raw = fetch_json(TASKS_URL, "tarkov.dev tasks").get("data") or {}
    tasks = tasks_raw.get("tasks") or {}
    if not tasks:
        sys.exit("tarkov.dev tasks: empty reply")

    maps_raw = fetch_json(MAPS_URL, "tarkov.dev maps").get("data") or {}
    maps = maps_raw.get("maps") or {}
    map_name = {}
    for mid, m in maps.items():
        nid = (m.get("nameId") or "").lower()
        if nid:
            map_name[mid] = nid

    quest_items = tasks_raw.get("questItems") or {}

    # readable names from the SPT locale table; degrade to slugs when it can't be fetched
    loc = {}
    try:
        loc = fetch_json(LOCALES_URL, "SPT locales")
    except SystemExit:
        print("SPT locales unreachable - falling back to slugs")

    # tarkov.dev's own task locale ( tip of the hat to tomo's tasks.py ): fresher than the
    # SPT repo, and it carries description keys for the objectives that have real text -
    # the GraphQL API serves those too but has been unreachable all week. Non-empty values
    # win over the SPT table; the bare 24-hex entries with empty values are skipped.
    try:
        ten = fetch_json(TASKS_EN_URL, "tarkov.dev task locales")
        ten = ten.get("data", ten) if isinstance(ten, dict) else {}
        added = 0
        for k, v in ten.items():
            if isinstance(v, str) and v and v != loc.get(k):
                loc[k] = v
                added += 1
        print("tasks_en: %d locale keys merged" % added)
    except SystemExit:
        print("tasks_en unavailable - staying with SPT locales")

    def task_name(qid):
        n = loc.get(qid + " name")
        if n:
            return clean(n)
        slug = tasks[qid].get("wikiLink") or ""
        return prettify_key(slug.rsplit("/", 1)[-1]) if slug else "Task " + qid[:8]

    def trader_name(tid):
        return clean(loc.get((tid or "") + " Nickname") or "")

    def qi_name(qid):
        qi = quest_items.get(qid) or {}
        # the full name: in-raid labels and map markers read "Bronze pocket watch", not "Watch"
        n = loc.get(qid + " Name") or qi.get("name") or loc.get(qid + " ShortName") or qi.get("shortName")
        if n and not re.match(r"^[0-9a-f]{24} ", n):
            return clean(n)
        return prettify_key(qi.get("normalizedName") or "Quest item")

    descs = graphql_descriptions()
    if not descs:
        print("tarkov.dev GraphQL unavailable - objective descriptions fall back to zone names")

    type_names = {
        "visit": "Visit", "mark": "Mark", "useItem": "Use", "experience": "Do", "skill": "Raise skill",
        "giveItem": "Hand over", "findItem": "Find", "plantItem": "Plant", "sellItem": "Sell",
        "extract": "Extract", "shoot": "Kill", "findQuestItem": "Find", "giveQuestItem": "Hand over",
        "plantQuestItem": "Plant", "buildWeapon": "Build", "taskStatus": "Task", "traderLevel": "Trader level",
        "traderStanding": "Standing", "globalVariable": "Objective", "dialogue": "Talk",
    }

    out = ["eft-quests 2"]
    nz = nq = ni = no = 0
    seen = set()
    for tid in sorted(tasks):
        t = tasks[tid]
        tmap = map_name.get(t.get("map") or "", "") if isinstance(t.get("map"), str) else ""
        out.append("\t".join(["T", tid, task_name(tid), trader_name(t.get("trader")), tmap]))

        for o in t.get("objectives") or []:
            oid = o.get("id") or ""
            # GraphQL wording first ( exact in-game text ), then the BSG locale, then a composed fallback
            desc = descs.get(oid) or resolve_desc(oid, o.get("description"), loc)
            if not desc:
                desc = fallback_text(o, type_names)
            desc = clean(desc)
            count = o.get("count") or 1

            # every objective, for the active-quests panel
            out.append("\t".join(["O", tid, oid, str(count), clean(o.get("type", "")), desc]))
            no += 1

            # zones with real world positions (+ outlines)
            for z in o.get("zones") or []:
                mid = z.get("map")
                mp = map_name.get(mid, (mid or "").lower() if isinstance(mid, str) else "")
                pos = z.get("position") or {}
                if not (isinstance(pos.get("x"), (int, float)) and (pos["x"], pos["y"], pos["z"]) != (0, 0, 0)):
                    continue
                key = (tid, oid, mp, round(pos["x"], 2), round(pos["y"], 2), round(pos["z"], 2))
                if key in seen:
                    continue
                seen.add(key)
                out.append("\t".join(["Z", tid, oid, mp, "%.2f" % pos["x"], "%.2f" % pos["y"], "%.2f" % pos["z"],
                                      clean(o.get("type", "")), desc]))
                nz += 1
                outline = z.get("outline") or []
                if 3 <= len(outline) <= 64:
                    for p in outline:
                        if isinstance(p.get("x"), (int, float)):
                            out.append("\t".join(["P", "%.2f" % p["x"], "%.2f" % p["y"], "%.2f" % p["z"]]))

            # quest items: where they can spawn + the item link
            qi = o.get("questItem")
            if isinstance(qi, str) and qi:
                for loc_ in o.get("possibleLocations") or []:
                    mid = loc_.get("map")
                    mp = map_name.get(mid, (mid or "").lower() if isinstance(mid, str) else "")
                    for pos in loc_.get("positions") or []:
                        if not isinstance(pos.get("x"), (int, float)):
                            continue
                        out.append("\t".join(["Q", tid, oid, qi, qi_name(qi), mp,
                                              "%.2f" % pos["x"], "%.2f" % pos["y"], "%.2f" % pos["z"]]))
                        nq += 1
                out.append("\t".join(["I", tid, oid, qi]))
                ni += 1

            for it in o.get("items") or []:
                if isinstance(it, str) and re.match(r"^[0-9a-f]{24}$", it):
                    out.append("\t".join(["I", tid, oid, it]))
                    ni += 1

            mk = o.get("markerItem")
            if isinstance(mk, str) and re.match(r"^[0-9a-f]{24}$", mk):
                out.append("\t".join(["I", tid, oid, mk]))
                ni += 1

    # N rows: an English name for every item an objective refers to. Quest items and hand-over documents are missing
    # from tarkov.dev's item table, and the game's own name for some is Russian - the script labels them from these.
    linked = sorted({r.split("\t")[3] for r in out if r.startswith(("I\t", "Q\t"))})
    nn = 0
    for it in linked:
        n = loc.get(it + " Name") or (quest_items.get(it) or {}).get("name")
        if n and not re.match(r"^[0-9a-f]{24} ", n):
            out.append("\t".join(["N", it, clean(n)]))
            nn += 1
    print("%d item names for objective items" % nn)

    text = "\n".join(out) + "\n"
    dest = os.path.expandvars(r"%APPDATA%\scripts\data\eft\eft_quests.txt") if len(sys.argv) < 2 else sys.argv[1]
    d = os.path.dirname(dest)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("%d tasks, %d objectives, %d zones, %d quest-item spots, %d item links -> %s"
          % (len(tasks), no, nz, nq, ni, dest))


if __name__ == "__main__":
    main()
