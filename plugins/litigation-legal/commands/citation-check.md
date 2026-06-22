---
description: Cite-check a brief or memo — verify every citation exists, quotes are verbatim, and authorities are still good law.
argument-hint: <file path to the document, or paste the text>
---

Cite-check the document below (a file path or pasted text):

**$ARGUMENTS**

If a file path is given, read it first. Then use the **citation-verification**
skill:

1. Extract every citation and quotation (`extract_case_references` /
   `extract_citations`), keeping the sentence each one supports.
2. Resolve each citation to a real authority (`find_case_from_reference`).
3. Verify every quotation verbatim with the correct pinpoint page
   (`verify_quote` / read the source).
4. Confirm each authority actually supports its proposition.
5. Check treatment for reversals/overrulings (`check_case_status`).

Return a **findings table** (citation as written → resolved authority → quote →
cite → support → treatment → fix), leading with must-fix items (fabricated /
not-found authorities, misquotations, overruled cases). Flag anything you cannot
resolve as **UNVERIFIED** — never assume it is fine. End with the disclaimer
that a clean result is not a guarantee and an attorney should confirm before
filing.
