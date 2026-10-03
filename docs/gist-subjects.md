# Subjects in a Gist (readable + editable)

`SUBJECTS_JSON` as a secret is write-only: nobody can read it back, so keyword
configs go blind. Point the bot at a gist instead — you see and edit the JSON
in your browser; the bot reads it every scan and writes it back on add/edit/
delete. Set the `SUBJECTS_URL` secret to the raw file URL, e.g.
`https://gist.githubusercontent.com/AhmedTyson/<hash>/raw/subjects.json`.

## Bootstrap (2 min, in Telegram)

1. `📚 Subjects` → `📤 Show JSON` → bot sends current `subjects.json`.
2. `gist.github.com` → New gist → filename `subjects.json` → paste → Create
   (public gist = bot reads without extra auth).
3. Open the gist file → **Raw** → copy URL → repo Settings → Secrets →
   Actions → new secret `SUBJECTS_URL` = that URL.
4. Re-run workflow. Next add/edit/delete saves to the gist (message says
   `saved to gist`).

## Writes need `gist` scope on GH_PAT

Reads of a public gist need no token. Writes (`PATCH /gists/:id`) need the
`gist` scope (classic PAT) or Gists read/write (fine-grained). Without it the
bot answers with the exact fix instead of saving. `SUBJECTS_JSON` secret stays
as automatic fallback when `SUBJECTS_URL` is unset.
