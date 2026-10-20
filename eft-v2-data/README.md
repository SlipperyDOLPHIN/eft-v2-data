# eft-v2-data

The item and quest tables the eft_v2 script downloads every time it loads, so players don't need an updater.

| File | What | Built by |
|---|---|---|
| `data/eft_items.txt` | item names + prices | `tools/fetch_items.py` then `tools/fix_eft_items.py` |
| `data/eft_quests.txt` | quest objectives, zones, outlines, quest items | `tools/fetch_quests.py` |

A GitHub Action (`.github/workflows/update-data.yml`) rebuilds both every day from tarkov.dev's public data and
the SPT locale files, and commits them only when something changed. If a source is down the run fails and the
last good tables stay published. After a wipe or patch you can force a refresh from the Actions tab:
**Update item and quest tables -> Run workflow**.

The script reads them from:

    https://raw.githubusercontent.com/<owner>/eft-v2-data/main/data/eft_items.txt
    https://raw.githubusercontent.com/<owner>/eft-v2-data/main/data/eft_quests.txt
