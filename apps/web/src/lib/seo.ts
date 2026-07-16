/**
 * SEO Utilities to manage reciprocal hreflang and canonical routing.
 */
import { languages, defaultLang } from '../i18n/ui';
import { getLanguageUrl } from '../i18n/utils';

export function generateCanonical(siteUrl: string | URL, pathname: string): string {
  const url = typeof siteUrl === 'string' ? new URL(siteUrl) : siteUrl;
  return new URL(normalizeSeoPath(pathname), url).href;
}

export function generateHreflang(
  siteUrl: string | URL,
  pathname: string,
  currentLocale: keyof typeof languages,
  availableLocales: Array<keyof typeof languages> = Object.keys(languages) as Array<keyof typeof languages>
) {
  const url = typeof siteUrl === 'string' ? new URL(siteUrl) : siteUrl;
  
  const links: Record<string, string> = {};
  
  for (const langCode of availableLocales) {
    const path = getLanguageUrl(pathname, currentLocale as any, langCode as any);
    links[langCode] = new URL(normalizeSeoPath(path), url).href;
  }
  
  const xDefaultLocale = availableLocales.includes(defaultLang)
    ? defaultLang
    : availableLocales[0];
  if (xDefaultLocale) {
    const xDefaultPath = getLanguageUrl(pathname, currentLocale as any, xDefaultLocale as any);
    links['x-default'] = new URL(normalizeSeoPath(xDefaultPath), url).href;
  }
  
  return links;
}

function normalizeSeoPath(pathname: string): string {
  const path = pathname.startsWith('/') ? pathname : `/${pathname}`;
  if (path === '/' || path.endsWith('/') || /\/[^/]+\.[a-z0-9]+$/i.test(path)) return path;
  return `${path}/`;
}

export function buildMetaDescription(value: string, maxLength = 160): string {
  const clean = String(value || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLength) return clean;

  const clipped = clean.slice(0, maxLength - 1);
  const lastSpace = clipped.lastIndexOf(' ');
  const safe = lastSpace > Math.floor(maxLength * 0.7) ? clipped.slice(0, lastSpace) : clipped;
  return `${safe.replace(/[,:;\s]+$/, '')}…`;
}
