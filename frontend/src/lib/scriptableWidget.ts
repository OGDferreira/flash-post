/**
 * The iPhone widget script for the Scriptable app. It reads /api/widget/today with a
 * read-only token (made when the user copies it in Configurações) and draws, in the logo's
 * blue gradient:
 * - medium and small (the SharkBot-style cards): FlashBot, sales pill, "Faturamento hoje",
 *   the day's total and the revenue-by-hour chart;
 * - large: revenue, profit, Pix generated/paid and a bigger chart;
 * - lock screen: logo, FlashBot, revenue and number of sales.
 * iOS widgets are still images the system refreshes on its own (it asks for 1 min; iOS
 * usually allows every 5-15 min), so a new sale shows as a green "+R$" badge, and tapping
 * the widget opens an animated view (chart drawing itself, numbers counting up).
 */
export function scriptableWidgetScript(baseUrl: string, token: string): string {
  const base = baseUrl.replace(/\/$/, "");
  return `// FlashBot — widget de vendas do FlashPost para o Scriptable
// Gerado em ${new Date().toLocaleDateString("pt-BR")}. Copiar o script de novo no site desliga este.
const API = ${JSON.stringify(`${base}/api/widget/today`)};
const TOKEN = ${JSON.stringify(token)};
const LOGO = ${JSON.stringify(`${base}/brand/icon-192.png`)};
const SITE = ${JSON.stringify(`${base}/feature/bots`)};

// the logo's colors
const BLUE = ["#3a5ffe", "#1e9cfd", "#15d6fe"];
const C = {
  text: Color.white(), soft: new Color("#ffffff", 0.78), faint: new Color("#ffffff", 0.55),
  pill: new Color("#ffffff", 0.2), green: new Color("#b6ffcf"), badge: new Color("#22c55e", 0.9),
};
const fm = FileManager.local();
const dir = fm.documentsDirectory();
const statePath = fm.joinPath(dir, "flashbot-widget-state.json");

function brl(value) {
  const [int, dec] = Math.abs(value).toFixed(2).split(".");
  return (value < 0 ? "-" : "") + "R$ " + int.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ".") + "," + dec;
}
function sales(n) { return n + (n === 1 ? " venda" : " vendas"); }

async function loadData() {
  const cache = fm.joinPath(dir, "flashbot-widget.json");
  try {
    const request = new Request(API);
    request.headers = { Authorization: "Bearer " + TOKEN };
    request.timeoutInterval = 20;
    const data = await request.loadJSON();
    if (request.response.statusCode !== 200) throw new Error(data.detail || "Não foi possível ler as vendas.");
    fm.writeString(cache, JSON.stringify(data));
    return data;
  } catch (error) {
    if (fm.fileExists(cache)) return Object.assign(JSON.parse(fm.readString(cache)), { offline: true });
    throw error;
  }
}

async function loadLogo() {
  const path = fm.joinPath(dir, "flashbot-logo-v2.png");
  if (fm.fileExists(path)) return fm.readImage(path);
  try {
    const image = await new Request(LOGO).loadImage();
    fm.writeImage(path, image);
    return image;
  } catch (error) {
    return null;
  }
}

// A sale since the last refresh: shown as a green "+R$" badge until the next one.
function newSales(data) {
  let last = null;
  try { last = fm.fileExists(statePath) ? JSON.parse(fm.readString(statePath)) : null; } catch (error) {}
  const day = new Date().toDateString();
  let delta = null;
  if (last && last.day === day && data.pix_paid > last.paid) {
    delta = { amount: data.revenue - last.revenue, count: data.pix_paid - last.paid, until: Date.now() + 15 * 60 * 1000 };
  } else if (last && last.day === day && last.delta && last.delta.until > Date.now()) {
    delta = last.delta;
  }
  fm.writeString(statePath, JSON.stringify({ day, paid: data.pix_paid, revenue: data.revenue, delta }));
  return delta;
}

function background(widget) {
  const gradient = new LinearGradient();
  gradient.colors = BLUE.map((c) => new Color(c));
  gradient.locations = [0, 0.55, 1];
  gradient.startPoint = new Point(0, 0);
  gradient.endPoint = new Point(1, 1);
  widget.backgroundGradient = gradient;
}

function header(stack, logo, size, pill) {
  const row = stack.addStack();
  row.centerAlignContent();
  if (logo) {
    const image = row.addImage(logo);
    image.imageSize = new Size(size, size);
    image.cornerRadius = size * 0.24;
    image.borderWidth = 1;
    image.borderColor = new Color("#ffffff", 0.35);
    row.addSpacer(6);
  }
  const name = row.addText("FlashBot");
  name.font = Font.boldSystemFont(size * 0.8);
  name.textColor = C.text;
  name.lineLimit = 1;
  name.minimumScaleFactor = 0.7;
  row.addSpacer();
  if (pill) {
    const tag = row.addStack();
    tag.backgroundColor = C.pill;
    tag.cornerRadius = 9;
    tag.setPadding(3, 8, 3, 8);
    const text = tag.addText(pill);
    text.font = Font.boldSystemFont(size * 0.58);
    text.textColor = C.text;
    text.lineLimit = 1;
  }
}

function label(stack, text, size) {
  const t = stack.addText(text.toUpperCase());
  t.font = Font.semiboldSystemFont(size);
  t.textColor = C.soft;
}

function value(stack, amount, size) {
  const v = stack.addText(brl(amount));
  v.font = Font.boldRoundedSystemFont(size);
  v.textColor = C.text;
  v.minimumScaleFactor = 0.45;
  v.lineLimit = 1;
}

function badge(stack, delta, size) {
  if (!delta) return;
  const b = stack.addStack();
  b.backgroundColor = C.badge;
  b.cornerRadius = 8;
  b.setPadding(2, 7, 2, 7);
  const t = b.addText("▲ +" + brl(delta.amount) + (delta.count > 1 ? " · " + delta.count + " novas" : " · nova venda"));
  t.font = Font.boldSystemFont(size);
  t.textColor = Color.white();
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.7;
}

// White line with a glow over a soft fill; the dot marks "now".
function chart(series, width, height) {
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;
  const points = series.length > 1 ? series : [0, series[0] || 0];
  const max = Math.max(...points, 1);
  const step = width / Math.max(points.length - 1, 1);
  const y = (v) => height - 4 - (v / max) * (height - 12);
  const line = new Path();
  line.move(new Point(0, y(points[0])));
  points.forEach((v, i) => line.addLine(new Point(i * step, y(v))));
  const area = new Path();
  area.move(new Point(0, height));
  points.forEach((v, i) => area.addLine(new Point(i * step, y(v))));
  area.addLine(new Point((points.length - 1) * step, height));
  area.closeSubpath();
  ctx.addPath(area);
  ctx.setFillColor(new Color("#ffffff", 0.16));
  ctx.fillPath();
  [[6, 0.15], [3.2, 0.3], [1.8, 1]].forEach(([w, a]) => {
    ctx.addPath(line);
    ctx.setStrokeColor(new Color("#ffffff", a));
    ctx.setLineWidth(w);
    ctx.strokePath();
  });
  const last = new Point((points.length - 1) * step, y(points[points.length - 1]));
  ctx.setFillColor(new Color("#ffffff", 0.35));
  ctx.fillEllipse(new Rect(last.x - 6, last.y - 6, 12, 12));
  ctx.setFillColor(Color.white());
  ctx.fillEllipse(new Rect(last.x - 2.5, last.y - 2.5, 5, 5));
  return ctx.getImage();
}

function footer(stack, data, size) {
  const row = stack.addStack();
  row.addSpacer();
  const t = row.addText(data.updated_at + (data.offline ? " · offline" : "") + " · FlashPost");
  t.font = Font.mediumSystemFont(size);
  t.textColor = C.faint;
}

function medium(data, logo, delta) {
  const w = new ListWidget();
  background(w);
  w.setPadding(14, 16, 10, 16);
  header(w, logo, 20, sales(data.pix_paid));
  w.addSpacer(8);
  const body = w.addStack();
  const left = body.addStack();
  left.layoutVertically();
  label(left, "Faturamento hoje", 11);
  left.addSpacer(2);
  value(left, data.revenue, 34);
  left.addSpacer(4);
  badge(left, delta, 10);
  body.addSpacer(10);
  const right = body.addStack();
  right.layoutVertically();
  right.addSpacer();
  const graph = right.addImage(chart(data.series || [0], 120, 56));
  graph.imageSize = new Size(120, 56);
  w.addSpacer();
  footer(w, data, 9);
  return w;
}

function small(data, logo, delta) {
  const w = new ListWidget();
  background(w);
  w.setPadding(12, 13, 9, 13);
  header(w, logo, 17, String(data.pix_paid));
  w.addSpacer(6);
  label(w, "Faturamento hoje", 9);
  w.addSpacer(1);
  value(w, data.revenue, 24);
  if (delta) {
    w.addSpacer(3);
    badge(w, delta, 8);
  } else {
    const count = w.addText(sales(data.pix_paid));
    count.font = Font.mediumSystemFont(10);
    count.textColor = C.soft;
  }
  w.addSpacer();
  const graph = w.addImage(chart(data.series || [0], 132, 30));
  graph.imageSize = new Size(132, 30);
  return w;
}

function large(data, logo, delta) {
  const w = new ListWidget();
  background(w);
  w.setPadding(16, 16, 12, 16);
  header(w, logo, 22, sales(data.pix_paid));
  w.addSpacer(10);
  label(w, "Faturamento hoje", 11);
  w.addSpacer(2);
  const row = w.addStack();
  row.bottomAlignContent();
  value(row, data.revenue, 34);
  row.addSpacer();
  const profit = row.addStack();
  profit.layoutVertically();
  label(profit, "Lucro", 10);
  const p = profit.addText(brl(data.profit));
  p.font = Font.boldRoundedSystemFont(18);
  p.textColor = C.green;
  w.addSpacer(4);
  badge(w, delta, 11);
  w.addSpacer(8);
  const pix = w.addStack();
  pix.backgroundColor = C.pill;
  pix.cornerRadius = 10;
  pix.setPadding(6, 10, 6, 10);
  const conversion = data.pix_generated ? Math.round((100 * data.pix_paid) / data.pix_generated) : 0;
  const pixText = pix.addText(data.pix_generated + " pix gerados  ·  " + data.pix_paid + " pagos  ·  " + conversion + "% conversão");
  pixText.font = Font.semiboldSystemFont(12);
  pixText.textColor = C.text;
  w.addSpacer(8);
  const graph = w.addImage(chart(data.series || [0], 306, 120));
  graph.imageSize = new Size(306, 120);
  w.addSpacer();
  footer(w, data, 10);
  return w;
}

// Lock screen: logo, FlashBot, revenue and sales (iOS draws it in one tone).
function lockScreen(data, logo, family) {
  const w = new ListWidget();
  if (family === "accessoryInline") {
    w.addText("FlashBot " + brl(data.revenue) + " · " + sales(data.pix_paid));
    return w;
  }
  if (family === "accessoryCircular") {
    w.addSpacer();
    const n = w.addText(String(data.pix_paid));
    n.font = Font.boldRoundedSystemFont(20);
    n.centerAlignText();
    const t = w.addText("vendas");
    t.font = Font.mediumSystemFont(9);
    t.centerAlignText();
    w.addSpacer();
    return w;
  }
  const top = w.addStack();
  top.centerAlignContent();
  if (logo) {
    const image = top.addImage(logo);
    image.imageSize = new Size(14, 14);
    image.cornerRadius = 3;
    top.addSpacer(4);
  }
  const name = top.addText("FlashBot");
  name.font = Font.boldSystemFont(12);
  const amount = w.addText(brl(data.revenue));
  amount.font = Font.boldRoundedSystemFont(20);
  amount.minimumScaleFactor = 0.6;
  amount.lineLimit = 1;
  const count = w.addText(sales(data.pix_paid));
  count.font = Font.mediumSystemFont(11);
  return w;
}

function failure(message) {
  const w = new ListWidget();
  background(w);
  const title = w.addText("FlashBot");
  title.font = Font.boldSystemFont(15);
  title.textColor = C.text;
  w.addSpacer(6);
  const text = w.addText(message);
  text.font = Font.systemFont(12);
  text.textColor = C.soft;
  return w;
}

// Opened from the widget (or run in the app): the chart draws itself and the numbers count up.
async function animatedView(data) {
  const series = data.series && data.series.length > 1 ? data.series : [0, data.revenue];
  const max = Math.max(...series, 1);
  const pts = series.map((v, i) => [(i / (series.length - 1)) * 320, 150 - (v / max) * 130]);
  const d = "M" + pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  const conversion = data.pix_generated ? Math.round((100 * data.pix_paid) / data.pix_generated) : 0;
  const html = \`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;min-height:100vh;font-family:-apple-system,system-ui;color:#fff;background:linear-gradient(135deg,\${BLUE[0]},\${BLUE[1]} 55%,\${BLUE[2]});display:flex;flex-direction:column;gap:18px;padding:28px 22px;box-sizing:border-box}
.top{display:flex;align-items:center;gap:10px;font-weight:700;font-size:22px}.top img{width:34px;height:34px;border-radius:9px;border:1px solid rgba(255,255,255,.4)}
.pill{margin-left:auto;background:rgba(255,255,255,.2);border-radius:99px;padding:5px 12px;font-size:14px}
.lbl{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;font-weight:600}
.big{font-size:46px;font-weight:800;letter-spacing:-.02em}.row{display:flex;gap:12px}
.card{flex:1;background:rgba(255,255,255,.16);border-radius:16px;padding:12px 14px}.card b{display:block;font-size:22px;margin-top:4px}
svg{width:100%;height:auto;overflow:visible}.line{fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 6px rgba(255,255,255,.7));stroke-dasharray:2000;stroke-dashoffset:2000;animation:draw 1.6s .2s ease-out forwards}
.area{fill:rgba(255,255,255,.16);opacity:0;animation:fade .8s 1.2s forwards}.dot{fill:#fff;opacity:0;animation:pulse 1.4s 1.6s ease-in-out infinite}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes fade{to{opacity:1}}@keyframes pulse{0%,100%{opacity:1;r:5}50%{opacity:.5;r:9}}
a{color:#fff;text-align:center;background:rgba(0,0,0,.18);border-radius:14px;padding:13px;text-decoration:none;font-weight:600}
</style></head><body>
<div class="top"><img src="\${LOGO}">FlashBot<span class="pill">\${sales(data.pix_paid)}</span></div>
<div><div class="lbl">Faturamento hoje</div><div class="big" data-to="\${data.revenue}">R$ 0,00</div></div>
<div class="row"><div class="card"><div class="lbl">Lucro</div><b data-to="\${data.profit}">R$ 0,00</b></div>
<div class="card"><div class="lbl">Pix</div><b>\${data.pix_generated} gerados</b><span style="opacity:.8">\${data.pix_paid} pagos · \${conversion}%</span></div></div>
<svg viewBox="0 0 320 160"><path class="area" d="\${d} L320,160 L0,160 Z"/><path class="line" d="\${d}"/><circle class="dot" cx="\${pts[pts.length-1][0]}" cy="\${pts[pts.length-1][1]}" r="5"/></svg>
<div class="lbl" style="text-align:right">atualizado \${data.updated_at}</div>
<a href="\${SITE}">Abrir o FlashBot</a>
<script>
const fmt=v=>"R$ "+v.toFixed(2).replace(".",",").replace(/\\\\B(?=(\\\\d{3})+(?!\\\\d))/g,".");
document.querySelectorAll("[data-to]").forEach(el=>{const to=+el.dataset.to,t0=performance.now();
(function tick(t){const k=Math.min(1,(t-t0)/1400),e=1-Math.pow(1-k,3);el.textContent=fmt(to*e);if(k<1)requestAnimationFrame(tick)})(t0)});
</script></body></html>\`;
  const view = new WebView();
  await view.loadHTML(html);
  await view.present(true);
}

const family = config.widgetFamily || "medium";
let widget;
let data = null;
try {
  const [loaded, logo] = await Promise.all([loadData(), loadLogo()]);
  data = loaded;
  const delta = newSales(data);
  if (family.startsWith("accessory")) widget = lockScreen(data, logo, family);
  else if (family === "small") widget = small(data, logo, delta);
  else if (family === "large" || family === "extraLarge") widget = large(data, logo, delta);
  else widget = medium(data, logo, delta);
} catch (error) {
  widget = failure(String(error.message || error));
}
// asks iOS to refresh every minute (iOS decides the real pace, usually 5-15 min)
widget.refreshAfterDate = new Date(Date.now() + 60 * 1000);
// tapping the widget runs this script in the app: the animated view
widget.url = URLScheme.forRunningScript();
if (config.runsInWidget) Script.setWidget(widget);
else if (data) await animatedView(data);
else await widget.presentMedium();
Script.complete();
`;
}
