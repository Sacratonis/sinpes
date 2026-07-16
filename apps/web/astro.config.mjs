import { defineConfig } from 'astro/config';
import preact from '@astrojs/preact';

export default defineConfig({
  output: 'static',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es', 'pt'],
  },
  integrations: [
    preact(),
  ],
  site: 'https://sinpes.com',
});
