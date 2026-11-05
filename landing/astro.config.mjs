import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://vzuhandgo.ru',
  // Сайт открывается с собственного домена (vzuhandgo.ru), поэтому из корня
  base: '/',
  output: 'static',
  build: {
    assets: 'assets'
  }
});
