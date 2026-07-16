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

const files = await htmlFiles(distDir);
const failures = [];

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
  const isHome = relative === 'index.html' || /^(es|pt)[/\\]index\.html$/.test(relative);
  const requiresStructuredData = isHome || isFont || isCategory;

  if (!title) failures.push(`${relative}: missing title`);
  if (!description) failures.push(`${relative}: missing meta description`);
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
        if (isFont) {
          const graph = Array.isArray(data?.['@graph']) ? data['@graph'] : [];
          const webPage = graph.find(item => item?.['@type'] === 'WebPage');
          const imageObject = graph.find(item => item?.['@type'] === 'ImageObject');
          const hasHero = /<img\b[^>]*class="[^"]*"[^>]*>/s.test(html) || html.includes('class="hero-cinema"');
          if (!webPage) failures.push(`${relative}: font page missing WebPage schema`);
          if (hasHero && !imageObject) failures.push(`${relative}: font page missing ImageObject schema`);
          if (hasHero && !webPage?.primaryImageOfPage) failures.push(`${relative}: font page missing primaryImageOfPage`);
        }
      } catch {
        failures.push(`${relative}: invalid JSON-LD`);
      }
    }
  }
}

const imageSitemapPath = path.join(distDir, 'image-sitemap.xml');
try {
  const imageSitemap = await readFile(imageSitemapPath, 'utf8');
  const imageLocations = [...imageSitemap.matchAll(/<image:loc>(.*?)<\/image:loc>/g)].map(match => match[1]);
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

try {
  const robots = await readFile(path.join(distDir, 'robots.txt'), 'utf8');
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
