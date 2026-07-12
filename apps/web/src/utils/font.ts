/**
 * Sanitizes a font family name for safe CSS injection.
 * Strips out dangerous characters ({, }, <, >, ;, ") that could break out 
 * of a @font-face block, while preserving Unicode letters, numbers, spaces, and hyphens.
 */
export function sanitizeFontFamily(name: string): string {
  if (!name) return '';
  return name.replace(/[^\p{L}\p{N} \-]/gu, '');
}
