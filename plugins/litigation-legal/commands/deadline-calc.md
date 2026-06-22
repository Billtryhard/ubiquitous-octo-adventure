---
description: Calculate litigation deadlines from a triggering event using the Courtroom5 deadline tools.
argument-hint: <triggering event and date, court/jurisdiction, and rule set if known>
---

Calculate the litigation deadlines for:

**$ARGUMENTS**

1. Identify the triggering event, its date, the court/jurisdiction, and the
   applicable rule set. If any of these is missing and it changes the
   computation, ask one brief clarifying question first.
2. Use Courtroom5 `deadline_calculator` to compute the deadlines. For broader
   case-stage guidance, `case_intake_assessment` and `next_step_guidance` are
   also available.
3. Return a clear table: deadline → date → the rule or basis it derives from →
   any assumptions (e.g. service method, weekend/holiday rollovers, time-zone).

Make every assumption explicit. Computed deadlines depend on the inputs and the
selected rule set, and local rules / standing orders can change them — flag this
clearly. End with: *Verify against the governing rules and have a licensed
attorney confirm. Research support only — not legal advice.*
