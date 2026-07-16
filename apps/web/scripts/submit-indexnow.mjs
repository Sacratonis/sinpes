import { readFile } from 'node:fs/promises';
import path from 'node:path';

const site = 'https://sinpes.com';
const key = '9a016cc587051b4a818487a5046cf90e';
const sitemapPath = path.resolve('dist/sitemap-0.xml');
const sitemap = await readFile(sitemapPath, 'utf8');
const urls = [...new Set(
  [...sitemap.matchAll(/<loc>(.*?)<\/loc>/g)]
    .map((match) => match[1].trim())
    .filter((url) => url.startsWith(`${site}/`))
)];

if (!urls.length) {
  throw new Error('IndexNow submission stopped: sitemap contains no SINPES URLs.');
}

const response = await fetch('https://api.indexnow.org/indexnow', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    host: 'sinpes.com',
    key,
    keyLocation: `${site}/${key}.txt`,
    urlList: urls.slice(0, 10000),
  }),
});

if (![200, 202].includes(response.status)) {
  throw new Error(`IndexNow submission failed with HTTP ${response.status}.`);
}

console.log(`IndexNow accepted ${urls.length} SINPES URL(s).`);
