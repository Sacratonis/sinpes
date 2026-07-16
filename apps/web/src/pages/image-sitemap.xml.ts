import type { APIRoute } from 'astro';
import { loadFontRegistry } from '../content/fonts/loader';

export const prerender = true;

const site = 'https://sinpes.com';
const locales = ['en', 'es', 'pt'] as const;

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export const GET: APIRoute = async () => {
  const fonts = await loadFontRegistry();
  const entries = fonts.flatMap((font) => locales.flatMap((locale) => {
    const translation = font.translations?.[locale] || font.translations?.en;
    const imageUrl = translation?.seo_image_url?.trim();
    if (!imageUrl) return [];
    const localePrefix = locale === 'en' ? '' : `/${locale}`;
    const pageUrl = `${site}${localePrefix}/font/${font.slug}/`;
    return [
      `  <url>\n` +
      `    <loc>${escapeXml(pageUrl)}</loc>\n` +
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
  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
