export function generateSoftwareApplicationSchema(font: any, url: string) {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": font.display_name,
    "applicationCategory": "Font",
    "operatingSystem": "All",
    "fileSize": `${font.file_size_kb} KB`,
    "fileFormat": font.file_format,
    "url": url,
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD"
    }
  });
}

interface FontPageSchemaInput {
  pageUrl: string;
  fontName: string;
  description: string;
  locale: string;
  category: string;
  keyword?: string;
  useCases: string[];
  imageUrl?: string;
  imageAlt: string;
  lastUpdated?: string;
  downloadUrl?: string;
  libraryName: string;
  libraryUrl: string;
  categoryUrl: string;
}

export function buildFontPageSchema(input: FontPageSchemaInput) {
  const fontId = `${input.pageUrl}#font`;
  const pageId = `${input.pageUrl}#webpage`;
  const imageId = input.imageUrl ? `${input.pageUrl}#primaryimage` : undefined;
  const graph: Record<string, unknown>[] = [
    {
      '@type': 'WebPage',
      '@id': pageId,
      url: input.pageUrl,
      name: input.fontName,
      description: input.description,
      inLanguage: input.locale,
      mainEntity: { '@id': fontId },
      primaryImageOfPage: imageId ? { '@id': imageId } : undefined,
    },
    {
      '@type': 'CreativeWork',
      '@id': fontId,
      name: input.fontName,
      description: input.description,
      url: input.pageUrl,
      image: imageId ? { '@id': imageId } : undefined,
      inLanguage: input.locale,
      genre: input.category,
      keywords: [input.keyword, ...input.useCases].filter(Boolean).join(', '),
      isAccessibleForFree: true,
      dateModified: input.lastUpdated || undefined,
      encoding: input.downloadUrl ? {
        '@type': 'MediaObject',
        contentUrl: input.downloadUrl,
        encodingFormat: 'application/zip',
      } : undefined,
    },
  ];
  if (input.imageUrl && imageId) {
    graph.push({
      '@type': 'ImageObject',
      '@id': imageId,
      contentUrl: input.imageUrl,
      url: input.imageUrl,
      caption: input.imageAlt,
      representativeOfPage: true,
    });
  }
  graph.push({
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: input.libraryName, item: input.libraryUrl },
      { '@type': 'ListItem', position: 2, name: input.category, item: input.categoryUrl },
      { '@type': 'ListItem', position: 3, name: input.fontName, item: input.pageUrl },
    ],
  });
  return { '@context': 'https://schema.org', '@graph': graph };
}
