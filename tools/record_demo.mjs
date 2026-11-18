// Records a demo video of the local app: real photo reading, a real generation and the instructions.
// Usage: node tools/record_demo.mjs <output_dir> <photo.jpg> "<request>"
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const [OUT, PHOTO, REQUEST = 'a dog'] = process.argv.slice(2);
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const URL_APP = 'http://127.0.0.1:8765/';
const sleep = ms => new Promise(r => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });
const framesDir = path.join(OUT, 'frames');
fs.rmSync(framesDir, { recursive: true, force: true });
fs.mkdirSync(framesDir, { recursive: true });

const browser = spawn(EDGE, ['--headless=new', '--remote-debugging-port=9333', `--user-data-dir=${path.join(OUT, 'profile')}`,
  '--window-size=1440,900', '--hide-scrollbars', '--no-first-run', 'about:blank'], { stdio: 'ignore' });
let targets = [];
for (let i = 0; i < 30 && !targets.length; i++) {
  await sleep(500);
  try { targets = (await (await fetch('http://127.0.0.1:9333/json')).json()).filter(t => t.type === 'page'); } catch {}
}
const ws = new WebSocket(targets[0].webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let seq = 0; const pending = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise(r => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

await send('Page.enable'); await send('Runtime.enable'); await send('DOM.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

const frames = [];
let n = 0;
async function shot(seconds) {
  const r = await send('Page.captureScreenshot', { format: 'jpeg', quality: 88 });
  const f = path.join(framesDir, `f${String(++n).padStart(4, '0')}.jpg`);
  fs.writeFileSync(f, Buffer.from(r.result.data, 'base64'));
  frames.push([f, seconds]);
}
async function caption(text) {
  await ev(`(()=>{let c=document.getElementById('cap');if(!c){c=document.createElement('div');c.id='cap';
  c.style.cssText='position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#4b2e83;color:#fff;font:600 24px system-ui,Segoe UI,Arial;padding:14px 26px;border-radius:14px;z-index:99999;box-shadow:0 8px 24px #0005;max-width:88vw;text-align:center';
  document.body.appendChild(c)}c.textContent=${JSON.stringify(text)};})()`);
  await sleep(150);
}
async function waitFor(expr, ms) { const end = Date.now() + ms; while (Date.now() < end) { if (await ev(expr)) return true; await sleep(500); } return false; }

// 0. start clean, with the 36 real bricks
await fetch(URL_APP + 'api/reset', { method: 'POST', body: '{}' });
await send('Page.navigate', { url: URL_APP });
await waitFor("document.querySelectorAll('.card').length>0", 15000);
await sleep(800);
await caption('Build What You Have: una IA diseña con las piezas que tienes');
await shot(3.5);

// 1. photo -> list
await caption('1. Foto de las piezas: el lector (OpenCV) las detecta');
const doc = await send('DOM.getDocument', { depth: -1 });
const node = await send('DOM.querySelector', { nodeId: doc.result.root.nodeId, selector: '#ph' });
await send('DOM.setFileInputFiles', { nodeId: node.result.nodeId, files: [path.resolve(PHOTO)] });
await ev("document.querySelector('#ph').dispatchEvent(new Event('change'))");
await waitFor("!!document.querySelector('#useph')", 60000);
await ev("document.querySelector('#phr').scrollIntoView({block:'center'})");
await sleep(600);
await shot(5);
await ev("document.querySelector('#useph').click()");
await sleep(1500);
await ev("window.scrollTo(0,0)");
await caption('2. La lista de piezas: la persona corrige un falso positivo (un pliegue de la tela)');
await shot(3);
await ev("(()=>{const i=S.inventory.findIndex(r=>r.part=='3004'&&r.color==15);if(i<0)return;const b=document.querySelector('#inv button[data-i=\"'+i+'\"][data-d=\"-1\"]');b.click();})()");
await sleep(1500);
await caption('Lista corregida: 36 piezas, las mismas que tienes');
await shot(3.5);

// 2. request -> real generation
await ev(`document.querySelector('#req').value=${JSON.stringify(REQUEST)}`);
await caption(`3. Se pide algo: "${REQUEST}"`);
await shot(3);
await ev("document.querySelector('#go').click()");
await sleep(2500);
const t0 = Date.now();
let job = null;
while (Date.now() - t0 < 12 * 60 * 1000) {
  job = await ev("fetch('/api/jobs').then(r=>r.json()).then(j=>j[0])");
  const mins = Math.floor((Date.now() - t0) / 60000), secs = Math.floor((Date.now() - t0) / 1000) % 60;
  await caption(`4. El agente diseña con BrickWright y valida su código (${mins} min ${secs} s, video acelerado)`);
  await shot(0.4);
  if (job && !['queued', 'running'].includes(job.status)) break;
  await sleep(10000);
}
await sleep(2500);

// 3. result, count and instructions
if (job && job.design) {
  const c = job.check || {};
  const msg = job.status === 'done' ? `5. Conteo independiente: usa ${c.used} de ${c.owned} piezas, todas tuyas`
    : `5. Conteo independiente: rechazado, se pasa de tus piezas`;
  await ev(`openD(${JSON.stringify(job.design)})`);
  await sleep(1500);
  await caption(msg);
  await shot(5);
  await caption('6. Instrucciones capa por capa para armarlo');
  for (let i = 0; i < 4; i++) {
    const more = await ev("(()=>{const b=document.querySelector('#nx');if(!b||b.disabled)return false;b.click();return true})()");
    await sleep(500);
    await shot(1.6);
    if (!more) break;
  }
  await ev("document.querySelector('#dlg').close()");
} else {
  await caption(`El diseño no se completó: ${job ? (job.error || job.status) : 'sin respuesta'}`);
  await shot(4);
}

// 4. gallery
await ev("document.querySelector('#h-gal').scrollIntoView({block:'start'})");
await sleep(800);
await caption('Galería: 41 diseños, filtrados por lo que puedes armar con tus piezas');
await shot(4);

// encode with ffmpeg (concat demuxer with per-frame durations)
const list = frames.map(([f, d]) => `file '${f.replace(/\\/g, '/')}'\nduration ${d}`).join('\n') + `\nfile '${frames.at(-1)[0].replace(/\\/g, '/')}'\n`;
fs.writeFileSync(path.join(OUT, 'frames.txt'), list);
const video = path.join(OUT, 'demo_build_what_you_have.mp4');
execFileSync('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', path.join(OUT, 'frames.txt'), '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '20', video], { stdio: 'ignore' });
console.log(JSON.stringify({ video, frames: frames.length, status: job && job.status, design: job && job.design, check: job && job.check, seconds: Math.round((Date.now() - t0) / 1000) }));
ws.close();
browser.kill();
process.exit(0);
