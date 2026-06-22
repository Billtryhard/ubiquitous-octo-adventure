---
name: litigation-tracking
description: >-
  Methodology for finding and monitoring litigation — locating a federal or
  state docket, reading filings and parties, profiling the assigned judge, and
  setting up alerts for new activity. Use when a user wants to track a case,
  watch a docket, find recent filings, monitor a party or law firm, or build a
  judge profile for a pending matter.
---

# Litigation tracking & docket monitoring

Find the matter, read what is on file, understand who is in front of you, and
set up monitoring so new activity surfaces automatically.

## Tools

**Federal (PACER/RECAP) — CourtListener**
- `search` over RECAP for dockets by case name, party, or docket number; then
  `get_endpoint_schema` + `call_endpoint` for full docket / party / attorney
  detail (use `fields` to keep responses small).
- `read_document` / `search_document` to read individual filings.
- `subscribe_to_docket_alert` / `unsubscribe_from_docket_alert` for new-filing
  alerts on a docket; `create_search_alert` / `delete_search_alert` for
  standing searches (a party name, a doctrine, an attorney).

**State courts — Trellis** (call `get_server_instructions` first)
- `search_cases` / `get_case` / `get_case_complaints` / `get_document` /
  `get_ruling` for state dockets and filings.
- `research_motions`, `research_rulings_orders`, `research_law_firm` for
  patterns by motion type, ruling, or firm.

**Judge analytics — Trellis / CourtListener**
- Trellis `search_judges` → `get_judge_profile` / `get_judge_analytics` for
  ruling tendencies, grant/deny rates, and timing.
- CourtListener Judges search + endpoints for biographical and appointment data.

## Workflow

1. **Locate the matter.** Resolve to a specific docket from whatever the user
   has (case name, number, party, court). If several plausibly match, list the
   top candidates with court, filing date, and parties and confirm which one.
2. **Map the docket.** Summarize parties, counsel, cause(s) of action, posture,
   and the assigned judge. Pull the operative complaint and the most recent
   substantive filings.
3. **Read what matters.** Open key filings (complaint, dispositive motions,
   recent orders) rather than summarizing from the docket text alone.
4. **Profile the judge** when there is a live motion or strategy question:
   tendencies on the relevant motion type, typical timelines, and notable
   rulings — clearly labeled as descriptive analytics, not prediction.
5. **Set up monitoring.** Offer to subscribe to docket alerts and/or standing
   search alerts. State exactly what will trigger a notification and how to
   unsubscribe. **Confirm before creating or deleting any alert** — these are
   account-level, outward-facing actions.

## Output

A docket brief: caption and court · parties and counsel · claims and posture ·
assigned judge (with analytics if requested) · recent/key filings (with links)
· monitoring set up or proposed. Note any access limits (sealed entries, PACER
paywalls, coverage gaps) explicitly.

Close with: **"Docket data may lag the court record and can be incomplete.
Confirm against the official docket. Research support only — not legal advice."**
