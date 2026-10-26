"""Builds scripts\\data\\eft\\eft_items.txt for eft_v2's item names and prices.

    python tools\\fetch_items.py [output-path]

Source: json.tarkov.dev/regular/items ( flea price first, trader base price as fallback ).
Format the script's load_items() parses:
    eft-items 2
    I  template id  price  name
"""
import json, os, re, sys, urllib.request, urllib.error

ITEMS_URL = "https://json.tarkov.dev/regular/items"
ITEMS_EN_URL = "https://json.tarkov.dev/regular/items_en"   # translation key -> English text
LOCALES_URL = "https://raw.githubusercontent.com/sp-tarkov/server/master/project/assets/database/locales/global/en.json"
UA = {"user-agent": "eft_v2-items/2"}


def fetch_json(url, what, timeout):
    req = urllib.request.Request(url, headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        sys.exit("%s: HTTP %s %s" % (what, e.code, e.read().decode("utf-8", "replace")[:300]))
    except Exception as e:
        sys.exit("%s: %s" % (what, e))


def main():
    data = fetch_json(ITEMS_URL, "tarkov.dev items", 180)
    items = (data.get("data") or {}).get("items") or {}
    if not items:
        sys.exit("tarkov.dev items: empty reply")

    # The item list's names are translation keys ( "<id> ShortName" ); items_en turns them into English. It covers
    # items the SPT locale doesn't have yet, which left ~1500 rows named "ShortName".
    en = {}
    try:
        en = fetch_json(ITEMS_EN_URL, "tarkov.dev items_en", 120).get("data") or {}
    except SystemExit:
        print("tarkov.dev items_en unreachable - falling back to the SPT locale")

    loc = {}
    try:
        loc = fetch_json(LOCALES_URL, "SPT locales", 120)
    except SystemExit:
        print("SPT locales unreachable - names will need GraphQL or the next run")

    def real(n):
        return n if n and n.strip() not in ("ShortName", "Name") and not re.match(r"^[0-9a-f]{24} ", n) else ""

    def item_name(iid, it):
        n = (real(en.get(it.get("shortName") or "")) or real(en.get(iid + " ShortName"))
             or real(loc.get(iid + " ShortName")) or real(en.get(it.get("name") or "")) or real(loc.get(iid + " Name")))
        if n:
            return re.sub(r"[\t\r\n]+", " ", n).strip()
        # locale failed: the dump's own fields are '{id} ShortName' keys, not readable text
        n = re.sub(r"^[0-9a-f]{24}\s*", "", it.get("shortName") or it.get("name") or "")
        return re.sub(r"[\t\r\n]+", " ", n).strip()

    out = ["eft-items 2"]
    for iid in sorted(items):
        it = items[iid]
        price = it.get("lastLowPrice") or it.get("basePrice") or 0
        name = item_name(iid, it)
        if not re.match(r"^[0-9a-f]{24}$", iid) or not name:
            continue
        out.append("\t".join(["I", iid, str(price), name]))

    text = "\n".join(out) + "\n"
    dest = os.path.expandvars(r"%APPDATA%\scripts\data\eft\eft_items.txt") if len(sys.argv) < 2 else sys.argv[1]
    d = os.path.dirname(dest)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("%d items -> %s" % (len(out) - 1, dest))


if __name__ == "__main__":
    main()
