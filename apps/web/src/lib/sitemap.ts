import { loadFontRegistry, type FontEntry } from '../content/fonts/loader';
import { blogPosts, type BlogPost } from '../data/blog';
import { categorySlug } from '../utils/taxonomy';
import { completeBlogLocales } from './blogLocale.mjs';

export const SITE_URL = 'https://sinpes.com';
export const SITEMAP_LOCALES = ['en', 'es', 'pt'] as const;

export interface SitemapAlternate {
  hreflang: string;
  href: string;
}

export interface SitemapEntry {
  loc: string;
  lastmod?: string;
  alternates?: SitemapAlternate[];
}

export interface SitemapCollections {
  fonts: SitemapEntry[];
  categories: SitemapEntry[];
  pages: SitemapEntry[];
  blog: SitemapEntry[];
  all: SitemapEntry[];
  lastmod: {
    fonts?: string;
    categories?: string;
    pages?: string;
    blog?: string;
    images?: string;
  };
}

let collectionsPromise: Promise<SitemapCollections> | undefined;

export function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export function formatLastmod(value?: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export function latestLastmod(values: Array<string | undefined>): string | undefined {
  const dates = values
    .map(formatLastmod)
    .filter((value): value is string => Boolean(value))
    .sort();
  return dates.at(-1);
}

export function localeUrl(locale: typeof SITEMAP_LOCALES[number], path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return locale === 'en'
    ? `${SITE_URL}${normalizedPath}`
    : `${SITE_URL}/${locale}${normalizedPath}`;
}

export function localizedEntries(
  path: string,
  lastmod?: string,
  locales: readonly typeof SITEMAP_LOCALES[number][] = SITEMAP_LOCALES
): SitemapEntry[] {
  if (!locales.length) return [];
  const xDefaultLocale = locales.includes('en') ? 'en' : locales[0];
  const alternates: SitemapAlternate[] = [
    ...locales.map((locale) => ({
      hreflang: locale,
      href: localeUrl(locale, path),
    })),
    { hreflang: 'x-default', href: localeUrl(xDefaultLocale, path) },
  ];

  return locales.map((locale) => ({
    loc: localeUrl(locale, path),
    lastmod: formatLastmod(lastmod),
    alternates,
  }));
}

export function buildUrlSet(entries: SitemapEntry[]): string {
  const rows = entries.map((entry) => {
    const alternates = (entry.alternates || [])
      .map((alternate) =>
        `    <xhtml:link rel="alternate" hreflang="${escapeXml(alternate.hreflang)}" href="${escapeXml(alternate.href)}" />`
      )
      .join('\n');
    return [
      '  <url>',
      `    <loc>${escapeXml(entry.loc)}</loc>`,
      entry.lastmod ? `    <lastmod>${escapeXml(entry.lastmod)}</lastmod>` : '',
      alternates,
      '  </url>',
    ].filter(Boolean).join('\n');
  });

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ...rows,
    '</urlset>',
  ].join('\n');
}

export function buildSitemapIndex(
  sitemaps: Array<{ loc: string; lastmod?: string }>
): string {
  const rows = sitemaps.map((sitemap) => [
    '  <sitemap>',
    `    <loc>${escapeXml(sitemap.loc)}</loc>`,
    sitemap.lastmod ? `    <lastmod>${escapeXml(sitemap.lastmod)}</lastmod>` : '',
    '  </sitemap>',
  ].filter(Boolean).join('\n'));

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...rows,
    '</sitemapindex>',
  ].join('\n');
}

export function xmlResponse(xml: string): Response {
  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=0, must-revalidate',
    },
  });
}

function fontEntries(fonts: FontEntry[]): SitemapEntry[] {
  return fonts.flatMap((font) =>
    localizedEntries(`/font/${font.slug}/`, font.last_updated)
  );
}

function categoryEntries(fonts: FontEntry[]): SitemapEntry[] {
  const categoryDates = new Map<string, string[]>();
  for (const font of fonts) {
    const slug = categorySlug(font.category);
    const dates = categoryDates.get(slug) || [];
    if (font.last_updated) dates.push(font.last_updated);
    categoryDates.set(slug, dates);
  }

  return [...categoryDates.entries()].flatMap(([slug, dates]) =>
    localizedEntries(`/category/${slug}/`, latestLastmod(dates))
  );
}

function staticPageEntries(fonts: FontEntry[], posts: BlogPost[]): SitemapEntry[] {
  const homepageLastmod = latestLastmod([
    ...fonts.map((font) => font.last_updated),
    ...posts.map((post) => post.date),
  ]);
  const staticPaths = ['/', '/about/', '/contact/', '/privacy/', '/terms/', '/disclaimer/'];

  return staticPaths.flatMap((path) =>
    localizedEntries(path, path === '/' ? homepageLastmod : undefined)
  );
}

function blogEntries(posts: BlogPost[]): SitemapEntry[] {
  const eligiblePosts = posts
    .map((post) => ({
      post,
      locales: completeBlogLocales(post, SITEMAP_LOCALES) as Array<typeof SITEMAP_LOCALES[number]>,
    }))
    .filter(({ locales }) => locales.length > 0);
  const blogLastmod = latestLastmod(eligiblePosts.map(({ post }) => post.date));
  return [
    ...localizedEntries('/blog/', blogLastmod),
    ...eligiblePosts.flatMap(({ post, locales }) =>
      localizedEntries(`/blog/${post.slug}/`, post.date, locales)
    ),
  ];
}

async function createSitemapCollections(): Promise<SitemapCollections> {
  const fonts = await loadFontRegistry();
  const fontsList = fontEntries(fonts);
  const categoriesList = categoryEntries(fonts);
  const pagesList = staticPageEntries(fonts, blogPosts);
  const blogList = blogEntries(blogPosts);
  const fontLastmod = latestLastmod(fonts.map((font) => font.last_updated));
  const blogLastmod = latestLastmod(blogPosts.map((post) => post.date));

  return {
    fonts: fontsList,
    categories: categoriesList,
    pages: pagesList,
    blog: blogList,
    all: [...pagesList, ...categoriesList, ...fontsList, ...blogList],
    lastmod: {
      fonts: fontLastmod,
      categories: fontLastmod,
      pages: latestLastmod([fontLastmod, blogLastmod]),
      blog: blogLastmod,
      images: fontLastmod,
    },
  };
}

export function getSitemapCollections(): Promise<SitemapCollections> {
  collectionsPromise ||= createSitemapCollections();
  return collectionsPromise;
}
