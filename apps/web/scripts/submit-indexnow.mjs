import { pathToFileURL } from 'node:url';

const site = 'https://sinpes.com';
const key = '9a016cc587051b4a818487a5046cf90e';

export const INDEXNOW_LIMITS = Object.freeze({
  maxDepth: 8,
  maxSitemaps: 1000,
  maxUrls: 100000,
  maxSitemapBytes: 10 * 1024 * 1024,
});

export function decodeXml(value) {
  return value
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&apos;', "'");
}

async function fetchXml(url, fetchImpl, maxSitemapBytes) {
  const response = await fetchImpl(url, {
    headers: { 'user-agent': 'SINPES-IndexNow/1.0' },
  });
  if (!response.ok) {
    throw new Error(`Could not fetch sitemap ${url} (${response.status}).`);
  }
  const xml = await response.text();
  if (Buffer.byteLength(xml, 'utf8') > maxSitemapBytes) {
    throw new Error(`Sitemap ${url} exceeds the ${maxSitemapBytes}-byte safety limit.`);
  }
  return xml;
}

export function pageUrls(xml) {
  return [...xml.matchAll(/<url>\s*<loc>(.*?)<\/loc>/gs)]
    .map((match) => decodeXml(match[1].trim()));
}

async function collectSitemapUrls(url, fetchImpl, siteUrl, options, state, depth = 0) {
  if (depth > options.maxDepth) {
    throw new Error(`Sitemap nesting exceeds the ${options.maxDepth}-level safety limit.`);
  }
  if (state.visited.has(url)) return [];
  if (state.visited.size >= options.maxSitemaps) {
    throw new Error(`Sitemap discovery exceeds the ${options.maxSitemaps}-file safety limit.`);
  }
  state.visited.add(url);
  const xml = await fetchXml(url, fetchImpl, options.maxSitemapBytes);
  if (!xml.includes('<sitemapindex')) return pageUrls(xml);

  const childSitemaps = [...xml.matchAll(/<sitemap>\s*<loc>(.*?)<\/loc>/gs)]
    .map((match) => decodeXml(match[1].trim()))
    .filter((childUrl) =>
      childUrl.startsWith(`${siteUrl}/`) && !childUrl.endsWith('/image-sitemap.xml')
    );
  const urls = [];
  for (const childUrl of childSitemaps) {
    urls.push(...await collectSitemapUrls(childUrl, fetchImpl, siteUrl, options, state, depth + 1));
    if (urls.length > options.maxUrls) {
      throw new Error(`Sitemap discovery exceeds the ${options.maxUrls}-URL safety limit.`);
    }
  }
  return urls;
}

export async function discoverIndexNowUrls(
  sitemapUrl,
  {
    fetchImpl = fetch,
    siteUrl = site,
    maxDepth = INDEXNOW_LIMITS.maxDepth,
    maxSitemaps = INDEXNOW_LIMITS.maxSitemaps,
    maxUrls = INDEXNOW_LIMITS.maxUrls,
    maxSitemapBytes = INDEXNOW_LIMITS.maxSitemapBytes,
  } = {}
) {
  const options = { maxDepth, maxSitemaps, maxUrls, maxSitemapBytes };
  if (!Number.isInteger(maxDepth) || maxDepth < 0) throw new TypeError('maxDepth must be a non-negative integer.');
  if (!Number.isInteger(maxSitemaps) || maxSitemaps < 1) throw new TypeError('maxSitemaps must be a positive integer.');
  if (!Number.isInteger(maxUrls) || maxUrls < 1) throw new TypeError('maxUrls must be a positive integer.');
  if (!Number.isInteger(maxSitemapBytes) || maxSitemapBytes < 1) throw new TypeError('maxSitemapBytes must be a positive integer.');
  const normalizedSite = siteUrl.replace(/\/$/, '');
  const discovered = await collectSitemapUrls(
    sitemapUrl,
    fetchImpl,
    normalizedSite,
    options,
    { visited: new Set() },
  );
  const urls = [...new Set(discovered.filter((url) => url.startsWith(`${normalizedSite}/`)))];
  if (urls.length > maxUrls) {
    throw new Error(`Sitemap discovery exceeds the ${maxUrls}-URL safety limit.`);
  }
  return urls;
}

async function main() {
  const sitemapUrl = process.env.INDEXNOW_SITEMAP_URL || `${site}/sitemap-index.xml`;
  const urls = await discoverIndexNowUrls(sitemapUrl);

  if (!urls.length) {
    throw new Error('IndexNow submission stopped: sitemap contains no SINPES URLs.');
  }

  for (let index = 0; index < urls.length; index += 10000) {
    const urlList = urls.slice(index, index + 10000);
    const response = await fetch('https://api.indexnow.org/indexnow', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        host: 'sinpes.com',
        key,
        keyLocation: `${site}/${key}.txt`,
        urlList,
      }),
    });

    if (![200, 202].includes(response.status)) {
      throw new Error(`IndexNow submission failed with HTTP ${response.status}.`);
    }
  }

  console.log(`IndexNow accepted ${urls.length} SINPES URL(s).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
