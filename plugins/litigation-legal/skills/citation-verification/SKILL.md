---
name: citation-verification
description: >-
  Methodology for extracting, normalizing, and verifying legal citations and
  quotations in a brief, memo, opinion, or any document — confirming each cited
  authority exists, that quoted language actually appears in the source, and
  that the authority is still good law. Use when a user asks to cite-check,
  verify quotes, validate authorities, build a table of authorities, or flag
  overruled/misquoted cases.
---

# Citation & quote verification

Cite-checking is adversarial proofreading: assume nothing in the document is
correct until a primary source confirms it. The goal is to catch fabricated,
misquoted, mis-cited, or no-longer-good authorities **before** they reach a
court or client.

## Tools

- **Descrybe Legal Engine**: `extract_case_references` (pull citations from
  text), `find_case_from_reference` (resolve a citation/name to a case),
  `verify_quote` (confirm a quotation appears verbatim), `check_case_status`
  and `find_cases_that_cite` (treatment / still-good-law).
- **CourtListener**: `extract_citations` / `analyze_citations` (find and
  resolve citations in text), `read_document` / `search_document` (read the
  opinion and locate the quoted passage and pinpoint page).
- **Trellis**: for state-court orders and rulings not in the above.

## Workflow

1. **Extract.** Pull every citation and every quotation from the document
   (`extract_case_references` / `extract_citations`). Build a working list with
   the surrounding sentence so you know the proposition each cite supports.
2. **Resolve.** For each citation, confirm the authority exists and you have the
   right one (`find_case_from_reference`). Watch for wrong reporter, wrong year,
   wrong court, or a transposed cite.
3. **Verify quotations verbatim.** For every quoted passage, run `verify_quote`
   or read the source and locate the exact language. Confirm the **pinpoint
   page**. Flag paraphrases presented as direct quotes and any altered wording,
   ellipses, or bracket changes that shift meaning.
4. **Check the proposition.** Confirm the cited authority actually supports the
   sentence it is attached to — not just that the case exists. A real case cited
   for a holding it does not contain is still a bad cite.
5. **Check treatment.** Run `check_case_status` / `find_cases_that_cite` to
   catch reversed, overruled, vacated, superseded, or negatively-treated
   authority. Note depublished or non-citable opinions.
6. **Report.**

## Output: a findings table

For each citation, report: the citation as written → resolved authority →
**Quote** (verbatim ✓ / misquoted / paraphrased / not found) → **Cite**
(correct / wrong reporter-court-year / not found) → **Support** (supports the
proposition / does not) → **Treatment** (good law / questioned / overruled /
unknown) → recommended fix.

Lead with the **must-fix** items: fabricated or not-found authorities,
misquotations, and overruled cases. Then minor cite-form issues. If a citation
cannot be resolved in any available source, say so explicitly — flag it as
**UNVERIFIED**, never assume it is fine.

Close with: **"Verification reflects the sources searched; a clear result is
not a guarantee. Have a licensed attorney confirm before filing. Research
support only — not legal advice."**
