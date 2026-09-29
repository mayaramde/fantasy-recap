// Headless ESPN capture for the cloud live update (.github/workflows/live-update.yml).
//
// Runs the same scripts/capture.js that Chrome runs, so the trimming logic lives in one
// place. Instead of a logged-in browser, ESPN requests carry the cookies from the
// ESPN_S2 and ESPN_SWID environment variables (GitHub Actions secrets that Maya set).
// The cookies are never printed or written to disk. The POST that capture.js normally
// sends to scripts/receive.py is handled here and written to
// data/<season>/week-NN/espn.json with the same checks receive.py applies.
//
// Usage: ESPN_S2=... ESPN_SWID=... node scripts/capture_node.mjs current   (or: 3 4)

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const { ESPN_S2, ESPN_SWID } = process.env;
if (!ESPN_S2 || !ESPN_SWID) {
  console.error('ESPN_S2 and ESPN_SWID must be set');
  process.exit(1);
}
const COOKIE = `espn_s2=${ESPN_S2}; SWID=${ESPN_SWID}`;
const ESPN = 'https://lm-api-reads.fantasy.espn.com/';
// ESPN's public NFL scoreboard (game states for the live box score). It takes no session,
// so it is fetched as-is and the cookies below never go anywhere near it.
const PUBLIC = 'https://site.api.espn.com/';
const RECEIVER = 'http://127.0.0.1:8765/save';
const realFetch = globalThis.fetch;

function save(url, init) {
  const week = Number(new URL(url).searchParams.get('week'));
  const data = JSON.parse(init.body);
  if (data.week !== week || week < 1 || week > 18 || !data.matchups?.length) {
    throw new Error(`invalid capture for week ${week}`);
  }
  const rel = join('data', String(data.season), `week-${String(week).padStart(2, '0')}`, 'espn.json');
  mkdirSync(dirname(join(ROOT, rel)), { recursive: true });
  const text = JSON.stringify(data, null, 1) + '\n';
  writeFileSync(join(ROOT, rel), text);
  return new Response(JSON.stringify({ saved: rel, bytes: Buffer.byteLength(text) }));
}

globalThis.window = globalThis;
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith(RECEIVER)) return save(url, init);
  if (url.startsWith(PUBLIC)) return realFetch(url, init);
  if (!url.startsWith(ESPN)) throw new Error(`unexpected fetch: ${url}`);
  const res = await realFetch(url, { ...init, headers: { ...init.headers, Cookie: COOKIE } });
  if (!res.ok) throw new Error(`ESPN ${res.status}: cookies may have expired`);
  return res;
};

(0, eval)(readFileSync(join(ROOT, 'scripts', 'capture.js'), 'utf8'));
const args = process.argv.slice(2);
const weeks = args[0] === 'current' ? 'current' : args.map(Number);
const out = await window.fantasyCapture(weeks);
console.log(JSON.stringify(out, null, 1));
