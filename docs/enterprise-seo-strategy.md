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
- [x] Submit the canonical sitemap index in Google Search Console.
- [x] Submit the page sitemap in Google Search Console.
- [x] Submit the image sitemap in Google Search Console.
- [x] Add Bing Webmaster verification to every public layout.
- [x] Implement IndexNow URL queueing and post-deployment submission locally.
- [x] Deploy IndexNow and verify the public key URL.
- [x] Run the one-time full-site IndexNow submission after deployment.
- [ ] Record page and image impressions, clicks, CTR, and average position.
- [x] Add images to the XML sitemap.
- [x] Add `primaryImageOfPage` and `ImageObject` where appropriate.
- [x] Add a reusable homepage `Schema.js` graph for EN, ES, and PT.
- [x] Verify R2/CDN image crawlability, robots rules, headers, and canonical URLs.
- [x] Extend the build-time SEO audit to image SEO.
- [x] Extend the build-time SEO audit to Bing verification, homepage schema, and IndexNow.
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

## Bulletproof execution checklist

This is the single working checklist. Items remain incomplete until they are
verified on the live site or in the relevant search engine, not merely written
in local code.

### A — Deployment and live verification

- [ ] Review the complete SEO diff before deployment.
- [ ] Back up the production database and current server files.
- [ ] Deploy the homepage schema and Bing IndexNow changes once.
- [ ] Confirm the API, Font/Oracle, Writer, Telethon, and SEO services restart.
- [ ] Confirm the homepage returns HTTP 200 in EN, ES, and PT.
- [ ] Validate homepage JSON-LD with Schema.org and Google Rich Results tools.
- [ ] Verify `Organization`, `WebSite`, `CollectionPage`, and `ItemList` entities.
- [ ] Confirm every homepage font URL in the schema is canonical and public.
- [x] Confirm the IndexNow key is publicly reachable at its exact root URL.
- [x] Run `npm run seo:indexnow` once against the live sitemap.
- [x] Confirm Bing accepts the full-site submission.
- [ ] Confirm later font and article deployments submit only queued changed URLs.
- [ ] Verify failed IndexNow submissions remain queued for retry.
- [ ] Record the deployment hash and rollback instructions.

### B — Google Search Console

- [x] Verify the `https://sinpes.com/` property.
- [x] Submit `sitemap-index.xml`.
- [x] Submit `sitemap-0.xml`.
- [x] Submit `image-sitemap.xml`.
- [x] Confirm 378 page URLs were discovered.
- [x] Confirm 342 image records were discovered.
- [ ] Wait for the Page Indexing report to finish processing.
- [ ] Audit every non-indexing reason before clicking **Validate fix**.
- [ ] Inspect the homepage URL.
- [ ] Inspect one representative font-family URL.
- [ ] Inspect one category URL.
- [ ] Inspect one Spanish font URL.
- [ ] Inspect one Portuguese font URL.
- [ ] Inspect one article after articles are published.
- [ ] Review canonical selection for all samples.
- [ ] Review crawl status and rendered HTML for all samples.
- [ ] Review Core Web Vitals.
- [ ] Review HTTPS status.
- [ ] Review manual actions and security issues.
- [ ] Review enhancement and structured-data reports.
- [ ] Record a 7-day baseline for clicks, impressions, CTR, and position.
- [ ] Record a 28-day baseline once sufficient data exists.

### C — Bing Webmaster and IndexNow

- [x] Add Bing Webmaster verification.
- [x] Connect the Bing query-statistics API to the Oracle.
- [x] Implement IndexNow key hosting.
- [x] Queue EN, ES, and PT URLs together.
- [x] Queue new font-family and category URLs.
- [x] Queue updated font-poster URLs.
- [x] Queue unpublished and erased font URLs.
- [x] Queue new article, blog-index, and homepage URLs.
- [x] Submit only after deployment confirmation.
- [x] Add deterministic IndexNow unit and deployment integration tests.
- [ ] Deploy and validate IndexNow against the live site.
- [ ] Add IndexNow status to `/seo_status`.
- [ ] Add last submission, pending URL count, and last error to `/seo_report`.
- [ ] Alert only after repeated submission failures.
- [ ] Compare Bing impressions and clicks before and after IndexNow.

### D — Competitor intelligence

- [x] Establish the baseline for dafontfree.io, dafont.com, and 1001fonts.com.
- [x] Record their visible taxonomy, page structure, description lengths, and filters.
- [x] Store reusable patterns in `docs/competitor-seo-patterns.md`.
- [ ] Add `/seo_competitors` to the read-only SEO bot.
- [ ] Store weekly competitor snapshots instead of replacing old results.
- [ ] Track estimated public inventory counts.
- [ ] Track newly exposed category and collection URLs.
- [ ] Track title, meta-description, and heading patterns.
- [ ] Track archive-card excerpt lengths.
- [ ] Track sampled font-description word counts.
- [ ] Track new filters, specimen tools, and internal-link modules.
- [ ] Track sitemap changes without copying their content.
- [ ] Produce a weekly “new pattern / unchanged / removed” report.
- [ ] Require human approval before adopting a competitor pattern.
- [ ] Measure adopted patterns against SINPES impressions, rankings, and clicks.

### E — Font-page content system

- [ ] Generate a dedicated 25–35 word archive-card excerpt.
- [ ] Keep the full verified font description at 160–220 words when data supports it.
- [ ] Identify the family and category in the opening.
- [ ] State real file, style, and weight counts.
- [ ] Describe practical use cases without unsupported anatomy claims.
- [ ] Include verified formats, variable capability, and character coverage.
- [ ] Add category and collection links.
- [ ] Add relevant editorial links.
- [ ] Add related-font recommendations using verified metadata.
- [ ] Add author or foundry only when verified source data exists.
- [ ] Add first-published and last-updated dates.
- [ ] Keep titles, descriptions, and excerpts unique across locales.
- [ ] Reject copied, spun, or near-duplicate competitor language.

### F — Archive growth

- [x] Automate font-only ingestion and metadata generation.
- [x] Group multi-file font families.
- [x] Publish localized EN, ES, and PT font pages.
- [ ] Reach 150 verified live font families.
- [ ] Reach 250 verified live font families.
- [ ] Reach 500 verified live font families.
- [ ] Keep queue, database, R2, sitemap, and live-page counts consistent.
- [ ] Detect family splits before publication.
- [ ] Detect duplicate files and duplicate poster images.
- [ ] Monitor failed, deferred, and blocked ingestion items.
- [ ] Verify every batch on the live website after deployment.

### G — Taxonomy and collection pages

- [ ] Finalize controlled dimensions for classification, size, weight, width,
  occasion, holiday, era, style, attitude, use case, and capability.
- [ ] Create a stable `intent_key` for every eligible landing page.
- [ ] Require at least four accurately matching fonts.
- [ ] Require real Google, Bing, Pinterest, or first-party evidence.
- [ ] Block exact intent cannibalization.
- [ ] Keep fuzzy similarity advisory-only.
- [ ] Add unique introductions and selection guidance.
- [ ] Add real specimens and useful filters.
- [ ] Add related collections and breadcrumbs.
- [ ] Add EN, ES, and PT versions only when genuinely translated.
- [ ] Keep empty and weak combinations non-indexable.

Initial style candidates:

- [ ] Sans serif
- [ ] Serif
- [ ] Slab serif
- [ ] Script
- [ ] Handwritten
- [ ] Display
- [ ] Decorative
- [ ] Brush
- [ ] Calligraphy
- [ ] Signature
- [ ] Monospaced
- [ ] Pixel
- [ ] Blackletter
- [ ] Gothic
- [ ] Retro
- [ ] Vintage
- [ ] Typewriter
- [ ] Graffiti
- [ ] Stencil
- [ ] Geometric
- [ ] Variable

Initial use-case candidates:

- [ ] UI design
- [ ] Web design
- [ ] Mobile applications
- [ ] Editorial design
- [ ] Branding
- [ ] Logos
- [ ] Posters
- [ ] Packaging
- [ ] Social media
- [ ] Wedding invitations
- [ ] Fashion branding
- [ ] Restaurants
- [ ] Magazines
- [ ] Portfolios
- [ ] Presentations

### H — Seasonal and trend pages

- [ ] Christmas fonts
- [ ] Halloween fonts
- [ ] Valentine fonts
- [ ] Wedding fonts
- [ ] Summer fonts
- [ ] Back-to-school fonts
- [ ] Black Friday fonts
- [ ] New Year fonts
- [ ] Activate seasonal promotion 8–12 weeks before demand peaks.
- [ ] Keep stable URLs and refresh content rather than creating yearly duplicates.
- [ ] Update `lastmod` only after a material change.
- [ ] Remove seasonal prominence after the event without deleting the useful page.

### I — Comparison and alternatives

- [ ] Free alternatives to Gotham.
- [ ] Free alternatives to Helvetica.
- [ ] Free alternatives to Proxima Nova.
- [ ] Free alternatives to Avenir.
- [ ] Free alternatives to Futura.
- [ ] Free alternatives to popular editorial fonts.
- [ ] Free alternatives to popular UI fonts.
- [ ] Define measurable comparison criteria.
- [ ] Use only fonts that SINPES actually hosts.
- [ ] Add clear trademark and independence disclosures.
- [ ] Never distribute counterfeit or unauthorized commercial assets.

### J — Article and internal-link system

- [ ] Publish two or three approved articles weekly.
- [ ] Require Oracle evidence or a documented first-party need.
- [ ] Add font, collection, and related-article links naturally.
- [ ] Link font pages back to relevant articles.
- [ ] Link collection pages to included fonts and related collections.
- [ ] Detect orphan pages daily.
- [ ] Detect broken internal links before deployment.
- [ ] Avoid repetitive exact-match anchor text.
- [ ] Refresh declining articles using real query data.
- [ ] Consolidate genuine cannibalization rather than creating another page.

### K — Image SEO

- [x] Generate a separate image sitemap.
- [x] Add `primaryImageOfPage` and `ImageObject`.
- [x] Use descriptive localized alt text.
- [x] Remove generated font names from hero images.
- [x] Reject numbers, faces, watermarks, and unwanted generated text.
- [x] Detect cross-family duplicate hero URLs.
- [ ] Verify the R2 image host as a Search Console property.
- [ ] Confirm hero images use normal crawlable `<img>` elements.
- [ ] Add responsive `srcset` and `sizes` where useful.
- [ ] Audit descriptive filenames.
- [ ] Monitor Google image indexing and image impressions.
- [ ] Regenerate visually weak or duplicated posters.

### L — Reporting and success criteria

Daily:

- [ ] Indexability and HTTP-status checks.
- [ ] Broken-link and schema validation.
- [ ] Sitemap consistency.
- [ ] Missing metadata and duplicate-image detection.

Weekly:

- [ ] Google and Bing query review.
- [ ] Queries ranking in positions 4–20.
- [ ] Low-CTR pages with meaningful impressions.
- [ ] New collection eligibility.
- [ ] Competitor-pattern changes.
- [ ] Orphan-page and content-decay report.

Monthly:

- [ ] Indexed-page and indexed-image growth.
- [ ] EN, ES, and PT performance.
- [ ] Font, collection, and article performance.
- [ ] Internal-link coverage.
- [ ] Core Web Vitals.
- [ ] Earned-link and brand-mention growth.
- [ ] Accepted, rejected, and measured SEO recommendations.

Primary success metrics:

- [ ] More valid indexed font pages.
- [ ] More non-branded impressions.
- [ ] More queries in the top 20 and top 10.
- [ ] Higher CTR on pages with stable rankings.
- [ ] More image impressions and clicks.
- [ ] More font downloads from organic sessions.
- [ ] No manual actions, doorway-page growth, or scaled-content quality failures.

### M — Sitemap architecture

- [x] Split fonts, categories, editorial content, static pages, and images into
  separate generated sitemap files locally.
- [x] Keep `sitemap-index.xml` as the canonical discovery entry point.
- [x] Keep EN, ES, PT, and `x-default` alternate annotations.
- [x] Use real font and article dates for `lastmod`.
- [x] Exclude ignored `priority` and `changefreq` values.
- [x] Keep `sitemap-0.xml` temporarily as a compatibility URL.
- [x] Make the one-time IndexNow script read the sitemap index recursively.
- [x] Add build checks for sitemap type separation, duplicates, canonical host,
  image-page consistency, and legacy compatibility.
- [ ] Deploy the split sitemap architecture.
- [ ] Confirm all five child sitemaps return HTTP 200.
- [ ] Confirm production counts match fonts, categories, articles, pages, and images.
- [ ] Confirm Search Console reads every child sitemap successfully.
- [ ] Remove the old direct `sitemap-0.xml` Search Console submission after the
  split sitemaps are accepted.
- [ ] Remove the compatibility sitemap in a later deployment after crawler logs
  show that no search engine still requests it.
- [ ] Track indexed and excluded counts by sitemap type each week.

## Safety and quality gates

- Use only verified database facts and real external evidence.
- Route Writer content and SEO recommendations through the shared content-integrity module.
- Never manufacture demand, metrics, reviews, links, or expertise.
- Never use hidden text, cloaking, doorway pages, PBNs, paid dofollow links, or mass thin pages.
- Never let the SEO bot publish, delete, redirect, deploy, or modify R2 automatically.
- Keep all new work local and deploy it once with the current font-ingestion and website updates.
