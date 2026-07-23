import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

const distDir = path.resolve('dist');

async function htmlFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return htmlFiles(target);
    return entry.name.endsWith('.html') ? [target] : [];
  }));
  return nested.flat();
}

function capture(html, pattern) {
  return html.match(pattern)?.[1]?.trim() || '';
}

function sitemapPageLocations(xml) {
  return [...xml.matchAll(/<url>\s*<loc>(.*?)<\/loc>/gs)].map(match => match[1].trim());
}

function sitemapUrlRows(xml) {
  return [...xml.matchAll(/<url>(.*?)<\/url>/gs)].map((match) => {
    const block = match[1];
    return {
      loc: capture(block, /<loc>(.*?)<\/loc>/s),
      alternates: [...block.matchAll(
        /<xhtml:link rel="alternate" hreflang="([^"]+)" href="([^"]+)"\s*\/>/g
      )].map((alternate) => ({
        hreflang: alternate[1],
        href: alternate[2],
      })),
    };
  });
}

function hasSchemaType(item, type) {
  const schemaType = item?.['@type'];
  return schemaType === type || (Array.isArray(schemaType) && schemaType.includes(type));
}

const files = await htmlFiles(distDir);
const failures = [];
const blogArticleCanonicals = [];
const blogArticleHreflangs = new Map();

for (const file of files) {
  const html = await readFile(file, 'utf8');
  const relative = path.relative(distDir, file);
  const title = capture(html, /<title>(.*?)<\/title>/s);
  const description = capture(html, /<meta name="description" content="([^"]*)"/);
  const canonical = capture(html, /<link rel="canonical" href="([^"]*)"/);
  const robots = capture(html, /<meta name="robots" content="([^"]*)"/);
  const h1Count = (html.match(/<h1\b/g) || []).length;
  const hreflangs = [...html.matchAll(/<link rel="alternate" hreflang="[^"]+" href="([^"]+)"/g)].map(match => match[1]);
  const routeSegments = relative.split(path.sep);
  const is404 = relative === '404.html';
  const isTest = routeSegments.includes('test');
  const isFont = routeSegments.includes('font');
  const isCategory = routeSegments.includes('category');
  const isBlogIndex = /^(?:(?:es|pt)[/\\])?blog[/\\]index\.html$/.test(relative);
  const isBlogArticle = routeSegments.includes('blog') && !isBlogIndex;
  const isHome = relative === 'index.html' || /^(es|pt)[/\\]index\.html$/.test(relative);
  const requiresStructuredData = isHome || isFont || isCategory || isBlogArticle;
  if (isBlogArticle && canonical) {
    blogArticleCanonicals.push(canonical);
    blogArticleHreflangs.set(canonical, new Set(hreflangs));
  }

  if (!title) failures.push(`${relative}: missing title`);
  if (!description) failures.push(`${relative}: missing meta description`);
  if (!html.includes('<meta name="msvalidate.01" content="451E1BD0AE8253F7665FC14EBC0D57B6"')) {
    failures.push(`${relative}: missing Bing Webmaster verification`);
  }
  if (!html.includes('<meta name="yandex-verification" content="1e504b07f03d7f62"')) {
    failures.push(`${relative}: missing Yandex Webmaster verification`);
  }
  if (description.length > 160) failures.push(`${relative}: meta description is ${description.length} characters`);
  if (!canonical) failures.push(`${relative}: missing canonical URL`);
  if (!is404 && canonical && !canonical.endsWith('/')) failures.push(`${relative}: canonical URL must end with /`);
  if (hreflangs.some(url => !url.endsWith('/'))) failures.push(`${relative}: hreflang URLs must end with /`);
  if (h1Count !== 1) failures.push(`${relative}: expected one h1, found ${h1Count}`);
  if ((is404 || isTest) && !robots.includes('noindex')) failures.push(`${relative}: utility page must be noindex`);

  if (requiresStructuredData) {
    const jsonLd = capture(html, /<script type="application\/ld\+json">(.*?)<\/script>/s);
    if (!jsonLd) {
      failures.push(`${relative}: missing JSON-LD`);
    } else {
      try {
        const data = JSON.parse(jsonLd);
        const graph = Array.isArray(data?.['@graph']) ? data['@graph'] : [];
        if (isHome) {
          const requiredTypes = ['Organization', 'WebSite', 'SiteNavigationElement', 'CollectionPage', 'ItemList'];
          for (const type of requiredTypes) {
            if (!graph.some(item => item?.['@type'] === type)) {
              failures.push(`${relative}: homepage schema missing ${type}`);
            }
          }
          const navigation = graph.find(item => item?.['@type'] === 'SiteNavigationElement');
          if (!Array.isArray(navigation?.hasPart) || navigation.hasPart.length < 4) {
            failures.push(`${relative}: homepage SiteNavigationElement has too few navigation entries`);
          }
          const itemList = graph.find(item => item?.['@type'] === 'ItemList');
          if (!Array.isArray(itemList?.itemListElement)) {
            failures.push(`${relative}: homepage ItemList has no font entries`);
          }
        }
        if (isFont) {
          const webPage = graph.find(item => item?.['@type'] === 'WebPage');
          const imageObject = graph.find(item => item?.['@type'] === 'ImageObject');
          const hasHero = /<img\b[^>]*class="[^"]*"[^>]*>/s.test(html) || html.includes('class="hero-cinema"');
          if (!webPage) failures.push(`${relative}: font page missing WebPage schema`);
          if (hasHero && !imageObject) failures.push(`${relative}: font page missing ImageObject schema`);
          if (hasHero && !webPage?.primaryImageOfPage) failures.push(`${relative}: font page missing primaryImageOfPage`);
        }
        if (isBlogArticle) {
          const article = graph.find(item =>
            hasSchemaType(item, 'BlogPosting') || hasSchemaType(item, 'Article')
          );
          const webPage = graph.find(item => hasSchemaType(item, 'WebPage'));
          const breadcrumb = graph.find(item => hasSchemaType(item, 'BreadcrumbList'));
          const imageObject = graph.find(item => hasSchemaType(item, 'ImageObject'));
          const htmlLang = capture(html, /<html lang="([^"]+)"/);
          const ogType = capture(html, /<meta property="og:type" content="([^"]+)"/);
          const ogTitle = capture(html, /<meta property="og:title" content="([^"]*)"/);
          const ogDescription = capture(html, /<meta property="og:description" content="([^"]*)"/);
          const ogUrl = capture(html, /<meta property="og:url" content="([^"]*)"/);
          const publishedTime = capture(html, /<meta property="article:published_time" content="([^"]*)"/);
          const articleSection = capture(html, /<meta property="article:section" content="([^"]*)"/);
          const articleAuthor = capture(html, /<meta property="article:author" content="([^"]*)"/);
          const twitterTitle = capture(html, /<meta name="twitter:title" content="([^"]*)"/);
          const twitterDescription = capture(html, /<meta name="twitter:description" content="([^"]*)"/);
          const hasHero = html.includes('class="blog-hero"');

          if (!article) failures.push(`${relative}: blog article missing BlogPosting or Article schema`);
          if (!webPage) failures.push(`${relative}: blog article missing WebPage schema`);
          if (!breadcrumb) failures.push(`${relative}: blog article missing BreadcrumbList schema`);
          if (breadcrumb && (!Array.isArray(breadcrumb.itemListElement) || breadcrumb.itemListElement.length < 3)) {
            failures.push(`${relative}: blog article breadcrumb is incomplete`);
          }
          if (!article?.headline) failures.push(`${relative}: blog article schema missing headline`);
          if (!article?.description) failures.push(`${relative}: blog article schema missing description`);
          if (!article?.datePublished) failures.push(`${relative}: blog article schema missing datePublished`);
          if (!article?.dateModified) failures.push(`${relative}: blog article schema missing dateModified`);
          if (!article?.author) failures.push(`${relative}: blog article schema missing author`);
          if (!article?.publisher) failures.push(`${relative}: blog article schema missing publisher`);
          if (!article?.mainEntityOfPage) failures.push(`${relative}: blog article schema missing mainEntityOfPage`);
          if (article?.inLanguage !== htmlLang) {
            failures.push(`${relative}: blog article schema language does not match the page`);
          }
          if (ogType !== 'article') failures.push(`${relative}: blog article og:type must be article`);
          if (!ogTitle || !twitterTitle) failures.push(`${relative}: blog article missing social title`);
          if (!ogDescription || !twitterDescription) failures.push(`${relative}: blog article missing social description`);
          if (ogUrl !== canonical) failures.push(`${relative}: blog article og:url does not match canonical`);
          if (!publishedTime || publishedTime !== article?.datePublished) {
            failures.push(`${relative}: article published time does not match schema`);
          }
          if (!articleSection) failures.push(`${relative}: blog article missing article section metadata`);
          if (!articleAuthor) failures.push(`${relative}: blog article missing article author metadata`);
          if (hasHero) {
            const ogImage = capture(html, /<meta property="og:image" content="([^"]*)"/);
            const ogImageAlt = capture(html, /<meta property="og:image:alt" content="([^"]*)"/);
            const twitterImage = capture(html, /<meta name="twitter:image" content="([^"]*)"/);
            const twitterImageAlt = capture(html, /<meta name="twitter:image:alt" content="([^"]*)"/);
            if (!imageObject) failures.push(`${relative}: blog article hero missing ImageObject schema`);
            if (!article?.image) failures.push(`${relative}: blog article schema missing image reference`);
            if (!ogImage || !twitterImage) failures.push(`${relative}: blog article hero missing social image`);
            if (!ogImageAlt || !twitterImageAlt) failures.push(`${relative}: blog article hero missing social image alt text`);
          }
        }
      } catch {
        failures.push(`${relative}: invalid JSON-LD`);
      }
    }
  }
}

try {
  const key = '9a016cc587051b4a818487a5046cf90e';
  const keyBody = (await readFile(path.join(distDir, `${key}.txt`), 'utf8')).trim();
  if (keyBody !== key) failures.push('IndexNow key file does not match its filename');
} catch {
  failures.push('IndexNow verification key file is missing');
}

const imageSitemapPath = path.join(distDir, 'image-sitemap.xml');
let imagePageLocations = [];
try {
  const imageSitemap = await readFile(imageSitemapPath, 'utf8');
  const imageLocations = [...imageSitemap.matchAll(/<image:loc>(.*?)<\/image:loc>/g)].map(match => match[1]);
  imagePageLocations = sitemapPageLocations(imageSitemap);
  if (!imageSitemap.includes('xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"')) {
    failures.push('image-sitemap.xml: missing Google image namespace');
  }
  if (!imageLocations.length) failures.push('image-sitemap.xml: contains no images');
  if (imageLocations.some(url => !url.startsWith('https://'))) {
    failures.push('image-sitemap.xml: image URLs must use HTTPS');
  }
} catch {
  failures.push('image-sitemap.xml: missing generated image sitemap');
}

const sitemapRules = {
  'font-sitemap.xml': url => url.includes('/font/'),
  'category-sitemap.xml': url => url.includes('/category/'),
  'page-sitemap.xml': url => !url.includes('/font/') && !url.includes('/category/') && !url.includes('/blog/'),
  'blog-sitemap.xml': url => url.includes('/blog/'),
};
const expectedSitemaps = [...Object.keys(sitemapRules), 'image-sitemap.xml'];
const combinedPageLocations = [];
let fontPageLocations = [];
let blogSitemapRows = [];

try {
  const sitemapIndex = await readFile(path.join(distDir, 'sitemap-index.xml'), 'utf8');
  const indexedSitemaps = [...sitemapIndex.matchAll(/<sitemap>\s*<loc>(.*?)<\/loc>/gs)]
    .map(match => match[1].trim());
  for (const filename of expectedSitemaps) {
    if (!indexedSitemaps.includes(`https://sinpes.com/${filename}`)) {
      failures.push(`sitemap-index.xml: missing ${filename}`);
    }
  }
  if (indexedSitemaps.includes('https://sinpes.com/sitemap-0.xml')) {
    failures.push('sitemap-index.xml: compatibility sitemap must not be indexed');
  }
} catch {
  failures.push('sitemap-index.xml: missing generated sitemap index');
}

for (const [filename, matchesRoute] of Object.entries(sitemapRules)) {
  try {
    const xml = await readFile(path.join(distDir, filename), 'utf8');
    const locations = sitemapPageLocations(xml);
    if (!locations.length) failures.push(`${filename}: contains no page URLs`);
    if (locations.some(url => !url.startsWith('https://sinpes.com/'))) {
      failures.push(`${filename}: contains a non-canonical host`);
    }
    if (locations.some(url => !matchesRoute(url))) {
      failures.push(`${filename}: contains a URL from the wrong page type`);
    }
    if (xml.includes('<priority>') || xml.includes('<changefreq>')) {
      failures.push(`${filename}: contains ignored priority or changefreq values`);
    }
    if (filename === 'font-sitemap.xml') fontPageLocations = locations;
    if (filename === 'blog-sitemap.xml') blogSitemapRows = sitemapUrlRows(xml);
    combinedPageLocations.push(...locations);
  } catch {
    failures.push(`${filename}: missing generated sitemap`);
  }
}

if (new Set(combinedPageLocations).size !== combinedPageLocations.length) {
  failures.push('split sitemaps: duplicate page URLs found across sitemap types');
}
if (imagePageLocations.some(url => !fontPageLocations.includes(url))) {
  failures.push('image-sitemap.xml: contains a page absent from font-sitemap.xml');
}

const expectedBlogIndexes = [
  'https://sinpes.com/blog/',
  'https://sinpes.com/es/blog/',
  'https://sinpes.com/pt/blog/',
];
const blogLocations = blogSitemapRows.map(row => row.loc);
for (const indexUrl of expectedBlogIndexes) {
  if (!blogLocations.includes(indexUrl)) {
    failures.push(`blog-sitemap.xml: missing localized blog index ${indexUrl}`);
  }
}

const blogArticleRows = blogSitemapRows.filter(row => !expectedBlogIndexes.includes(row.loc));
const sitemapArticleLocations = blogArticleRows.map(row => row.loc).sort();
const generatedArticleLocations = [...blogArticleCanonicals].sort();
if (
  sitemapArticleLocations.length !== generatedArticleLocations.length ||
  generatedArticleLocations.some((url, index) => url !== sitemapArticleLocations[index])
) {
  failures.push('blog-sitemap.xml: article locales differ from generated complete article routes');
}

for (const row of blogArticleRows) {
  const localeAlternates = row.alternates.filter(alternate => alternate.hreflang !== 'x-default');
  const xDefault = row.alternates.find(alternate => alternate.hreflang === 'x-default');
  const alternateUrls = new Set(localeAlternates.map(alternate => alternate.href));
  if (!localeAlternates.length || !xDefault) {
    failures.push(`blog-sitemap.xml: ${row.loc} has incomplete hreflang annotations`);
    continue;
  }
  if ([...alternateUrls].some(url => !sitemapArticleLocations.includes(url))) {
    failures.push(`blog-sitemap.xml: ${row.loc} links to an article locale absent from the sitemap`);
  }
  if (!alternateUrls.has(row.loc)) {
    failures.push(`blog-sitemap.xml: ${row.loc} does not include a self-referencing alternate`);
  }
  const englishAlternate = localeAlternates.find(alternate => alternate.hreflang === 'en');
  const expectedDefault = englishAlternate?.href || localeAlternates[0].href;
  if (xDefault.href !== expectedDefault) {
    failures.push(`blog-sitemap.xml: ${row.loc} has the wrong x-default locale`);
  }
  const pageHreflangs = blogArticleHreflangs.get(row.loc) || new Set();
  const sitemapHreflangs = new Set(row.alternates.map(alternate => alternate.href));
  if (
    pageHreflangs.size !== sitemapHreflangs.size ||
    [...sitemapHreflangs].some(url => !pageHreflangs.has(url))
  ) {
    failures.push(`blog-sitemap.xml: ${row.loc} hreflangs differ from the article page`);
  }
}

try {
  const legacySitemap = await readFile(path.join(distDir, 'sitemap-0.xml'), 'utf8');
  const legacyLocations = sitemapPageLocations(legacySitemap);
  if (new Set(legacyLocations).size !== legacyLocations.length) {
    failures.push('sitemap-0.xml: contains duplicate page URLs');
  }
  if (
    legacyLocations.length !== combinedPageLocations.length ||
    combinedPageLocations.some(url => !legacyLocations.includes(url))
  ) {
    failures.push('sitemap-0.xml: compatibility URLs differ from split sitemaps');
  }
} catch {
  failures.push('sitemap-0.xml: missing compatibility sitemap');
}

try {
  const robots = await readFile(path.join(distDir, 'robots.txt'), 'utf8');
  if (!robots.includes('Sitemap: https://sinpes.com/sitemap-index.xml')) {
    failures.push('robots.txt: missing sitemap index declaration');
  }
  if (!robots.includes('Sitemap: https://sinpes.com/image-sitemap.xml')) {
    failures.push('robots.txt: missing image sitemap declaration');
  }
} catch {
  failures.push('robots.txt: missing');
}

if (failures.length) {
  console.error(`SEO audit failed with ${failures.length} issue(s):`);
  failures.forEach(failure => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`SEO audit passed for ${files.length} generated page(s).`);
