---
description: Research U.S. case law / statutes on an issue and return a memo with verified inline citations.
argument-hint: <legal issue, question, or fact pattern> [jurisdiction] [posture]
---

**Required MCP servers:** Descrybe Legal Engine and/or CourtListener (Trellis
for state law; Legal Data Hunter for non-U.S. / multi-jurisdictional). If none
of these is connected, say so and stop — do not answer case-law questions from
memory.

Research the following legal issue and produce a grounded research memo:

**$ARGUMENTS**

Use the **case-law-research** skill. In particular:

1. Frame the issue, jurisdiction, and posture. If the jurisdiction or posture is
   missing and it materially changes the answer, ask one brief clarifying
   question before doing extensive work.
2. Find authority starting with Descrybe `search_cases_by_concept` /
   `search_laws_and_rules`, then CourtListener and Trellis as needed. Prefer
   binding, in-jurisdiction, higher-court authority.
3. Read the opinions before citing them; confirm holdings and pinpoint pages.
4. Verify every quotation (`verify_quote` / read the passage) and check each key
   authority is still good law (`check_case_status` / `find_cases_that_cite`).
5. Synthesize: rule → authority → application → counter-authority and
   distinctions.

Deliver a memo with **inline citations on every legal proposition**, a short
Sources list, and the standard disclaimer: *Research support only — not legal
advice. Verify all authorities and have a licensed attorney review before
relying on this.*
