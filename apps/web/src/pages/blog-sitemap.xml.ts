import type { APIRoute } from 'astro';
import { buildUrlSet, getSitemapCollections, xmlResponse } from '../lib/sitemap';

export const prerender = true;

export const GET: APIRoute = async () => {
  const collections = await getSitemapCollections();
  return xmlResponse(buildUrlSet(collections.blog));
};
