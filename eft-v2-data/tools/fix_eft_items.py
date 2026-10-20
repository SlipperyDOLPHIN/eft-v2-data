#!/usr/bin/env python
# Repairs eft_items.txt: fills in the rows whose name column is the placeholder "ShortName".
#
# The file is the item table eft_v2.as loads ( data/eft/eft_items.txt ): a header line, then
#   I \t <24-hex template id> \t <rouble price> \t <short name>
# A broken export left ~1800 rows with the literal name "ShortName". This rewrites only those
# rows, keeping every price and every good name. Prefers tarkov.dev ( complete, current prices );
# falls back to the TarkovTracker mirror for whatever tarkov.dev can't serve.
#
# Usage:  python -I fix_eft_items.py [path-to-eft_items.txt]

import json
import sys
import urllib.request

ITEMS_TXT = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\longh\AppData\Roaming\scripts\data\eft\eft_items.txt"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def strip_suffix(name):
    # Preset rows come back as "AK-74N Default" - the game shows just the weapon name.
    return name[:-8] if name.endswith(" Default") else name


def from_tarkov_dev():
    # id -> (shortName, price). Price is the flea average, basePrice when an item has no flea.
    q = '{items{id shortName avg24hPrice basePrice}}'
    body = json.dumps({"query": q}).encode()
    req = urllib.request.Request(
        "https://api.tarkov.dev/graphql", data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Origin": "https://tarkov.dev", "Referer": "https://tarkov.dev/"})
    raw = urllib.request.urlopen(req, timeout=90).read()
    data = json.loads(raw).get("data")
    if not data or not data.get("items"):
        raise RuntimeError("tarkov.dev returned no items: " + raw[:200].decode("utf-8", "replace"))
    out = {}
    for it in data["items"]:
        sn = it.get("shortName")
        if not sn:
            continue
        price = it.get("avg24hPrice") or it.get("basePrice") or 0
        out[it["id"]] = (sn, int(price))
    return out


def from_mirror():
    url = "https://raw.githubusercontent.com/TarkovTracker/tarkovdata/master/items.en.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = json.loads(urllib.request.urlopen(req, timeout=90).read())
    out = {}
    for tid, v in data.items():
        sn = v.get("shortName")
        if sn:
            out[tid] = strip_suffix(sn)
    return out


def from_ratstash():
    # The game's own locale ( SPT format ): keys like "<id> ShortName". More complete than the mirror for
    # older items, but a stale snapshot - it won't have the newest wipe's items ( those need tarkov.dev ).
    url = ("https://raw.githubusercontent.com/RatScanner/RatStash/master/"
           "RatStashTest/TestData/locales/en.json")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    loc = json.loads(urllib.request.urlopen(req, timeout=90).read())
    out = {}
    for k, v in loc.items():
        if k.endswith(" ShortName") and v and v.strip():
            out[k[:-10]] = strip_suffix(v)
    return out


def main():
    dev = {}
    try:
        dev = from_tarkov_dev()
        print("tarkov.dev: {} items".format(len(dev)))
    except Exception as e:
        print("tarkov.dev unavailable ({}), using mirror only".format(e))

    mirror = {}
    try:
        mirror = from_ratstash()
        print("ratstash locale: {} items".format(len(mirror)))
    except Exception as e:
        print("ratstash unavailable ({})".format(e))
    try:
        tt = from_mirror()
        for tid, sn in tt.items():
            mirror.setdefault(tid, sn)   # tarkovtracker fills any gaps ratstash left
        print("mirror total: {} items".format(len(mirror)))
    except Exception as e:
        print("tarkovtracker mirror unavailable ({})".format(e))

    with open(ITEMS_TXT, encoding="utf-8") as f:
        lines = f.read().split("\n")

    fixed = still = 0
    out = []
    for line in lines:
        p = line.split("\t")
        if len(p) >= 4 and p[0] == "I" and p[3] == "ShortName":
            tid = p[1]
            if tid in dev:
                sn, price = dev[tid]
                p[3] = strip_suffix(sn)
                if price > 0:
                    p[2] = str(price)
                fixed += 1
            elif tid in mirror:
                p[3] = mirror[tid]
                fixed += 1
            else:
                still += 1
            out.append("\t".join(p))
        else:
            out.append(line)

    backup = ITEMS_TXT + ".bak"
    with open(backup, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(ITEMS_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print("fixed {} rows, {} still unresolved".format(fixed, still))
    print("backup written to " + backup)


if __name__ == "__main__":
    main()
