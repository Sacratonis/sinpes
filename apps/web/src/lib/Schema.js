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
  const navigationId = `${site}#site-navigation`;
  const categoryKeywords = [...new Set(categories.filter(Boolean))];
  const navigationItems = [
    { name: 'Font Library', url: `${site.replace(/\/$/, '')}${prefix || ''}/` },
    { name: 'Blog', url: `${site.replace(/\/$/, '')}${prefix}/blog/` },
    { name: 'About', url: `${site.replace(/\/$/, '')}${prefix}/about/` },
    { name: 'Contact', url: `${site.replace(/\/$/, '')}${prefix}/contact/` },
    ...categoryKeywords.slice(0, 8).map((category) => ({
      name: `${category} Fonts`,
      url: `${site.replace(/\/$/, '')}${prefix}/category/${category.toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}/`,
    })),
  ];

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
        alternateName: ['Sinpes Fonts', 'Free Fonts for Everyone'],
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
        '@type': 'SiteNavigationElement',
        '@id': navigationId,
        name: 'SINPES primary navigation',
        hasPart: navigationItems.map((item, index) => ({
          '@type': 'WebPage',
          position: index + 1,
          name: item.name,
          url: item.url,
        })),
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
          name: 'Free fonts and typography resources',
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
