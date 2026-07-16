interface BlogArticleSchemaInput {
  pageUrl: string;
  blogUrl: string;
  homeUrl: string;
  aboutUrl: string;
  title: string;
  description: string;
  contentHtml: string;
  locale: string;
  publishedAt: string;
  modifiedAt?: string;
  imageUrl?: string;
  imageAlt?: string;
  targetKeyword?: string;
  blogName: string;
  homeName: string;
}

function plainText(value: string): string {
  return value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

export function buildBlogArticleSchema(input: BlogArticleSchemaInput) {
  const pageId = `${input.pageUrl}#webpage`;
  const articleId = `${input.pageUrl}#article`;
  const breadcrumbId = `${input.pageUrl}#breadcrumb`;
  const organizationId = `${input.homeUrl}#organization`;
  const imageId = input.imageUrl ? `${input.pageUrl}#primaryimage` : undefined;
  const articleText = plainText(input.contentHtml);
  const wordCount = articleText ? articleText.split(/\s+/).length : undefined;

  const graph: Record<string, unknown>[] = [
    {
      '@type': 'WebPage',
      '@id': pageId,
      url: input.pageUrl,
      name: input.title,
      description: input.description,
      inLanguage: input.locale,
      isPartOf: { '@id': input.blogUrl },
      mainEntity: { '@id': articleId },
      breadcrumb: { '@id': breadcrumbId },
      primaryImageOfPage: imageId ? { '@id': imageId } : undefined,
    },
    {
      '@type': 'BlogPosting',
      '@id': articleId,
      url: input.pageUrl,
      headline: input.title,
      description: input.description,
      articleBody: articleText || undefined,
      wordCount,
      inLanguage: input.locale,
      datePublished: input.publishedAt,
      dateModified: input.modifiedAt || input.publishedAt,
      articleSection: 'Typography',
      keywords: input.targetKeyword || undefined,
      isAccessibleForFree: true,
      mainEntityOfPage: { '@id': pageId },
      isPartOf: { '@id': input.blogUrl },
      author: {
        '@type': 'Organization',
        name: 'SINPES',
        url: input.aboutUrl,
      },
      publisher: { '@id': organizationId },
      image: imageId ? { '@id': imageId } : undefined,
    },
    {
      '@type': 'Organization',
      '@id': organizationId,
      name: 'SINPES',
      url: input.homeUrl,
    },
    {
      '@type': 'BreadcrumbList',
      '@id': breadcrumbId,
      itemListElement: [
        {
          '@type': 'ListItem',
          position: 1,
          name: input.homeName,
          item: input.homeUrl,
        },
        {
          '@type': 'ListItem',
          position: 2,
          name: input.blogName,
          item: input.blogUrl,
        },
        {
          '@type': 'ListItem',
          position: 3,
          name: input.title,
          item: input.pageUrl,
        },
      ],
    },
  ];

  if (input.imageUrl && imageId) {
    graph.push({
      '@type': 'ImageObject',
      '@id': imageId,
      contentUrl: input.imageUrl,
      url: input.imageUrl,
      caption: input.imageAlt || input.title,
      representativeOfPage: true,
      width: 1200,
      height: 630,
    });
  }

  return {
    '@context': 'https://schema.org',
    '@graph': graph,
  };
}
