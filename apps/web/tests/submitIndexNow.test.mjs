import assert from 'node:assert/strict';
import test from 'node:test';
import {
  discoverIndexNowUrls,
  pageUrls,
} from '../scripts/submit-indexnow.mjs';

const site = 'https://sinpes.com';

function response(body, status = 200) {
  return new Response(body, {
    status,
    headers: { 'content-type': 'application/xml' },
  });
}

test('reads split sitemap indexes, skips the image sitemap, and removes duplicates', async () => {
  const fixtures = new Map([
    [`${site}/sitemap-index.xml`, response(`
      <sitemapindex>
        <sitemap><loc>${site}/font-sitemap.xml</loc></sitemap>
        <sitemap><loc>${site}/page-sitemap.xml</loc></sitemap>
        <sitemap><loc>${site}/image-sitemap.xml</loc></sitemap>
        <sitemap><loc>https://example.com/external.xml</loc></sitemap>
      </sitemapindex>
    `)],
    [`${site}/font-sitemap.xml`, response(`
      <urlset>
        <url><loc>${site}/font/inter/</loc></url>
        <url><loc>${site}/font/space&amp;time/</loc></url>
      </urlset>
    `)],
    [`${site}/page-sitemap.xml`, response(`
      <urlset>
        <url><loc>${site}/</loc></url>
        <url><loc>${site}/font/inter/</loc></url>
      </urlset>
    `)],
  ]);
  const requested = [];
  const fetchImpl = async (url) => {
    requested.push(url);
    return fixtures.get(url) || response('', 404);
  };

  const urls = await discoverIndexNowUrls(`${site}/sitemap-index.xml`, {
    fetchImpl,
    siteUrl: site,
  });

  assert.deepEqual(urls, [
    `${site}/font/inter/`,
    `${site}/font/space&time/`,
    `${site}/`,
  ]);
  assert.equal(requested.includes(`${site}/image-sitemap.xml`), false);
  assert.equal(requested.includes('https://example.com/external.xml'), false);
});

test('reads a direct legacy urlset', async () => {
  const xml = `
    <urlset>
      <url><loc>${site}/font/inter/</loc></url>
      <url><loc>${site}/es/font/inter/</loc></url>
    </urlset>
  `;

  assert.deepEqual(pageUrls(xml), [
    `${site}/font/inter/`,
    `${site}/es/font/inter/`,
  ]);
});

test('stops sitemap cycles without refetching the same document', async () => {
  const fixtures = new Map([
    [`${site}/root.xml`, response(`<sitemapindex><sitemap><loc>${site}/child.xml</loc></sitemap></sitemapindex>`)],
    [`${site}/child.xml`, response(`<sitemapindex><sitemap><loc>${site}/root.xml</loc></sitemap></sitemapindex>`)],
  ]);
  const requested = [];
  const fetchImpl = async (url) => {
    requested.push(url);
    return fixtures.get(url) || response('', 404);
  };

  assert.deepEqual(await discoverIndexNowUrls(`${site}/root.xml`, { fetchImpl }), []);
  assert.deepEqual(requested, [`${site}/root.xml`, `${site}/child.xml`]);
});

test('rejects sitemap nesting beyond the configured bound', async () => {
  const fixtures = new Map([
    [`${site}/root.xml`, response(`<sitemapindex><sitemap><loc>${site}/child.xml</loc></sitemap></sitemapindex>`)],
    [`${site}/child.xml`, response(`<sitemapindex><sitemap><loc>${site}/leaf.xml</loc></sitemap></sitemapindex>`)],
    [`${site}/leaf.xml`, response(`<urlset><url><loc>${site}/font/example/</loc></url></urlset>`)],
  ]);
  const fetchImpl = async (url) => fixtures.get(url) || response('', 404);

  await assert.rejects(
    discoverIndexNowUrls(`${site}/root.xml`, { fetchImpl, maxDepth: 1 }),
    /nesting exceeds the 1-level safety limit/,
  );
});

test('rejects an oversized URL set before submission', async () => {
  const xml = `<urlset><url><loc>${site}/a/</loc></url><url><loc>${site}/b/</loc></url></urlset>`;
  const fetchImpl = async () => response(xml);
  await assert.rejects(
    discoverIndexNowUrls(`${site}/root.xml`, { fetchImpl, maxUrls: 1 }),
    /discovery exceeds the 1-URL safety limit/,
  );
});
