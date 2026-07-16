import type { APIRoute } from 'astro';
import {
  SITE_URL,
  buildSitemapIndex,
  getSitemapCollections,
  xmlResponse,
} from '../lib/sitemap';

export const prerender = true;

export const GET: APIRoute = async () => {
  const collections = await getSitemapCollections();
  return xmlResponse(buildSitemapIndex([
    { loc: `${SITE_URL}/font-sitemap.xml`, lastmod: collections.lastmod.fonts },
    { loc: `${SITE_URL}/category-sitemap.xml`, lastmod: collections.lastmod.categories },
    { loc: `${SITE_URL}/page-sitemap.xml`, lastmod: collections.lastmod.pages },
    { loc: `${SITE_URL}/blog-sitemap.xml`, lastmod: collections.lastmod.blog },
    { loc: `${SITE_URL}/image-sitemap.xml`, lastmod: collections.lastmod.images },
  ]));
};
