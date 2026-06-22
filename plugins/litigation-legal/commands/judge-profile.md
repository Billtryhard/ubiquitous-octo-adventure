---
description: Build an analytics profile of a judge — ruling tendencies, timing, and notable rulings for a pending matter.
argument-hint: <judge name> [court] [motion type or issue]
---

**Required MCP servers:** Trellis (judge analytics) and/or CourtListener
(judges data). If neither is connected, say so and stop — do not estimate a
judge's tendencies from memory.

Build an analytics profile of the judge:

**$ARGUMENTS**

Use the **litigation-tracking** skill's judge-analytics workflow:

1. Resolve the judge with Trellis `search_judges` (and CourtListener Judges for
   biographical/appointment data). Confirm the right judge and court if there is
   any ambiguity.
2. Pull `get_judge_profile` and `get_judge_analytics`: ruling tendencies,
   grant/deny rates, and typical timelines — focused on the motion type or issue
   provided, if any.
3. Surface notable or representative rulings with links.

Present this as **descriptive analytics, not prediction**: it describes past
patterns and does not forecast how the judge will rule. Note sample-size or
coverage limits where the data is thin. End with: *Research support only — not
legal advice.*
