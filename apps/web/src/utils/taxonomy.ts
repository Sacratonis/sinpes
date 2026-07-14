const preservedAcronyms = new Set(['UI', 'UX', 'AI', 'AR', 'VR', '3D']);

export const categorySlug = (value: string) => value
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-|-$/g, '');

export const formatTaxonomyLabel = (value: string) => value
  .trim()
  .replace(/-/g, ' ')
  .replace(/\S+/g, (word) => {
    const upper = word.toUpperCase();
    if (preservedAcronyms.has(upper)) return upper;
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });

export const uniqueCategoryLabels = (values: string[]) => {
  const categories = new Map<string, string>();
  values.filter(Boolean).forEach((value) => {
    const slug = categorySlug(value);
    if (slug && !categories.has(slug)) categories.set(slug, formatTaxonomyLabel(value));
  });
  return [...categories.values()].sort((a, b) => a.localeCompare(b));
};

export const parseUseCases = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(String).map(item => item.trim()).filter(Boolean);
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map(String).map(item => item.trim()).filter(Boolean);
  } catch {
    // Legacy comma-separated values are handled below.
  }
  return value.split(',').map(item => item.replace(/[\[\]"]+/g, '').trim()).filter(Boolean);
};
