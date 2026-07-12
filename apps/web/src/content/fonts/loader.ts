export interface FontEntry {
  slug: string;
  display_name: string;
  is_demo: boolean;
  category: string;
  use_cases: string;
  variants: string[];
  weights: string[] | null;
  woff2_url: string;
  download_zip_url?: string;
  file_format: string;
  file_size_kb: number;
  last_updated: string;
  translations: Record<string, { description: string; seo_image_url: string; primary_keyword?: string }>;
}

export async function loadFontRegistry(): Promise<FontEntry[]> {
  const url = import.meta.env.SNAPSHOT_PRESIGNED_URL;
  if (!url) {
    console.warn("No SNAPSHOT_PRESIGNED_URL provided, falling back to mock data.");
    return [
      {
        slug: 'mock-sans',
        display_name: 'Mock Sans',
        is_demo: false,
        category: 'Sans-Serif',
        use_cases: 'UI, Web',
        variants: ['Regular', 'Bold'],
        weights: ['400', '700'],
        woff2_url: 'https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hjp-Ek-_EeA.woff2',
        download_zip_url: '#download',
        file_format: 'ttf',
        file_size_kb: 124,
        last_updated: new Date().toISOString(),
        translations: {
          en: { description: 'A clean and versatile sans-serif typeface for UI and editorial design.', seo_image_url: 'https://picsum.photos/1200/600' },
          es: { description: 'Una tipografía sans-serif limpia y versátil para UI y diseño editorial.', seo_image_url: 'https://picsum.photos/1200/600' },
          pt: { description: 'Uma tipografia sans-serif limpa e versátil para UI e design editorial.', seo_image_url: 'https://picsum.photos/1200/600' }
        }
      }
    ]; // Return mock data block in dev
  }
  
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to fetch snapshot: ${res.status}`);
  }
  
  return res.json() as Promise<FontEntry[]>;
}