import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://shaurum.github.io',
  base: '/bike-crm-api/',
  output: 'static',
  build: {
    assets: 'assets'
  }
});
