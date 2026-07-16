import type { APIRoute } from 'astro';
import { buildUrlSet, getSitemapCollections, xmlResponse } from '../lib/sitemap';

export const prerender = true;

// Temporary compatibility sitemap for the URL already submitted to Search Console.
// It is intentionally excluded from sitemap-index.xml to avoid duplicate reporting.
export const GET: APIRoute = async () => {
  const collections = await getSitemapCollections();
  return xmlResponse(buildUrlSet(collections.all));
};
