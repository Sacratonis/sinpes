/// <reference path="../.astro/types.d.ts" />

interface ImportMetaEnv {
  readonly SNAPSHOT_PRESIGNED_URL?: string;
  readonly BLOG_SNAPSHOT_PRESIGNED_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
