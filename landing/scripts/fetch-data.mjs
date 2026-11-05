#!/usr/bin/env node
// Данные байков для лендинга из CRM («Парковка») перед сборкой.
//
// PUBLIC_API_URL — адрес CRM (например https://crm.example.com),
// PUBLIC_API_KEY — ключ публичного API (в CRM: Настройки → Ключи и токены).
// Байки группируются по модели; фото скачиваются в public/bikes/, чтобы сайт
// на GitHub Pages не зависел от того, включён ли сервер CRM.
// При любой ошибке остаётся прежний public/bikes.json — сайт не пустеет.
import fs from 'fs';
import path from 'path';
import http from 'http';
import https from 'https';

const API_URL = (process.env.PUBLIC_API_URL || '').replace(/\/$/, '');
const API_KEY = process.env.PUBLIC_API_KEY || '';
const OUT = path.resolve(process.cwd(), 'public/bikes.json');
const PHOTOS_DIR = path.resolve(process.cwd(), 'public/bikes');
const TIMEOUT_MS = 20000;
const PHOTO_EXTS = new Set(['.png', '.webp', '.jpg', '.jpeg', '.gif']);
const DAY = 24 * 60;

if (!API_URL) {
  console.log('PUBLIC_API_URL не задан — оставляю текущий bikes.json');
  process.exit(0);
}

function get(url, headers = {}, redirects = 3) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https:') ? https : http;
    const req = client.get(url, { headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirects > 0) {
        res.resume();
        resolve(get(new URL(res.headers.location, url).toString(), headers, redirects - 1));
        return;
      }
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`${url}: HTTP ${res.statusCode}`));
        return;
      }
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve(Buffer.concat(chunks)));
    });
    req.on('error', reject);
    req.setTimeout(TIMEOUT_MS, () => req.destroy(new Error(`${url}: timeout`)));
  });
}

function slugify(model) {
  const translit = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y',
    к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f',
    х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
  };
  const latin = model.toLowerCase().split('').map((ch) => translit[ch] ?? ch).join('');
  return latin.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'bike';
}

function priceFor(prices, minDays, maxDays) {
  const hit = prices.find((p) => p.duration_min >= minDays * DAY && p.duration_min < maxDays * DAY);
  return hit ? hit.price : null;
}

async function downloadPhoto(photo, slug) {
  // Фото из CRM приходят путём /uploads/...; внешние ссылки берём как есть
  const url = /^https?:\/\//.test(photo) ? photo : `${API_URL}${photo.startsWith('/') ? '' : '/'}${photo}`;
  const ext = path.extname(new URL(url).pathname).toLowerCase();
  if (!PHOTO_EXTS.has(ext)) return null;
  const data = await get(url);
  const name = `${slug}${ext === '.jpeg' ? '.jpg' : ext}`;
  fs.writeFileSync(path.join(PHOTOS_DIR, name), data);
  return `/bikes/${name}`;
}

async function run() {
  const raw = await get(`${API_URL}/api/v1/public/bikes?available_only=false`, API_KEY ? { 'X-API-Key': API_KEY } : {});
  const bikes = JSON.parse(raw.toString('utf8'));
  if (!Array.isArray(bikes)) throw new Error('CRM вернула не список байков');
  if (bikes.length === 0) {
    console.log('В CRM нет байков — оставляю текущий bikes.json');
    return;
  }

  const groups = new Map();
  for (const bike of bikes) {
    if (!groups.has(bike.model)) groups.set(bike.model, []);
    groups.get(bike.model).push(bike);
  }

  fs.mkdirSync(PHOTOS_DIR, { recursive: true });
  const out = { updated_at: new Date().toISOString(), source: 'crm', bikes: [] };

  for (const [model, list] of groups) {
    // У байков одной модели поля заполнены по-разному: берём первое непустое
    const withPrices = list.find((b) => b.prices && b.prices.length) || list[0];
    const withPhoto = list.find((b) => b.photos && b.photos.length);
    const pick = (field) => list.map((b) => b[field]).find((v) => v !== null && v !== undefined && v !== '') ?? null;
    const slug = slugify(model);

    let photos = [];
    if (withPhoto) {
      try {
        const local = await downloadPhoto(withPhoto.photos[0], slug);
        if (local) photos = [local];
      } catch (e) {
        console.warn(`Фото ${model} не скачано: ${e.message}`);
      }
    }

    const prices = withPrices.prices || [];
    const week = priceFor(prices, 7, 14);
    const twoWeeks = priceFor(prices, 14, 30);
    const month = priceFor(prices, 30, Infinity);

    out.bikes.push({
      id: withPrices.id,
      model,
      slug,
      color: pick('color'),
      year: pick('year'),
      battery_capacity: pick('battery_capacity'),
      max_speed: pick('max_speed'),
      range_km: pick('range_km'),
      photos,
      // CRM до v1.1.8 не отдаёт is_available — тогда смотрим на статус
      available_count: list.filter((b) => (b.is_available ?? b.status === 'available')).length,
      total_count: list.length,
      prices: [
        week ? { label: 'Неделя', amount: week } : null,
        twoWeeks ? { label: '2 недели', amount: twoWeeks } : null,
        month ? { label: 'Месяц', amount: month } : null,
      ].filter(Boolean),
      deposit: prices[0]?.deposit || 0,
      per_day: Math.floor((week || 6500) / 7 / 10) * 10,
    });
  }

  // Сначала модели, которые можно взять прямо сейчас
  out.bikes.sort((a, b) => (b.available_count > 0) - (a.available_count > 0) || a.model.localeCompare(b.model, 'ru'));

  const tmp = `${OUT}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(out, null, 2)}\n`);
  fs.renameSync(tmp, OUT);
  console.log(`Загружено из CRM: ${out.bikes.length} моделей, ${bikes.length} байков`);
}

run().catch((e) => {
  console.error(`Не удалось получить данные из CRM, оставляю прежние: ${e.message || e.code || e}`);
  process.exit(0);
});
