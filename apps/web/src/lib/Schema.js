const supportedLocales = ['en', 'es', 'pt'];

function withTrailingSlash(value) {
  return value.endsWith('/') ? value : `${value}/`;
}

function localePrefix(locale) {
  return locale === 'en' ? '' : `/${locale}`;
}

export function buildHomePageSchema({
  siteUrl = 'https://sinpes.com',
  pageUrl,
  locale = 'en',
  title,
  description,
  fonts = [],
  categories = [],
}) {
  const site = withTrailingSlash(siteUrl);
  const page = withTrailingSlash(pageUrl || site);
  const prefix = localePrefix(locale);
  const organizationId = `${site}#organization`;
  const websiteId = `${site}#website`;
  const pageId = `${page}#webpage`;
  const listId = `${page}#font-list`;
  const categoryKeywords = [...new Set(categories.filter(Boolean))];

  const itemListElement = fonts.map((font, index) => ({
    '@type': 'ListItem',
    position: index + 1,
    name: font.display_name,
    url: `${site.replace(/\/$/, '')}${prefix}/font/${font.slug}/`,
  }));

  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': organizationId,
        name: 'SINPES',
        url: site,
        logo: {
          '@type': 'ImageObject',
          url: `${site}favicon.svg`,
        },
      },
      {
        '@type': 'WebSite',
        '@id': websiteId,
        name: 'SINPES',
        url: site,
        publisher: { '@id': organizationId },
        inLanguage: supportedLocales,
        potentialAction: {
          '@type': 'SearchAction',
          target: {
            '@type': 'EntryPoint',
            urlTemplate: `${page}?q={search_term_string}`,
          },
          'query-input': 'required name=search_term_string',
        },
      },
      {
        '@type': 'CollectionPage',
        '@id': pageId,
        name: title,
        description,
        url: page,
        isPartOf: { '@id': websiteId },
        about: {
          '@type': 'Thing',
          name: 'Free fonts and open-source typography',
        },
        inLanguage: locale,
        keywords: categoryKeywords.join(', '),
        mainEntity: { '@id': listId },
      },
      {
        '@type': 'ItemList',
        '@id': listId,
        name: `${title} font archive`,
        numberOfItems: itemListElement.length,
        itemListOrder: 'https://schema.org/ItemListOrderDescending',
        itemListElement,
      },
    ],
  };
}
