import type { APIRoute } from 'astro';
import { loadFontRegistry } from '../content/fonts/loader';
import {
  SITEMAP_LOCALES,
  escapeXml,
  formatLastmod,
  localeUrl,
  xmlResponse,
} from '../lib/sitemap';

export const prerender = true;

export const GET: APIRoute = async () => {
  const fonts = await loadFontRegistry();
  const entries = fonts.flatMap((font) => SITEMAP_LOCALES.flatMap((locale) => {
    const translation = font.translations?.[locale] || font.translations?.en;
    const imageUrl = translation?.seo_image_url?.trim();
    if (!imageUrl) return [];
    const pageUrl = localeUrl(locale, `/font/${font.slug}/`);
    const lastmod = formatLastmod(font.last_updated);
    return [
      `  <url>\n` +
      `    <loc>${escapeXml(pageUrl)}</loc>\n` +
      (lastmod ? `    <lastmod>${escapeXml(lastmod)}</lastmod>\n` : '') +
      `    <image:image><image:loc>${escapeXml(imageUrl)}</image:loc></image:image>\n` +
      `  </url>`,
    ];
  }));
  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ...entries,
    '</urlset>',
  ].join('\n');
  return xmlResponse(xml);
};
