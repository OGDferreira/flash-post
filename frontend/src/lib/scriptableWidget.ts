/**
 * The iPhone widget script for the Scriptable app. It reads /api/widget/today with a
 * read-only token (made when the user copies it in Configurações) and draws, in the logo's
 * blue gradient:
 * - medium and small (the SharkBot-style cards): Flash, sales pill, "Faturamento hoje",
 *   the day's total and the revenue-by-hour chart;
 * - large: revenue, profit, Pix generated/paid and a bigger chart;
 * - lock screen: logo, Flash, revenue and number of sales.
 * iOS widgets are still images the system refreshes on its own (it asks for 1 min; iOS
 * usually allows every 5-15 min), so a new sale shows as a green "+R$" badge, and tapping
 * the widget opens an animated view (chart drawing itself, numbers counting up).
 */
export type WidgetTheme = "azul" | "dark" | "white";

export function scriptableWidgetScript(baseUrl: string, token: string, theme: WidgetTheme = "azul"): string {
  const base = baseUrl.replace(/\/$/, "");
  return `// Flash — widget de vendas do Flash para o Scriptable
// Gerado em ${new Date().toLocaleDateString("pt-BR")}. Copiar o script de novo no site desliga este.
const API = ${JSON.stringify(`${base}/api/widget/today`)};
const TOKEN = ${JSON.stringify(token)};
const LOGO = ${JSON.stringify(`${base}/brand/flash-icon-192.png`)};
const SITE = ${JSON.stringify(`${base}/bot`)};

// Three looks in the Flash colors (azul-ciano). Pick one per widget in its "Parameter"
// field (dark, white or azul); empty = the one chosen when the script was copied. "comm" is the
// commission tone (purple) used on the Super Admin's commission line and dotted chart.
const THEMES = {
  azul: { bg: ["#1e9cfd", "#1577c9", "#0e5fa8"], text: "#ffffff", soft: ["#ffffff", 0.82], faint: ["#ffffff", 0.62],
          pill: ["#ffffff", 0.2], line: "#ffffff", fill: 0.16, profit: "#b6ffcf", rate: "#ffffff", comm: "#dcc4ff" },
  dark: { bg: ["#12141c", "#191d2e", "#20264a"], text: "#ffffff", soft: ["#aab4d4", 1], faint: ["#6b7699", 1],
          pill: ["#1e9cfd", 0.24], line: "#4fb6fe", fill: 0.2, profit: "#22c55e", rate: "#6ec9ff", comm: "#b171ff" },
  white: { bg: ["#ffffff", "#f2f5ff", "#e7edff"], text: "#0b1530", soft: ["#495271", 1], faint: ["#8a93b4", 1],
           pill: ["#1e9cfd", 0.12], line: "#0b74c4", fill: 0.14, profit: "#16a34a", rate: "#1e9cfd", comm: "#8b3fd6" },
};
const PICK = String(args.widgetParameter || ${JSON.stringify(theme)}).trim().toLowerCase();
const T = THEMES[PICK === "branco" ? "white" : PICK === "escuro" ? "dark" : PICK] || THEMES.azul;
const BLUE = T.bg;
const C = {
  text: new Color(T.text), soft: new Color(...T.soft), faint: new Color(...T.faint),
  pill: new Color(...T.pill), green: new Color(T.profit), rate: new Color(T.rate), badge: new Color("#22c55e", 0.92),
  comm: new Color(T.comm),
};
function rgba(hex, alpha = 1) {
  const n = parseInt(hex.slice(1), 16);
  return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
}
function rate(data) { return data.pix_generated ? Math.round((100 * data.pix_paid) / data.pix_generated) : 0; }
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
  const path = fm.joinPath(dir, "flashbot-logo-v3.png");
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
    image.borderColor = new Color(T.text, 0.25);
    row.addSpacer(6);
  }
  const name = row.addText("Flash");
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

// "45% conversão · 31 pix": paid over generated Pix today
function conversion(stack, data, size) {
  const row = stack.addStack();
  row.centerAlignContent();
  const pct = row.addText(rate(data) + "%");
  pct.font = Font.boldRoundedSystemFont(size + 1);
  pct.textColor = C.rate;
  row.addSpacer(4);
  const rest = row.addText("conversão · " + data.pix_generated + " pix");
  rest.font = Font.mediumSystemFont(size);
  rest.textColor = C.soft;
  rest.lineLimit = 1;
  rest.minimumScaleFactor = 0.7;
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
// Draw a dashed polyline (Scriptable has no native line dash), used for the commission chart.
function dashed(ctx, pts, color, width) {
  const dash = 5, gap = 4;
  let on = true, remain = dash;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 0.0001;
    const ux = dx / len, uy = dy / len;
    let pos = 0;
    while (pos < len) {
      const seg = Math.min(remain, len - pos);
      if (on) {
        const p = new Path();
        p.move(new Point(a.x + ux * pos, a.y + uy * pos));
        p.addLine(new Point(a.x + ux * (pos + seg), a.y + uy * (pos + seg)));
        ctx.addPath(p);
        ctx.setStrokeColor(color);
        ctx.setLineWidth(width);
        ctx.strokePath();
      }
      pos += seg; remain -= seg;
      if (remain <= 0.001) { on = !on; remain = on ? dash : gap; }
    }
  }
}

function chart(series, width, height, opts) {
  opts = opts || {};
  const hex = opts.color || T.line;
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;
  const points = series.length > 1 ? series : [0, series[0] || 0];
  const max = Math.max(...points, 1);
  const step = width / Math.max(points.length - 1, 1);
  const y = (v) => height - 4 - (v / max) * (height - 12);
  const pts = points.map((v, i) => new Point(i * step, y(v)));
  if (opts.dotted) {
    // Commission chart: just a dashed line and the end dot, no filled area.
    dashed(ctx, pts, new Color(hex, 0.95), 1.8);
  } else {
    const line = new Path();
    line.move(pts[0]);
    pts.forEach((p) => line.addLine(p));
    const area = new Path();
    area.move(new Point(0, height));
    pts.forEach((p) => area.addLine(p));
    area.addLine(new Point((points.length - 1) * step, height));
    area.closeSubpath();
    ctx.addPath(area);
    ctx.setFillColor(new Color(hex, T.fill));
    ctx.fillPath();
    [[6, 0.15], [3.2, 0.3], [1.8, 1]].forEach(([w, a]) => {
      ctx.addPath(line);
      ctx.setStrokeColor(new Color(hex, a));
      ctx.setLineWidth(w);
      ctx.strokePath();
    });
  }
  const last = pts[pts.length - 1];
  ctx.setFillColor(new Color(hex, 0.35));
  ctx.fillEllipse(new Rect(last.x - 6, last.y - 6, 12, 12));
  ctx.setFillColor(new Color(hex));
  ctx.fillEllipse(new Rect(last.x - 2.5, last.y - 2.5, 5, 5));
  return ctx.getImage();
}

// Super Admin line: "+R$x em comissões · total R$y", shown below the sales.
function commissionLine(stack, data, size) {
  if (!data.is_admin) return;
  const total = (data.revenue || 0) + (data.commissions || 0);
  const row = stack.addStack();
  row.centerAlignContent();
  const plus = row.addText("+" + brl(data.commissions || 0) + " em comissões");
  plus.font = Font.semiboldSystemFont(size);
  plus.textColor = C.comm;
  const rest = row.addText(" · total " + brl(total));
  rest.font = Font.mediumSystemFont(size);
  rest.textColor = C.soft;
}

function footer(stack, data, size) {
  const row = stack.addStack();
  row.addSpacer();
  const t = row.addText(data.updated_at + (data.offline ? " · offline" : "") + " · Flash");
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
  left.addSpacer(3);
  conversion(left, data, 11);
  left.addSpacer(4);
  badge(left, delta, 10);
  if (data.is_admin) { left.addSpacer(4); commissionLine(left, data, 10); }
  body.addSpacer(10);
  const right = body.addStack();
  right.layoutVertically();
  right.addSpacer();
  if (data.is_admin) {
    // Revenue chart plus the dotted commission chart below it.
    const g1 = right.addImage(chart(data.series || [0], 120, 34));
    g1.imageSize = new Size(120, 34);
    right.addSpacer(3);
    const g2 = right.addImage(chart(data.commission_series || [0], 120, 22, { dotted: true, color: T.comm }));
    g2.imageSize = new Size(120, 22);
  } else {
    const graph = right.addImage(chart(data.series || [0], 120, 56));
    graph.imageSize = new Size(120, 56);
  }
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
  w.addSpacer(2);
  if (delta) badge(w, delta, 8);
  else conversion(w, data, 10);
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
  if (data.is_admin) { w.addSpacer(6); commissionLine(w, data, 12); }
  w.addSpacer(8);
  const pix = w.addStack();
  pix.backgroundColor = C.pill;
  pix.cornerRadius = 10;
  pix.setPadding(6, 10, 6, 10);
  const pixText = pix.addText(data.pix_generated + " pix gerados  ·  " + data.pix_paid + " pagos  ·  " + rate(data) + "% conversão");
  pixText.font = Font.semiboldSystemFont(12);
  pixText.textColor = C.text;
  w.addSpacer(8);
  if (data.is_admin) {
    const graph = w.addImage(chart(data.series || [0], 306, 86));
    graph.imageSize = new Size(306, 86);
    w.addSpacer(4);
    const crow = w.addStack();
    crow.centerAlignContent();
    const tag = crow.addText("comissões");
    tag.font = Font.mediumSystemFont(9);
    tag.textColor = C.comm;
    crow.addSpacer();
    const cg = w.addImage(chart(data.commission_series || [0], 306, 30, { dotted: true, color: T.comm }));
    cg.imageSize = new Size(306, 30);
  } else {
    const graph = w.addImage(chart(data.series || [0], 306, 120));
    graph.imageSize = new Size(306, 120);
  }
  w.addSpacer();
  footer(w, data, 10);
  return w;
}

// Lock screen: logo, Flash, revenue and sales (iOS draws it in one tone).
function lockScreen(data, logo, family) {
  const w = new ListWidget();
  if (family === "accessoryInline") {
    w.addText("Flash " + brl(data.revenue) + " · " + sales(data.pix_paid));
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
  const name = top.addText("Flash");
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
  const title = w.addText("Flash");
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
  const conversion = rate(data);
  const html = \`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;min-height:100vh;font-family:-apple-system,system-ui;color:\${T.text};background:linear-gradient(135deg,\${BLUE[0]},\${BLUE[1]} 55%,\${BLUE[2]});display:flex;flex-direction:column;gap:18px;padding:28px 22px;box-sizing:border-box}
.top{display:flex;align-items:center;gap:10px;font-weight:700;font-size:22px}.top img{width:34px;height:34px;border-radius:9px;border:1px solid \${rgba(T.text, 0.3)}}
.pill{margin-left:auto;background:\${rgba(...T.pill)};border-radius:99px;padding:5px 12px;font-size:14px}
.lbl{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;font-weight:600}
.big{font-size:46px;font-weight:800;letter-spacing:-.02em}.row{display:flex;gap:12px}
.card{flex:1;background:\${rgba(...T.pill)};border-radius:16px;padding:12px 14px}.card b{display:block;font-size:22px;margin-top:4px}
svg{width:100%;height:auto;overflow:visible}.line{fill:none;stroke:\${T.line};stroke-width:3;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 6px \${rgba(T.line, 0.7)});stroke-dasharray:2000;stroke-dashoffset:2000;animation:draw 1.6s .2s ease-out forwards}
.area{fill:\${rgba(T.line, T.fill)};opacity:0;animation:fade .8s 1.2s forwards}.dot{fill:\${T.line};opacity:0;animation:pulse 1.4s 1.6s ease-in-out infinite}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes fade{to{opacity:1}}@keyframes pulse{0%,100%{opacity:1;r:5}50%{opacity:.5;r:9}}
a{color:#fff;text-align:center;background:\${T.line === "#ffffff" ? "rgba(0,0,0,.18)" : T.line};border-radius:14px;padding:13px;text-decoration:none;font-weight:600}
</style></head><body>
<div class="top"><img src="\${LOGO}">Flash<span class="pill">\${sales(data.pix_paid)}</span></div>
<div><div class="lbl">Faturamento hoje</div><div class="big" data-to="\${data.revenue}">R$ 0,00</div></div>
<div class="row"><div class="card"><div class="lbl">Lucro</div><b data-to="\${data.profit}">R$ 0,00</b></div>
<div class="card"><div class="lbl">Pix</div><b>\${data.pix_generated} gerados</b><span style="opacity:.8">\${data.pix_paid} pagos · \${conversion}%</span></div></div>
<svg viewBox="0 0 320 160"><path class="area" d="\${d} L320,160 L0,160 Z"/><path class="line" d="\${d}"/><circle class="dot" cx="\${pts[pts.length-1][0]}" cy="\${pts[pts.length-1][1]}" r="5"/></svg>
<div class="lbl" style="text-align:right">atualizado \${data.updated_at}</div>
<a href="\${SITE}">Abrir o Flash</a>
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
