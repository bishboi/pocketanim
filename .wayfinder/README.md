# Wayfinder tracker (local markdown)

No issue tracker was configured for this repo, so maps and tickets live here as
files. One map per effort, its tickets as children.

    .wayfinder/
      map-<slug>.md        the map: destination, notes, decisions, fog
      tickets/<n>-<slug>.md  one ticket, a child of a map

Every file carries frontmatter. The fields are the tracker:

| Field | Meaning |
|---|---|
| `id` | identity, unique across maps and tickets |
| `title` | **the name** — refer to a ticket by this, never by its id |
| `labels` | `wayfinder:map`, or the ticket's type: `research`, `prototype`, `grilling`, `task` |
| `parent` | the map this ticket belongs to |
| `blocked_by` | ids that must close first; the native dependency edge |
| `assignee` | the claim. An open, unassigned ticket is unclaimed |
| `state` | `open` or `closed` |

A ticket is **unblocked** when every id in `blocked_by` is closed. The
**frontier** is the open, unblocked, unclaimed tickets — what a session may take.

    python3 .wayfinder/frontier.py            # the frontier
    python3 .wayfinder/frontier.py --all      # every ticket and its state

A resolution is a `## Resolution` section appended to the ticket, plus `state:
closed`, plus a one-line gist added to the map's Decisions-so-far.
