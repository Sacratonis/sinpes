/**
 * SEO Utilities to manage reciprocal hreflang and canonical routing.
 */
import { languages, defaultLang } from '../i18n/ui';
import { getLanguageUrl } from '../i18n/utils';

export function generateCanonical(siteUrl: string | URL, pathname: string): string {
  const url = typeof siteUrl === 'string' ? new URL(siteUrl) : siteUrl;
  
  // Strip trailing slash for consistent SEO equity, unless it's the root
  const cleanPath = pathname.endsWith('/') && pathname.length > 1 
    ? pathname.slice(0, -1) 
    : pathname;
    
  return new URL(cleanPath, url).href;
}

export function generateHreflang(siteUrl: string | URL, pathname: string, currentLocale: keyof typeof languages) {
  const url = typeof siteUrl === 'string' ? new URL(siteUrl) : siteUrl;
  
  const links: Record<string, string> = {};
  
  for (const langCode of Object.keys(languages)) {
    const path = getLanguageUrl(pathname, currentLocale as any, langCode as any);
    links[langCode] = new URL(path, url).href;
  }
  
  const xDefaultPath = getLanguageUrl(pathname, currentLocale as any, defaultLang as any);
  links['x-default'] = new URL(xDefaultPath, url).href;
  
  return links;
}