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