# SINPES Enterprise SEO Strategy

## Operating model

SINPES uses three separate Telegram bots with strict responsibilities:

- Font/Oracle bot: font ingestion, family grouping, publishing, and evidence collection.
- Writer bot: article drafting, validation, review, and approved publication.
- SEO Expert bot: read-only audits, measurement, alerts, and evidence-based recommendations.

Each bot uses an isolated Groq credential:

- Font/Oracle bot: `GROQ_ORACLE_API_KEY`.
- Writer bot: `GROQ_WRITER_API_KEY`.
- SEO Expert bot: `GROQ_SEO_API_KEY`.

Keys must never fall back to another bot's credential. Missing credentials fail clearly so usage and rate limits cannot leak across bots.

The SEO Expert bot must never publish, delete, redirect, rewrite, or deploy automatically. It sends findings and proposed actions to the owner for approval. Groq is used only to summarize verified data; deterministic checks run without AI.

## Phase 0 — SEO Expert bot foundation

- [x] Reserve a separate Telegram bot token locally.
- [x] Reserve a separate Groq API key locally.
- [x] Add isolated SEO bot configuration.
- [x] Add the owner's private Telegram chat ID locally.
- [x] Implement owner-only authorization.
- [x] Implement `/start`, `/seo_status`, `/seo_audit`, and `/seo_pages`.
- [x] Add a separate systemd service, disabled by configuration by default.
- [x] Confirm the current audit path does not mutate the database, R2, GitHub, or Cloudflare.
- [x] Enable only after read-only and authorization tests pass.

## Shared content-integrity foundation

- [x] Build one shared module for evidence-bound claims and keyword conflicts.
- [x] Make exact normalized target-keyword matches deterministic hard blocks.
- [x] Support exact canonical `intent_key` blocks once taxonomy IDs are assigned.
- [x] Keep fuzzy overlap at 70% or higher advisory-only.
- [x] Ignore generic words when calculating fuzzy overlap.
- [x] Recheck integrity during Writer queueing, approval, and scheduled publication.
- [x] Use the same conflict engine from the SEO bot's read-only audit path.
- [x] Add integration tests proving both real paths invoke the shared module.
- [x] Persist verified variable-font capability from the font's `fvar` table.
- [x] Keep font-claim scans inside the paragraph that contains the font link.
- [ ] Run the variable-font backfill against existing R2 WOFF2 files during deployment.

Planned commands:

- `/seo_status` — integrations, last audit, and data freshness.
- `/seo_audit` — full technical and on-page audit.
- `/seo_pages` — weak, missing, duplicate, or non-indexed pages.
- `/seo_images` — image crawlability, duplication, alt text, schema, and sitemap checks.
- `/seo_links` — broken links, orphan pages, and internal-link opportunities.
- `/seo_opportunities` — evidence-backed collection, comparison, alternative, and article ideas.
- `/seo_report` — current weekly report.

## Phase 1 — Measurement and technical foundation

- [ ] Connect Google Search Console data.
- [x] Connect Bing Webmaster data.
- [ ] Record page and image impressions, clicks, CTR, and average position.
- [x] Add images to the XML sitemap.
- [x] Add `primaryImageOfPage` and `ImageObject` where appropriate.
- [x] Verify R2/CDN image crawlability, robots rules, headers, and canonical URLs.
- [x] Extend the build-time SEO audit to image SEO.
- [x] Send one weekly Telegram report and urgent alerts only.

Automation: deterministic scheduled audit, stored historical snapshots, change detection, and one concise summary request only when useful.

## Phase 2A — Taxonomy structure

- [ ] Build a controlled taxonomy for categories, styles, use cases, moods, industries, and supported capabilities.
- [ ] Define stable canonical `intent_key` values and naming rules.
- [ ] Keep the structure internal until evidence and catalog thresholds are met.

## Phase 2B — Evidence-gated taxonomy expansion

- [ ] Derive candidates from verified font metadata only after ingestion has produced enough qualifying records.
- [ ] Map every indexable page to one primary intent.
- [x] Detect exact keyword cannibalization in the Writer before approval and publication.
- [ ] Add canonical intent checks as taxonomy IDs become available.
- [ ] Keep unsupported or empty filters non-indexable.

Automation: derive taxonomy candidates from verified font metadata, require explicit catalog and search-evidence thresholds, and send additions for approval. The taxonomy structure can be built early; indexable pages cannot be created until their data gates pass.

## Phase 3 — Use-case collection pages

- [ ] Create useful collections only when at least two qualifying fonts exist.
- [ ] Add unique introductions, selection criteria, font examples, and internal links.
- [ ] Reject thin combinations and near-duplicate pages.

Automation: Oracle evidence plus database eligibility rules create proposals; the owner approves before the Writer bot prepares content.

## Phase 4 — Comparison and alternative pages

- [ ] Create comparisons using measurable facts only.
- [ ] Create alternative pages only for demonstrated search demand.
- [ ] Prohibit invented superiority, origin, licensing, or design-characteristic claims.
- [ ] Clearly state selection methodology.

Automation: deterministic fact tables first, AI-assisted prose second, validation and owner approval last.

## Phase 5 — Article system

- [ ] Use Oracle evidence to propose specific design problems and decisions.
- [ ] Check duplicates and cannibalization against existing pages and recent drafts.
- [ ] Enforce the Writer bot's scope, HTML, font-claim, image, and review rules.
- [ ] Add approved contextual links to fonts, collections, and related articles.

Automation: evidence to eligibility to verified facts to draft to validation to Telegram approval to publication.

## Phase 6 — Typography tools

- [ ] Prioritize useful tools with real search intent.
- [ ] Consider font pairing, type-scale, line-height, character-count, and contrast tools.
- [ ] Give each tool explanatory content, examples, and relevant archive links.

Automation: monitor tool landing pages separately and propose improvements from real query data.

## Phase 7 — Original data and digital PR

- [ ] Require at least 90 days of reliable search data before proposing a study.
- [ ] Require a documented minimum sample and impression threshold for each study proposal.
- [ ] Publish periodic studies based on anonymized archive and search data.
- [ ] Document methodology and sample size.
- [ ] Create reusable charts and journalist-friendly summaries.
- [ ] Run selective outreach for genuinely useful studies and tools.

Automation: scheduled data snapshots and report preparation; all claims and outreach remain human-approved.

## Phase 8 — Continuous maintenance

- [ ] Detect broken links, redirect chains, orphan pages, duplicate metadata, and schema errors.
- [ ] Detect traffic, CTR, ranking, and indexing drops.
- [ ] Find pages that should be refreshed, consolidated, redirected, or removed from the index.
- [ ] Track recommendations through proposed, approved, completed, and measured states.

Automation: daily lightweight checks, weekly reporting, monthly opportunity review, and urgent alerts only for material failures.

## Safety and quality gates

- Use only verified database facts and real external evidence.
- Route Writer content and SEO recommendations through the shared content-integrity module.
- Never manufacture demand, metrics, reviews, links, or expertise.
- Never use hidden text, cloaking, doorway pages, PBNs, paid dofollow links, or mass thin pages.
- Never let the SEO bot publish, delete, redirect, deploy, or modify R2 automatically.
- Keep all new work local and deploy it once with the current font-ingestion and website updates.
