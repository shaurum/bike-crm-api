#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import https from 'https';

const API_URL = process.env.PUBLIC_API_URL;
const API_KEY = process.env.PUBLIC_API_KEY;
const OUT = path.resolve(process.cwd(), 'src/data/bikes.json');
const PHOTOS = path.resolve(process.cwd(), 'public/bikes');

if (!API_URL) {
  console.log('No PUBLIC_API_URL set, keeping existing bikes.json');
  process.exit(0);
}

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
    }, (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(new Error('timeout')); });
  });
}

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (res) => {
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(); });
    }).on('error', (err) => {
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

async function run() {
  try {
    const data = await fetchJson(`${API_URL.replace(/\/$/, '')}/api/v1/public/bikes?available_only=true`);
    const bikes = Array.isArray(data) ? data : (data.items || []);
    
    // Group by model
    const groups = new Map();
    for (const b of bikes) {
      const key = b.model;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(b);
    }
    
    const out = {
      updated_at: new Date().toISOString(),
      source: 'api',
      bikes: []
    };
    
    if (!fs.existsSync(PHOTOS)) fs.mkdirSync(PHOTOS, { recursive: true });
    
    for (const [model, list] of groups) {
      const first = list[0];
      const prices = first.prices || [];
      const priceMap = { week: null, two_week: null, month: null };
      for (const p of prices) {
        const mins = p.duration_min || 0;
        if (mins >= 7*24*60 && mins < 14*24*60) priceMap.week = p.price;
        else if (mins >= 14*24*60 && mins < 30*24*60) priceMap.two_week = p.price;
        else if (mins >= 30*24*60) priceMap.month = p.price;
      }
      
      const week = priceMap.week || 6500;
      const per_day = Math.floor(week / 7 / 10) * 10;
      
      out.bikes.push({
        id: first.id,
        model,
        slug: model.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
        color: first.color,
        year: first.year,
        battery_capacity: first.battery_capacity,
        max_speed: first.max_speed,
        range_km: first.range_km,
        photos: first.photos || [],
        available_count: list.filter(b => b.status === 'available').length || list.length,
        prices: [
          priceMap.week ? { label: 'Неделя', amount: priceMap.week } : null,
          priceMap.two_week ? { label: '2 недели', amount: priceMap.two_week } : null,
          priceMap.month ? { label: 'Месяц', amount: priceMap.month } : null,
        ].filter(Boolean),
        deposit: prices[0]?.deposit || 0,
        per_day
      });
    }
    
    // Atomic write - don't overwrite if failed partially? write to tmp then rename
    const tmp = OUT + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(out, null, 2));
    fs.renameSync(tmp, OUT);
    console.log(`Updated ${out.bikes.length} bike groups`);
  } catch (e) {
    console.error('Fetch failed, keeping old data:', e.message);
    process.exit(0);
  }
}

run();
