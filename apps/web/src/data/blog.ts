export interface BlogPost {
  slug: string; date: string;
  title: { en: string; es: string; pt: string };
  excerpt: { en: string; es: string; pt: string };
  content: { en: string; es: string; pt: string };
  image_url?: string;
  image_alt_text?: string;
  target_keyword?: string;
}

export async function loadBlogPosts(): Promise<BlogPost[]> {
  const url = import.meta.env.BLOG_SNAPSHOT_PRESIGNED_URL;
  if (!url) {
    console.warn("No BLOG_SNAPSHOT_PRESIGNED_URL provided; blog will be empty.");
    return [];
  }

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch blog snapshot: ${response.status}`);
  }
  return response.json() as Promise<BlogPost[]>;
}

export const blogPosts: BlogPost[] = await loadBlogPosts();
