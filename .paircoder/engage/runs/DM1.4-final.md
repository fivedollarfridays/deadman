DM1.4 is \`done\`. The strict AC gate passed on the first attempt, all 7 criteria checked with evidence.

## The spike answered the question, and the answer was no

I ran live unauthenticated \`curl\` against real posts versus fabricated ids, across three user agents. The test that matters isn't "does a permalink return 200" — it's **does the response discriminate a post that exists from one that doesn't**.

| Destination | Real post | Absent post | Verdict |
|---|---|---|---|
| Instagram permalink | \`200\` | \`200\` | Opaque |
| Instagram oEmbed (no approved app) | \`400\` "Media Not Found" | \`400\` | Unavailable |
| Facebook | \`400\` | \`400\` | Opaque |
| X | \`200\` + post text | \`404\` | **Readable** |

Instagram serves the *same* body for a real famous public post and a nonexistent shortcode — both carrying \`"pageID":"httpErrorPage"\`, no \`og:\` tags, identical under Chrome, \`facebookexternalhit\`, and Googlebot. The shortcode appearing in the body is just the request URL reflected back. \`instagram_oembed\` was the fallback and it's closed the same way: without an approved Meta app it returns "Media Not Found" for the *real* post too. So the API answer isn't "harder", it's no.

Both false directions were live, and both are worse than useless: keying on status reports every missing post as published (a false \`HEALTHY\` — this project's own failure mode, mechanized), and keying on the error marker reports every published post as missing.

## What that made the probe

\`Method.DESTINATION_PUBLIC\`, trust tier 3 of 5 — and it exists only for X, whose \`200\` carries the post text in \`og:description\`, so verification is content-level rather than just routing.

The honest consequence, which I took rather than engineered around: **Instagram posts yield \`UNOBSERVABLE\` forever.** Metricool can report a hundred published and the probe reports blindness a hundred times, because a third-party claim is genuinely all it knows. That blind spot gets its own line in every report via \`blind_spots()\` — strictly better than the fabricated pass that let the original FWDAO incident run unnoticed. The probe doesn't fetch those permalinks at all; there's nothing to learn from a response that can't vary.

Two things worth flagging:
- **\`PermalinkReader\` refuses to fetch an opaque platform** even if a future caller wires it up directly. On Instagram, \`200 → PRESENT\` manufactures the exact false pass this system exists to catch, so the guard lives at the fetch rather than depending on everyone remembering the finding.
- **A 10-minute propagation grace period**, because verifying a post published seconds ago manufactures a false \`FAULT\` — and an alarm that cries wolf gets ignored, which reopens the same hole.

20 tests, suite 39/39, both collaborators injected so nothing touches the network. My first draft tripped \`arch check --strict\` ("too many functions", 16 \> 15) — baseline was clean, so it was mine, and it drove a split at the real seam: \`destinations.py\` for platform knowledge (reusable by DM1.9's canary) and \`metricool.py\` for batch reasoning. \`ruff\` and \`arch check\` clean.

**One follow-up for you to weigh:** LinkedIn's permalink shape *did* discriminate (200 on a real company page, 404 on a bogus activity URN), but I never tested a real activity URN, so I recorded it as unreadable rather than claiming a tier I hadn't proven. One fetch of a real FWDAO activity URN settles it and would give the surface a second verifiable destination. The larger lever is shifting the FWDAO calendar toward verifiable destinations where the content allows — that changes the reachable evidence tier at no engineering cost.