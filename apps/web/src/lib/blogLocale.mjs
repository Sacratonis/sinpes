export const BLOG_LOCALES = ['en', 'es', 'pt'];

function hasText(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

export function hasCompleteBlogLocale(post, locale) {
  return Boolean(
    post &&
    hasText(post.title?.[locale]) &&
    hasText(post.excerpt?.[locale]) &&
    hasText(post.content?.[locale])
  );
}

export function completeBlogLocales(post, locales = BLOG_LOCALES) {
  return locales.filter((locale) => hasCompleteBlogLocale(post, locale));
}
