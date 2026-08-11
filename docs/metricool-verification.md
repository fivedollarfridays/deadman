# Metricool destination-verification spike

**Run:** 2026-08-11 (UTC) · **Task:** DM1.4 · **Status:** answered, acted on

## The question

Metricool reports that a post published. That report is a heartbeat: the
known incident behind this surface is a scheduled FWDAO roundtable post that
Metricool reported as published, never appeared on the platform, and nobody
noticed. So the probe cannot key on the scheduler. It has to read the
destination.

**Which raises the question this spike exists to answer, in week one rather
than week three: is the destination readable at all?** Three possible
answers — platform API, public permalink, or neither — and each implies a
different `Method`, so a different trust tier, so a different set of verdicts
the probe is honestly allowed to reach.

## Method

Live unauthenticated HTTP from the development machine, `curl`, real posts
against fabricated ones. The test that matters is not "does a permalink
return 200" — it is **does the response discriminate a post that exists from
one that does not**. A check that returns the same answer either way is not
a check.

Controls: a known-real, famous, public post per platform; a syntactically
valid but nonexistent id; `example.com` to prove the network path works.
User agents tried: Chrome, `facebookexternalhit/1.1`, `Googlebot/2.1` —
because platforms often serve Open Graph tags to crawlers while walling
browsers, and if that were true here it would be the way in.

## Findings

| Destination | Real post | Absent post | Discriminates? | Verdict |
|---|---|---|---|---|
| Instagram permalink | `200` | `200` | **No** | Opaque |
| Instagram oEmbed (no approved app) | `400` "Media Not Found" | `400` | **No** | Unavailable |
| Facebook permalink | `400` | `400` | **No** | Opaque |
| X permalink | `200` + post text | `404` | **Yes** | **Readable** |
| LinkedIn permalink | `200` (company page) | `404` (bogus activity) | Untested on a real activity URN | Candidate |

### Instagram is not readable, in either direction

`https://www.instagram.com/p/BwrHPjxlseb/` is a real, famous, public post.
`https://www.instagram.com/p/AAAAAAAAAAA/` does not exist. Both return
**HTTP 200**, ~605 KB, `<title>Instagram</title>`, no `og:` tags, and — the
decisive detail — both bodies contain:

```json
"polarisRouteConfig":{"pageID":"httpErrorPage"},"url":"\/p\/BwrHPjxlseb\/"
"polarisRouteConfig":{"pageID":"httpErrorPage"},"url":"\/p\/AAAAAAAAAAA\/"
```

Instagram serves an *error page* under a *200* for a real public post to an
unauthenticated client. The shortcode appearing in the body is the request
URL reflected back, not evidence the post exists. Identical under all three
user agents.

Both error directions are therefore live, and both are worse than useless:

- keying on status (`200` = present) reports **every missing post as
  published** — a false `HEALTHY`, which is precisely the silent failure this
  project exists to catch, mechanized;
- keying on the error marker (`httpErrorPage` = absent) reports **every
  published post as missing** — a false `FAULT`, which trains the operator
  to ignore the alarm.

`instagram_oembed` was the remaining hope and it is closed the same way: for
the *real* public post above, with no app token, it returns `400`
`OAuthException` code 24, `"Media Not Found"` — the same response a genuinely
absent post gets. The endpoint requires an approved Meta app (oEmbed Read),
and Meta approval is unavailable here. **An unapproved app cannot distinguish
present from absent either.** So the API answer is not "harder", it is "no".

### Facebook is not readable

Every shape tried — a real public page (`/Meta/`), a nonexistent page, a
bogus post permalink — returned `400` with `<title>Error</title>`.
Unauthenticated Facebook does not distinguish anything, including whether the
*page* exists.

### X is readable, with content confirmation

Three real posts returned `200`; three fabricated ids returned `404`. Stable
across two passes each, and 10 consecutive requests to one real post returned
`200` ten times with no rate limiting. Better than routing alone: the `200`
body carries the post itself —

```
og:description content="just setting up my twttr"
<title>jack on X: "just setting up my twttr" / X</title>
```

so the probe can confirm the artifact's *identity*, not merely that the
server recognized an id.

### LinkedIn is a candidate, not a finding

A real company page returned `200` and a fabricated activity URN returned
`404`, so the shape discriminates. But no *real* activity URN was tested, and
LinkedIn is known to wall datacenter traffic. That is an untested path, so it
is treated as unreadable until proven — see Follow-ups.

## Decision

**The chosen verification path is the public permalink fetch, expressed as
`Method.DESTINATION_PUBLIC`** — trust tier 3 of 5, above `ACTIVE_CANARY`,
`LOCAL_ARTIFACT` and `REPORTED`, below only `DESTINATION_API`. It is real
evidence from the destination, obtained without privileged access, and weaker
than an authenticated read because it depends on a platform's willingness to
answer anonymous requests. Every verdict this probe reaches on X will say
`destination_public` in the provenance table, and a reader can see from that
alone what the claim rests on.

`Method.DESTINATION_API` is **not** available for any Metricool destination
and the code must not pretend otherwise. Metricool's own API, if used, reports
only what Metricool believes — that is `Method.REPORTED`, tier 0, the
heartbeat this surface already learned not to trust.

**Verifiability is a property of the platform, so the probe is keyed by
platform** (`PLATFORM_VERIFICATION` in `src/deadman/probes/metricool.py`):

| Platform | Verification | Consequence |
|---|---|---|
| X / Twitter | `DESTINATION_PUBLIC` | can reach `HEALTHY` or `FAULT` |
| Instagram, Facebook, Threads | none | `UNOBSERVABLE`, always |
| anything unlisted | none | `UNOBSERVABLE` (fail closed) |

The consequence is deliberate and is the honest reading of the finding: **for
Instagram this surface is a permanent, declared blind spot.** Metricool can
report a hundred Instagram posts published and the probe reports
`UNOBSERVABLE` a hundred times, because the only thing it actually knows is
that a third party made a claim. It does not fetch the permalink at all —
there is nothing to learn from it. That blind spot appears on its own line in
every report via `blind_spots()`, which is the point: a declared blind spot
gets escalated to a human, whereas a fabricated `HEALTHY` gets filed and
forgotten. This is the same incident as before, and the second time it is at
least visible.

The one defense the code keeps against its own future: `PermalinkReader`
refuses to fetch an opaque platform even if a caller wires it up directly,
because on Instagram the mapping `200 → present` silently manufactures the
false `HEALTHY` described above.

## Follow-ups

1. **Prove or drop LinkedIn** — one fetch of a real FWDAO activity URN
   settles it. If it discriminates, add it to `PLATFORM_VERIFICATION`; the
   probe gains a second verifiable destination and the fail-closed default
   means nothing breaks in the meantime.
2. **Shift the FWDAO calendar toward verifiable destinations where the
   content allows.** A post whose delivery can be verified is worth more than
   one that cannot, and this changes the reachable evidence tier at no
   engineering cost.
3. **Revisit if Meta approval ever lands.** With an approved app,
   `/{ig-user-id}/media` upgrades Instagram to `DESTINATION_API`, tier 4 —
   the strongest tier available. That is the only path that closes the blind
   spot; nothing in the public surface will.
4. **Re-run this spike before the demo.** Every finding is a fact about
   someone else's server, and it can change without notice. The commands are
   in this document precisely so the re-run is cheap.
