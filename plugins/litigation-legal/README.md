# Litigation & Legal Research — Claude Code plugin

Grounded litigation and legal-research workflows that drive the legal MCP
servers available in this environment. Every legal proposition is tied to a
**verifiable primary source**, every quotation is checked against the opinion,
and every deliverable is labeled **research support — not legal advice**.

> ⚠️ This plugin assists with legal-research and litigation workflows. It does
> **not** provide legal advice and does not create an attorney–client
> relationship. All output must be reviewed by a qualified, licensed attorney
> before it is relied upon or filed.

## What's in it

### Slash commands
| Command | What it does |
|---------|--------------|
| `/case-research <issue> [jurisdiction] [posture]` | Research case law / statutes and return a memo with verified inline citations. |
| `/citation-check <file or text>` | Cite-check a brief/memo: verify each citation exists, quotes are verbatim, and authorities are still good law. |
| `/docket-watch <case, number, or party>` | Find a federal/state docket, brief it, and offer to set up new-activity alerts. |
| `/judge-profile <judge> [court] [motion]` | Build an analytics profile of a judge — tendencies, timing, notable rulings. |
| `/deadline-calc <event + date + court>` | Compute litigation deadlines from a triggering event. |

### Skills (auto-invoked methodology)
- **case-law-research** — grounded research with a source-preference order and a
  mandatory inline-citation output contract.
- **citation-verification** — extract → resolve → verify-verbatim → check-support
  → check-treatment, returned as a findings table.
- **litigation-tracking** — locate a docket, read filings, profile the judge, and
  set up alerts (with confirmation before any account-level action).

### Subagent
- **litigation-researcher** — deep multi-source research that fans out across the
  legal MCP servers, reads opinions, verifies quotes, and returns a
  self-contained memo with inline citations.

## MCP servers it uses

The plugin orchestrates whichever of these are connected; it does not bundle
them:

- **Descrybe Legal Engine** — structured U.S. primary law (case law, statutes,
  regulations); concept search, citation lookup, treatment, quote verification.
- **CourtListener** — case law (Opinions), federal dockets (RECAP/PACER),
  judges, oral arguments; citation analysis and docket/search alerts.
- **Trellis** — state-court rulings, motions, dockets, and judge analytics.
- **Courtroom5** — case intake, deadline calculation, next-step guidance.
- **Legal Data Hunter** — multi-jurisdictional / non-U.S. research.

If a needed server isn't connected, the workflows say so rather than guessing.

## Install (single-repo marketplace)

This repository doubles as a one-plugin marketplace
(`.claude-plugin/marketplace.json`):

```
/plugin marketplace add billtryhard/ubiquitous-octo-adventure
/plugin install litigation-legal@litigation-legal-marketplace
```

## Layout

```
plugins/litigation-legal/
├── .claude-plugin/plugin.json
├── README.md
├── commands/        # case-research, citation-check, docket-watch, judge-profile, deadline-calc
├── skills/          # case-law-research, citation-verification, litigation-tracking
└── agents/          # litigation-researcher
```

## Design principles

1. **No fabrication.** Never invent a case, citation, holding, or quote;
   anything unverifiable is labeled UNVERIFIED.
2. **Read before citing.** Holdings and pinpoint pages come from the opinion
   text, not headnotes or summaries.
3. **Verify quotes and treatment.** Quotations are confirmed verbatim;
   authorities are checked for reversal/overruling.
4. **Inline citations are mandatory** — in the sentence where the claim appears.
5. **Confirm outward-facing actions.** Docket/search alerts are created or
   deleted only after explicit confirmation.
6. **Research support, not legal advice** — stated on every deliverable.
