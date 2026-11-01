/**
 * The iPhone widget script for the Scriptable app. It reads /api/widget/today with a
 * read-only token (made when the user copies it in Configurações) and draws:
 * - the day's TOTAL in evidence, then one line each for sales (Flash + SharkBot webhook),
 *   commission and Flash fees (the last two for the Super Admin only);
 * - Pix conversion (generated → paid), the Flash Post views of the day (eye icon), the chart;
 * - seven looks (claro, escuro, preto e branco, roxo, galáxia, rosa, flores) with the big Flash mark
 *   faded in the background.
 * iOS widgets are still images the system refreshes on its own (it asks for 1 min; iOS
 * usually allows every 5-15 min), so a new sale shows as a green "+R$" badge, and tapping
 * the widget opens an animated view (chart drawing itself, numbers counting up).
 */
export type WidgetTheme = "claro" | "escuro" | "pb" | "roxo" | "galaxia" | "rosa" | "flores";

export const WIDGET_THEME_IDS: WidgetTheme[] = ["claro", "escuro", "pb", "roxo", "galaxia", "rosa", "flores"];

export function scriptableWidgetScript(baseUrl: string, token: string, theme: WidgetTheme = "roxo"): string {
  const base = baseUrl.replace(/\/$/, "");
  return `// Flash — widget de vendas do Flash para o Scriptable
// Gerado em ${new Date().toLocaleDateString("pt-BR")}. Copiar o script de novo no site desliga este.
const API = ${JSON.stringify(`${base}/api/widget/today`)};
const TOKEN = ${JSON.stringify(token)};
const THEME_API = ${JSON.stringify(`${base}/api/widget/theme/phone`)};
const LOGO = ${JSON.stringify(`${base}/brand/flash-icon-bot-192.png`)};
const MARKS = {
  white: ${JSON.stringify(`${base}/brand/flash-mark-white-512.png`)},
  purple: ${JSON.stringify(`${base}/brand/flash-mark-purple-512.png`)},
  pink: ${JSON.stringify(`${base}/brand/flash-mark-pink-512.png`)},
};
const SITE = ${JSON.stringify(`${base}/bot`)};

// Seven looks. Pick one per widget in its "Parameter" field (claro, escuro, pb, roxo, galaxia,
// rosa or flores); empty = the one chosen when the script was copied. "comm" colors the commission
// line, "fee" the Flash fees line; "mark" is the big logo faded in the background.
const THEMES = {
  claro: { bg: ["#ffffff", "#f6f0ff", "#ece2ff"], text: "#17082e", soft: ["#574b71", 1], faint: ["#938ab4", 1],
           pill: ["#8f1dff", 0.12], line: "#7412d1", fill: 0.14, profit: "#16a34a", rate: "#8f1dff", comm: "#8b3fd6",
           mark: "purple", markAlpha: 0.1 },
  escuro: { bg: ["#0e0f16", "#161322", "#211836"], text: "#ffffff", soft: ["#b7a6d4", 1], faint: ["#7a6b99", 1],
            pill: ["#8f1dff", 0.28], line: "#a64bff", fill: 0.2, profit: "#22c55e", rate: "#d19bff", comm: "#d6a0ff",
            mark: "white", markAlpha: 0.07 },
  pb: { bg: ["#000000", "#0b0b0b", "#1a1a1a"], text: "#ffffff", soft: ["#d4d4d4", 1], faint: ["#8a8a8a", 1],
        pill: ["#ffffff", 0.16], line: "#ffffff", fill: 0.14, profit: "#ffffff", rate: "#ffffff", comm: "#bdbdbd",
        mark: "white", markAlpha: 0.08 },
  roxo: { bg: ["#8f1dff", "#7a00ff", "#5b00c4"], text: "#ffffff", soft: ["#ffffff", 0.82], faint: ["#ffffff", 0.62],
          pill: ["#ffffff", 0.2], line: "#ffffff", fill: 0.16, profit: "#b6ffcf", rate: "#ffffff", comm: "#f0d4ff",
          mark: "white", markAlpha: 0.12 },
  galaxia: { bg: ["#05041a", "#1d0b4a", "#4a1592"], text: "#ffffff", soft: ["#c9b8ff", 1], faint: ["#8c7bc4", 1],
             pill: ["#b06bff", 0.26], line: "#c48bff", fill: 0.2, profit: "#5ef0b0", rate: "#e0c4ff", comm: "#ff9ee8",
             mark: "white", markAlpha: 0.09, stars: true },
  rosa: { bg: ["#ff5fb0", "#ec2a8a", "#b0136a"], text: "#ffffff", soft: ["#ffffff", 0.85], faint: ["#ffffff", 0.65],
          pill: ["#ffffff", 0.22], line: "#ffffff", fill: 0.18, profit: "#d9ffe8", rate: "#ffffff", comm: "#ffe0f1",
          mark: "white", markAlpha: 0.13 },
  // Delicate: pastel pink with little flowers drawn in the background.
  flores: { bg: ["#fff7fa", "#ffe6f0", "#ffd3e4"], text: "#5a1236", soft: ["#8d3d62", 1], faint: ["#c27f9e", 1],
            pill: ["#ff6fa8", 0.18], line: "#e8559a", fill: 0.18, profit: "#2f9e6e", rate: "#e0408a", comm: "#b04ad6",
            mark: "pink", markAlpha: 0.1, flowers: true },
};
const ALIASES = { azul: "roxo", purple: "roxo", dark: "escuro", white: "claro", branco: "claro", light: "claro",
  preto: "pb", "preto e branco": "pb", mono: "pb", "galáxia": "galaxia", galaxy: "galaxia", pink: "rosa",
  flor: "flores", floral: "flores", flowers: "flores", feminino: "flores", delicado: "flores" };
const fm = FileManager.local();
const dir = fm.documentsDirectory();
const themePath = fm.joinPath(dir, "flash-widget-theme.txt");
function themeOf(name) {
  const key = String(name || "").trim().toLowerCase();
  const id = ALIASES[key] || key;
  return THEMES[id] ? id : null;
}
// The look: a name typed in the widget's Parameter field (optional) wins; otherwise the
// one picked with a tap (on the site or on the phone), which comes with the numbers.
const PARAM = themeOf(args.widgetParameter);
let saved = null;
try { saved = fm.fileExists(themePath) ? themeOf(fm.readString(themePath)) : null; } catch (error) {}
let THEME, T, BLUE, C;
function useTheme(name) {
  THEME = name;
  T = THEMES[name];
  BLUE = T.bg;
  C = {
    text: new Color(T.text), soft: new Color(...T.soft), faint: new Color(...T.faint),
    pill: new Color(...T.pill), green: new Color(T.profit), rate: new Color(T.rate), badge: new Color("#22c55e", 0.92),
    comm: new Color(T.comm),
  };
}
function rememberTheme(name) {
  try { fm.writeString(themePath, name); } catch (error) {}
}
useTheme(PARAM || saved || themeOf(${JSON.stringify(theme)}) || "roxo");
function rgba(hex, alpha = 1) {
  const n = parseInt(hex.slice(1), 16);
  return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
}
function rate(data) { return data.pix_generated ? Math.round((100 * data.pix_paid) / data.pix_generated) : 0; }
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

async function loadImage(url, name) {
  const path = fm.joinPath(dir, name);
  if (fm.fileExists(path)) return fm.readImage(path);
  try {
    const image = await new Request(url).loadImage();
    fm.writeImage(path, image);
    return image;
  } catch (error) {
    return null;
  }
}
function loadLogo() { return loadImage(LOGO, "flash-logo-v4.png"); }
function loadMark() { return loadImage(MARKS[T.mark], "flash-mark-" + T.mark + "-v1.png"); }

// Older servers send only "revenue": fall back to it.
function total(data) { return data.total != null ? data.total : data.revenue || 0; }
function salesValue(data) { return data.sales != null ? data.sales : data.revenue || 0; }
function salesCount(data) { return data.sales_count != null ? data.sales_count : data.pix_paid; }
function viewsText(n) {
  n = n || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(".", ",") + " mi";
  return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ".");
}

// A sale since the last refresh: shown as a green "+R$" badge until the next one.
function newSales(data) {
  let last = null;
  try { last = fm.fileExists(statePath) ? JSON.parse(fm.readString(statePath)) : null; } catch (error) {}
  const day = new Date().toDateString();
  let delta = null;
  const count = salesCount(data), amount = salesValue(data);
  if (last && last.day === day && count > last.paid) {
    delta = { amount: amount - last.revenue, count: count - last.paid, until: Date.now() + 15 * 60 * 1000 };
  } else if (last && last.day === day && last.delta && last.delta.until > Date.now()) {
    delta = last.delta;
  }
  fm.writeString(statePath, JSON.stringify({ day, paid: count, revenue: amount, delta }));
  return delta;
}

// Point sizes of each widget family, for the background picture.
const SIZES = { small: [158, 158], medium: [338, 158], large: [338, 354], extraLarge: [715, 354] };
function hexRgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function toHex(rgb) { return "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join(""); }
function gradientAt(k) {
  const i = k < 0.55 ? 0 : 1;
  const t = i === 0 ? k / 0.55 : (k - 0.55) / 0.45;
  const a = hexRgb(T.bg[i]), b = hexRgb(T.bg[i + 1]);
  return toHex([0, 1, 2].map((j) => a[j] + (b[j] - a[j]) * t));
}
function paint(ctx, w, h, alpha) {
  const bands = 64;
  for (let i = 0; i < bands; i++) {
    const y0 = Math.floor((i * h) / bands), y1 = Math.floor(((i + 1) * h) / bands);
    ctx.setFillColor(new Color(gradientAt(i / (bands - 1)), alpha));
    ctx.fillRect(new Rect(0, y0, w, y1 - y0));
  }
}
// The theme's gradient with the big Flash mark faded in (a second, almost opaque coat of the
// gradient over the mark leaves it at low opacity); galáxia gets its stars on top.
function backgroundImage(family, mark) {
  const size = SIZES[family] || SIZES.medium;
  const w = size[0], h = size[1];
  const ctx = new DrawContext();
  ctx.size = new Size(w, h);
  ctx.opaque = true;
  ctx.respectScreenScale = true;
  paint(ctx, w, h, 1);
  if (mark) {
    const m = Math.min(h * 1.3, w * 0.95);
    ctx.drawImageInRect(mark, new Rect(w - m * 0.78, (h - m) / 2 + h * 0.05, m, m));
    paint(ctx, w, h, 1 - T.markAlpha);
  }
  if (T.stars) {
    let seed = 11;
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < Math.round((w * h) / 700); i++) {
      const r = rnd() * 1.4 + 0.4;
      ctx.setFillColor(new Color("#ffffff", 0.2 + rnd() * 0.65));
      ctx.fillEllipse(new Rect(rnd() * w, rnd() * h, r, r));
    }
  }
  if (T.flowers) drawFlowers(ctx, w, h);
  return ctx.getImage();
}
// Five round petals around a little golden center; leaves and pollen dots around them.
function flower(ctx, x, y, r, petal, alpha) {
  for (let i = 0; i < 5; i++) {
    const a = (i / 5) * Math.PI * 2 - Math.PI / 2;
    const px = x + Math.cos(a) * r * 0.55, py = y + Math.sin(a) * r * 0.55, pr = r * 0.52;
    ctx.setFillColor(new Color(petal, alpha));
    ctx.fillEllipse(new Rect(px - pr, py - pr, pr * 2, pr * 2));
  }
  ctx.setFillColor(new Color("#ffffff", alpha * 0.7));
  ctx.fillEllipse(new Rect(x - r * 0.3, y - r * 0.3, r * 0.6, r * 0.6));
  ctx.setFillColor(new Color("#f7c96b", Math.min(1, alpha + 0.2)));
  ctx.fillEllipse(new Rect(x - r * 0.2, y - r * 0.2, r * 0.4, r * 0.4));
}
function leaf(ctx, x, y, s, alpha) {
  ctx.setFillColor(new Color("#8fcf9f", alpha));
  ctx.fillEllipse(new Rect(x - s, y - s * 0.4, s * 2, s * 0.8));
}
function drawFlowers(ctx, w, h) {
  // Kept to the edges and corners, so the numbers stay easy to read.
  const k = Math.min(w, h) / 158;
  const spots = [
    [w - 14 * k, 12 * k, 20, "#ff8fbf", 0.55], [w - 46 * k, 30 * k, 11, "#ffb3d1", 0.6],
    [w - 30 * k, h - 14 * k, 24, "#ff7fb4", 0.5], [w - 72 * k, h - 6 * k, 12, "#ffc2da", 0.65],
    [10 * k, h - 10 * k, 16, "#ff9cc6", 0.45], [w * 0.5, h - 4 * k, 8, "#ffb3d1", 0.5],
    [w * 0.62, 8 * k, 7, "#ffc2da", 0.55],
  ];
  if (h > 250) spots.push([12 * k, h * 0.55, 13, "#ffb3d1", 0.45], [w - 10 * k, h * 0.5, 15, "#ff9cc6", 0.45]);
  spots.forEach(([x, y, r, color, alpha]) => {
    leaf(ctx, x - r * k * 0.95, y + r * k * 0.55, r * k * 0.45, 0.35);
    leaf(ctx, x + r * k * 0.95, y + r * k * 0.5, r * k * 0.4, 0.3);
    flower(ctx, x, y, r * k, color, alpha);
  });
  let seed = 23;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < Math.round((w * h) / 1400); i++) {
    const d = rnd() * 2 + 1;
    ctx.setFillColor(new Color(rnd() > 0.5 ? "#ff8fbf" : "#f7c96b", 0.25 + rnd() * 0.35));
    ctx.fillEllipse(new Rect(rnd() * w, rnd() * h, d, d));
  }
}
function background(widget, family, mark) {
  if (family) {
    widget.backgroundImage = backgroundImage(family, mark);
    return;
  }
  const gradient = new LinearGradient();
  gradient.colors = BLUE.map((c) => new Color(c));
  gradient.locations = [0, 0.55, 1];
  gradient.startPoint = new Point(0, 0);
  gradient.endPoint = new Point(1, 1);
  widget.backgroundGradient = gradient;
}

// Eye icon + the Flash Post views of the day.
function eye(stack, data, size) {
  if (data.views == null) return;
  const box = stack.addStack();
  box.centerAlignContent();
  const icon = box.addImage(SFSymbol.named("eye.fill").image);
  icon.imageSize = new Size(size, size);
  icon.tintColor = C.soft;
  box.addSpacer(3);
  const t = box.addText(viewsText(data.views));
  t.font = Font.semiboldSystemFont(size * 0.85);
  t.textColor = C.soft;
  t.lineLimit = 1;
}

function header(stack, logo, size, pill, data) {
  const row = stack.addStack();
  row.centerAlignContent();
  if (logo) {
    const image = row.addImage(logo);
    image.imageSize = new Size(size, size);
    image.cornerRadius = size * 0.24;
    row.addSpacer(6);
  }
  const name = row.addText("Flash");
  name.font = Font.boldSystemFont(size * 0.8);
  name.textColor = C.text;
  name.lineLimit = 1;
  name.minimumScaleFactor = 0.7;
  row.addSpacer();
  if (data) {
    eye(row, data, size * 0.62);
    row.addSpacer(8);
  }
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

// "22% conversão" and "51 pix → 11 pagos": paid over generated Pix today.
function conversionBlock(stack, data, size) {
  const row = stack.addStack();
  row.centerAlignContent();
  const pct = row.addText(rate(data) + "%");
  pct.font = Font.boldRoundedSystemFont(size + 6);
  pct.textColor = C.rate;
  row.addSpacer(4);
  const word = row.addText("conversão");
  word.font = Font.mediumSystemFont(size);
  word.textColor = C.soft;
  const detail = stack.addText(data.pix_generated + " pix → " + data.pix_paid + " pagos");
  detail.font = Font.mediumSystemFont(size - 1);
  detail.textColor = C.faint;
  detail.lineLimit = 1;
  detail.minimumScaleFactor = 0.7;
}

// "● R$ X em vendas" (+ commission and fees for the Super Admin); the amount in bold.
function amountLine(stack, amount, text, color, size) {
  const row = stack.addStack();
  row.centerAlignContent();
  const dot = row.addText("●");
  dot.font = Font.systemFont(size * 0.7);
  dot.textColor = color;
  row.addSpacer(4);
  const v = row.addText(brl(amount));
  v.font = Font.boldRoundedSystemFont(size);
  v.textColor = C.text;
  v.lineLimit = 1;
  v.minimumScaleFactor = 0.6;
  row.addSpacer(4);
  const t = row.addText(text);
  t.font = Font.mediumSystemFont(size * 0.88);
  t.textColor = C.soft;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.6;
}
function breakdown(stack, data, size, gap, sharkNote) {
  amountLine(stack, salesValue(data), "em vendas", C.rate, size);
  if (data.is_admin) {
    stack.addSpacer(gap);
    amountLine(stack, data.commissions || 0, "em comissão", C.comm, size);
    stack.addSpacer(gap);
    amountLine(stack, data.fees || 0, "em arrecadação", C.green, size);
  }
  if (sharkNote && data.shark_sales) {
    stack.addSpacer(gap);
    const t = stack.addText("inclui " + brl(data.shark_revenue || 0) + " da Shark (" + sales(data.shark_sales) + ")");
    t.font = Font.mediumSystemFont(size * 0.78);
    t.textColor = C.faint;
    t.lineLimit = 1;
    t.minimumScaleFactor = 0.7;
  }
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

function footer(stack, data, size) {
  const row = stack.addStack();
  row.addSpacer();
  const t = row.addText(data.updated_at + (data.offline ? " · offline" : "") + " · Flash");
  t.font = Font.mediumSystemFont(size);
  t.textColor = C.faint;
}

function medium(data, logo, mark, delta) {
  const w = new ListWidget();
  background(w, "medium", mark);
  w.setPadding(13, 15, 11, 15);
  header(w, logo, 20, sales(salesCount(data)), data);
  w.addSpacer(6);
  const body = w.addStack();
  const left = body.addStack();
  left.layoutVertically();
  label(left, data.is_admin ? "Total hoje" : "Faturamento hoje", 10);
  left.addSpacer(1);
  value(left, total(data), 30);
  left.addSpacer(4);
  breakdown(left, data, 11, 2, !data.is_admin);
  left.addSpacer();
  body.addSpacer(8);
  const right = body.addStack();
  right.layoutVertically();
  if (data.is_admin) {
    // Sales line and, below it, the dotted commission line.
    const g1 = right.addImage(chart(data.series || [0], 112, 36));
    g1.imageSize = new Size(112, 36);
    right.addSpacer(2);
    const g2 = right.addImage(chart(data.commission_series || [0], 112, 16, { dotted: true, color: T.comm }));
    g2.imageSize = new Size(112, 16);
  } else {
    const graph = right.addImage(chart(data.series || [0], 112, 48));
    graph.imageSize = new Size(112, 48);
  }
  right.addSpacer(4);
  if (delta) {
    badge(right, delta, 8);
    right.addSpacer(3);
  }
  conversionBlock(right, data, 10);
  right.addSpacer();
  footer(right, data, 8);
  return w;
}

function small(data, logo, mark, delta) {
  const w = new ListWidget();
  background(w, "small", mark);
  w.setPadding(12, 13, 9, 13);
  header(w, logo, 17, String(salesCount(data)));
  w.addSpacer(5);
  label(w, data.is_admin ? "Total hoje" : "Faturamento hoje", 9);
  w.addSpacer(1);
  value(w, total(data), 24);
  w.addSpacer(2);
  if (delta) badge(w, delta, 8);
  else {
    const row = w.addStack();
    row.centerAlignContent();
    const pct = row.addText(rate(data) + "% ");
    pct.font = Font.boldRoundedSystemFont(11);
    pct.textColor = C.rate;
    const rest = row.addText(data.pix_paid + "/" + data.pix_generated + " pix");
    rest.font = Font.mediumSystemFont(10);
    rest.textColor = C.soft;
  }
  w.addSpacer(2);
  eye(w, data, 10);
  w.addSpacer();
  const graph = w.addImage(chart(data.series || [0], 132, 26));
  graph.imageSize = new Size(132, 26);
  return w;
}

function large(data, logo, mark, delta) {
  const w = new ListWidget();
  background(w, "large", mark);
  w.setPadding(16, 16, 12, 16);
  header(w, logo, 22, sales(salesCount(data)), data);
  w.addSpacer(12);
  label(w, data.is_admin ? "Total do dia" : "Faturamento do dia", 12);
  w.addSpacer(2);
  value(w, total(data), 40);
  if (delta) {
    w.addSpacer(4);
    badge(w, delta, 11);
  }
  w.addSpacer(10);
  breakdown(w, data, 15, 5, true);
  w.addSpacer(12);
  const pix = w.addStack();
  pix.backgroundColor = C.pill;
  pix.cornerRadius = 10;
  pix.setPadding(6, 10, 6, 10);
  pix.centerAlignContent();
  const pct = pix.addText(rate(data) + "% conversão");
  pct.font = Font.boldSystemFont(12);
  pct.textColor = C.rate;
  const pixText = pix.addText("  ·  " + data.pix_generated + " pix gerados → " + data.pix_paid + " pagos");
  pixText.font = Font.semiboldSystemFont(12);
  pixText.textColor = C.text;
  pixText.lineLimit = 1;
  pixText.minimumScaleFactor = 0.7;
  w.addSpacer(10);
  const graph = w.addImage(chart(data.series || [0], 306, data.is_admin ? 84 : 110));
  graph.imageSize = new Size(306, data.is_admin ? 84 : 110);
  if (data.is_admin) {
    w.addSpacer(3);
    const cg = w.addImage(chart(data.commission_series || [0], 306, 24, { dotted: true, color: T.comm }));
    cg.imageSize = new Size(306, 24);
  }
  w.addSpacer();
  footer(w, data, 10);
  return w;
}

// Lock screen: logo, Flash, revenue and sales (iOS draws it in one tone).
function lockScreen(data, logo, family) {
  const w = new ListWidget();
  if (family === "accessoryInline") {
    w.addText("Flash " + brl(total(data)) + " · " + sales(salesCount(data)));
    return w;
  }
  if (family === "accessoryCircular") {
    w.addSpacer();
    const n = w.addText(String(salesCount(data)));
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
  const amount = w.addText(brl(total(data)));
  amount.font = Font.boldRoundedSystemFont(20);
  amount.minimumScaleFactor = 0.6;
  amount.lineLimit = 1;
  const count = w.addText(sales(salesCount(data)) + (data.views != null ? " · " + viewsText(data.views) + " views" : ""));
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
const THEME_CHIPS = [["claro", "☀️ Claro"], ["escuro", "🌙 Escuro"], ["pb", "◐ Preto e branco"], ["roxo", "💜 Roxo"],
  ["galaxia", "✨ Galáxia"], ["rosa", "💗 Rosa"], ["flores", "🌸 Flores"]];

function viewHtml(data) {
  const series = data.series && data.series.length > 1 ? data.series : [0, salesValue(data)];
  const max = Math.max(...series, 1);
  const pts = series.map((v, i) => [(i / (series.length - 1)) * 320, 150 - (v / max) * 130]);
  const d = "M" + pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  const conversion = rate(data);
  const html = \`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;min-height:100vh;font-family:-apple-system,system-ui;color:\${T.text};background:linear-gradient(135deg,\${BLUE[0]},\${BLUE[1]} 55%,\${BLUE[2]});background-attachment:fixed;display:flex;flex-direction:column;gap:18px;padding:28px 22px;box-sizing:border-box}
.top{display:flex;align-items:center;gap:10px;font-weight:700;font-size:22px}.top img{width:34px;height:34px;border-radius:9px;border:1px solid \${rgba(T.text, 0.3)}}
.pill{margin-left:auto;background:\${rgba(...T.pill)};border-radius:99px;padding:5px 12px;font-size:14px}
.lbl{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;font-weight:600}
.big{font-size:46px;font-weight:800;letter-spacing:-.02em}.row{display:flex;gap:12px}
.card{flex:1;background:\${rgba(...T.pill)};border-radius:16px;padding:12px 14px}.card b{display:block;font-size:22px;margin-top:4px}
svg{width:100%;height:auto;overflow:visible}.line{fill:none;stroke:\${T.line};stroke-width:3;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 6px \${rgba(T.line, 0.7)});stroke-dasharray:2000;stroke-dashoffset:2000;animation:draw 1.6s .2s ease-out forwards}
.area{fill:\${rgba(T.line, T.fill)};opacity:0;animation:fade .8s 1.2s forwards}.dot{fill:\${T.line};opacity:0;animation:pulse 1.4s 1.6s ease-in-out infinite}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes fade{to{opacity:1}}@keyframes pulse{0%,100%{opacity:1;r:5}50%{opacity:.5;r:9}}
a.open{color:#fff;text-align:center;background:\${T.line === "#ffffff" ? "rgba(0,0,0,.18)" : T.line};border-radius:14px;padding:13px;text-decoration:none;font-weight:600}
.themes{display:flex;flex-wrap:wrap;gap:8px}.chip{color:\${T.text};text-decoration:none;background:\${rgba(...T.pill)};border:2px solid transparent;border-radius:99px;padding:8px 12px;font-size:14px;font-weight:600}
.chip.on{border-color:\${T.text}}
</style></head><body>
<div class="top"><img src="\${LOGO}">Flash<span class="pill">\${data.views != null ? "👁 " + viewsText(data.views) : ""}</span><span class="pill" style="margin-left:6px">\${sales(salesCount(data))}</span></div>
<div><div class="lbl">\${data.is_admin ? "Total do dia" : "Faturamento do dia"}</div><div class="big" data-to="\${total(data)}">R$ 0,00</div></div>
<div class="row"><div class="card"><div class="lbl">Vendas</div><b data-to="\${salesValue(data)}">R$ 0,00</b></div>
\${data.is_admin ? '<div class="card"><div class="lbl">Comissão</div><b data-to="' + (data.commissions || 0) + '">R$ 0,00</b></div><div class="card"><div class="lbl">Arrecadação</div><b data-to="' + (data.fees || 0) + '">R$ 0,00</b></div>' : ""}</div>
<div class="row"><div class="card"><div class="lbl">Conversão</div><b>\${conversion}%</b><span style="opacity:.8">\${data.pix_generated} pix → \${data.pix_paid} pagos</span></div>
\${data.shark_sales ? '<div class="card"><div class="lbl">Shark</div><b data-to="' + (data.shark_revenue || 0) + '">R$ 0,00</b></div>' : ""}</div>
<svg viewBox="0 0 320 160"><path class="area" d="\${d} L320,160 L0,160 Z"/><path class="line" d="\${d}"/><circle class="dot" cx="\${pts[pts.length-1][0]}" cy="\${pts[pts.length-1][1]}" r="5"/></svg>
<div class="lbl" style="text-align:right">atualizado \${data.updated_at}</div>
<div class="lbl">Tema do widget · toque para trocar</div>
<div class="themes">\${THEME_CHIPS.map((item) => '<a class="chip' + (item[0] === THEME ? " on" : "") + '" href="flashtheme://' + item[0] + '">' + item[1] + "</a>").join("")}</div>
\${PARAM ? '<div class="lbl" style="text-transform:none;letter-spacing:0">Este widget tem um tema escrito em Parameter, que vale antes do escolhido aqui.</div>' : ""}
<a class="open" href="\${SITE}">Abrir o Flash</a>
<script>
const fmt=v=>"R$ "+v.toFixed(2).replace(".",",").replace(/\\\\B(?=(\\\\d{3})+(?!\\\\d))/g,".");
document.querySelectorAll("[data-to]").forEach(el=>{const to=+el.dataset.to,t0=performance.now();
(function tick(t){const k=Math.min(1,(t-t0)/1400),e=1-Math.pow(1-k,3);el.textContent=fmt(to*e);if(k<1)requestAnimationFrame(tick)})(t0)});
</script></body></html>\`;
  return html;
}

// Opened from the widget: tapping a theme chip applies it at once here, saves it on the
// account (the widget takes it on its next refresh) and on the phone.
async function saveTheme(name) {
  rememberTheme(name);
  try {
    const request = new Request(THEME_API);
    request.method = "POST";
    request.headers = { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" };
    request.body = JSON.stringify({ theme: name });
    request.timeoutInterval = 15;
    await request.loadJSON();
  } catch (error) {}
}
async function animatedView(data) {
  const view = new WebView();
  view.shouldAllowRequest = (request) => {
    const url = String(request.url || "");
    if (url.indexOf("flashtheme://") !== 0) return true;
    const name = themeOf(url.slice("flashtheme://".length));
    if (name) {
      useTheme(name);
      view.loadHTML(viewHtml(data));
      saveTheme(name);
    }
    return false;
  };
  await view.loadHTML(viewHtml(data));
  await view.present(true);
}

const family = config.widgetFamily || "medium";
let widget;
let data = null;
try {
  const [loaded, logo] = await Promise.all([loadData(), loadLogo()]);
  data = loaded;
  const picked = themeOf(data.theme);
  if (!PARAM && picked) {
    if (picked !== THEME) useTheme(picked);
    rememberTheme(picked);
  }
  const mark = await loadMark();
  const delta = newSales(data);
  if (family.startsWith("accessory")) widget = lockScreen(data, logo, family);
  else if (family === "small") widget = small(data, logo, mark, delta);
  else if (family === "large" || family === "extraLarge") widget = large(data, logo, mark, delta);
  else widget = medium(data, logo, mark, delta);
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
