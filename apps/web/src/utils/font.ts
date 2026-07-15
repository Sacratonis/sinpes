/**
 * Sanitizes a font family name for safe CSS injection.
 * Strips out dangerous characters ({, }, <, >, ;, ") that could break out 
 * of a @font-face block, while preserving Unicode letters, numbers, spaces, and hyphens.
 */
export function sanitizeFontFamily(name: string): string {
  if (!name) return '';
  return name.replace(/[^\p{L}\p{N} \-]/gu, '');
}

export interface FontVariant {
  weight?: number | string;
  style?: string;
  url?: string;
  filename?: string;
}

function variantPreference(variant: FontVariant): number {
  const filename = String(variant.filename || '').toLowerCase();
  if (/outline|\bhc\b|\blc\b/.test(filename)) return 2;
  if (/regular|italic/.test(filename)) return 0;
  return 1;
}

export function buildFontFaceCSS(
  displayName: string,
  variants: FontVariant[] | undefined,
  fallbackUrl?: string,
): string {
  const family = sanitizeFontFamily(displayName);
  const candidates = Array.isArray(variants)
    ? variants.filter((variant) => typeof variant?.url === 'string' && variant.url)
    : [];

  const selected = new Map<string, FontVariant>();
  for (const variant of candidates) {
    const weight = Number(variant.weight) || 400;
    const style = variant.style === 'italic' ? 'italic' : 'normal';
    const key = `${weight}-${style}`;
    const current = selected.get(key);
    if (!current || variantPreference(variant) < variantPreference(current)) {
      selected.set(key, variant);
    }
  }

  if (!selected.size && fallbackUrl) {
    selected.set('400-normal', { weight: 400, style: 'normal', url: fallbackUrl });
  }

  return [...selected.values()].map((variant) => {
    const weight = Number(variant.weight) || 400;
    const style = variant.style === 'italic' ? 'italic' : 'normal';
    return `@font-face { font-family: "${family}"; src: url(${JSON.stringify(variant.url)}) format("woff2"); font-weight: ${weight}; font-style: ${style}; font-display: swap; }`;
  }).join('\n');
}
