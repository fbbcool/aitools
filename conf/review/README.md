# Review lists — cheatsheet (`aitools.review_imgs.v1`)

Throwaway image review lists: an agent posts a list of images plus a small
form, the operator answers it in the aidb app's **Review** tab, the agent
reads the answers back. Board task 102.

- Storage: collection `review_imgs` in the aidb DB of the chosen profile
  (`scenes_test` / `scenes_prod`), one document per list.
- Schema: [`conf/review/_schema.json`](_schema.json). Code: `src/aidb/review_imgs.py`
  (manager + validation), `src/aidb/app/tab_review.py` (tab), `script/review_list.py` (CLI).
- Lazy and throwaway: image refs are the paths as they are at creation time.
  There is no status, versioning or archival. Delete the list once its
  feedback is processed.
- Side-effect free: reviewing never writes to `images` / `scenes` / `sets`.

## 1. Write the list JSON

```json
{
  "schema_id": "aitools.review_imgs.v1",
  "list_id": "gtsv4-pilot-nearmiss",
  "title": "gts-v4 pilot near-misses: accept?",
  "created_by": "1xlasm-datasetter",
  "show_context": false,
  "form": [
    {"key": "accept", "type": "choice", "label": "Gate", "options": ["accept", "reject", "unsure"]},
    {"key": "why",    "type": "multi",  "label": "Reason", "options": ["head", "ratio", "text", "other"]},
    {"key": "ok_face","type": "bool",   "label": "Face ok?"},
    {"key": "note",   "type": "text",   "label": "Comment"}
  ],
  "items": [
    {"id": "p09", "url": "/home/misw/Data/AI/scenes_prod/enhancer-001/x.png", "context": "head 1 · ratio 0"},
    {"id": "p10", "url": "/abs/path/other.png"}
  ]
}
```

| field | rules |
|---|---|
| `list_id` | unique, `[A-Za-z0-9][A-Za-z0-9._-]*` (max 128) |
| `title`, `form`, `items` | required, `form` and `items` must be non-empty |
| `created` | optional, filled with local time `YYYY-MM-DDTHH:MM` when absent |
| `created_by` | optional, your board username |
| `show_context` | default `false`. When `false`, `items[].context` is not even sent to the browser (blind calibration) |
| `form[].key` | unique identifier (`[A-Za-z_][A-Za-z0-9_]*`) |
| `form[].type` | `bool` · `choice` · `multi` · `text`. `choice`/`multi` need `options` |
| `items[].id` | unique within the list |
| `items[].url` | local absolute file path. Missing, unreadable or non-image files show as a placeholder |
| `response`, `comment` | leave out (default `null`). The app writes them |

## 2. CLI

Set up the environment first (`PYTHONPATH=src`, `CONF_AIT`, see CLAUDE.md), e.g. `source activate.fish`.
`--config` defaults to `$AIDB_SCENE_CONFIG`.

```sh
python script/review_list.py validate list.json                 # schema check, no DB
python script/review_list.py --config prod create list.json     # validate + insert
python script/review_list.py --config prod create list.json --replace   # overwrite same list_id
python script/review_list.py --config prod ls                   # list_id  answered/total  created  by  title
python script/review_list.py --config prod get <list_id>        # full doc incl. responses, JSON on stdout
python script/review_list.py --config prod delete <list_id>
```

`create` also accepts `-` (stdin). Exit code 1 on invalid input or an unknown list.
Python API: `from aidb.review_imgs import ReviewImgs; ReviewImgs(config='prod').get(list_id)`.

## 3. Read the answers

`get` returns the document with each item's `response` filled in:

```json
{"id": "p09", "url": "...", "context": "...",
 "response": {"accept": "reject", "why": ["head", "ratio"], "ok_face": false, "note": "chin"}}
```

- The value types are: bool → `true`/`false`, choice → string, multi → list of
  strings (in `options` order), text → string. A key that has been cleared is
  `null`. A key that was never touched is missing.
- `response: null` means the item was never touched. An item counts as
  *answered* when any key holds a non-empty value.
- The list-level `comment` is a string or `null`.
- Quick extraction:
  `review_list.py get L | jq -r '.items[] | [.id, .response.accept // "-"] | @tsv'`

## 4. Operator side (Review tab, app on :7861)

- The dropdown lists every list, newest first, as `title [list_id] answered/total`. `↻ lists` refreshes it.
- Clicking an image opens a fullscreen modal with the item's form next to
  it. Answers given there are saved the same way as in the grid.
- Keys: `1`–`9` pick an option of the first `choice` field (or `bool`:
  1 = yes, 2 = no) · `0` clears it · `←`/`→` or `j`/`k` move to the previous/next item
  (`↑`/`↓` also work in the modal) · `Enter`/`Space` opens the modal · `Esc` closes it.
  With *auto-advance* on, a number key also moves to the next item.
- *unanswered only* hides items that already have an answer.
- Every answer is saved per item right away (debounced, acknowledged by
  the server, re-sent if lost). *reload list* re-reads the list from the DB.
