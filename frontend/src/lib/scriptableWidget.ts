/**
 * The iPhone widget script for the Scriptable app. It reads /api/widget/today with a
 * read-only token (made when the user copies it in Configurações) and draws:
 * - large: purple panel with revenue, profit, Pix generated/paid and the revenue-by-hour chart;
 * - medium: "FlashBot", today's sales total and the number of sales in small print;
 * - small and lock screen: the same, compact.
 * iOS widgets are still images refreshed by the system (about every 5-15 min), so the
 * "motion" is in the look: glow, gradient and the chart's live dot.
 */
export function scriptableWidgetScript(baseUrl: string, token: string): string {
  const base = baseUrl.replace(/\/$/, "");
  return `// FlashBot — widget de vendas do FlashPost para o Scriptable
// Gerado em ${new Date().toLocaleDateString("pt-BR")}. Copiar o script de novo no site desliga este.
const API = ${JSON.stringify(`${base}/api/widget/today`)};
const TOKEN = ${JSON.stringify(token)};
const LOGO = ${JSON.stringify(`${base}/brand/icon-192.png`)};

const C = {
  bgTop: new Color("#2b0f63"), bgBottom: new Color("#0b0620"), dark: new Color("#0a0a12"),
  line: new Color("#b07cff"), glow: new Color("#8b5cf6"), text: Color.white(),
  muted: new Color("#b9a8e6"), green: new Color("#4ade80"), soft: new Color("#ffffff", 0.08),
};
const fm = FileManager.local();
const dir = fm.documentsDirectory();

function brl(value) {
  const [int, dec] = Math.abs(value).toFixed(2).split(".");
  return (value < 0 ? "-" : "") + "R$ " + int.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ".") + "," + dec;
}

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
  const path = fm.joinPath(dir, "flashbot-logo.png");
  if (fm.fileExists(path)) return fm.readImage(path);
  try {
    const image = await new Request(LOGO).loadImage();
    fm.writeImage(path, image);
    return image;
  } catch (error) {
    return null;
  }
}

function header(stack, logo, size, right) {
  const row = stack.addStack();
  row.centerAlignContent();
  if (logo) {
    const image = row.addImage(logo);
    image.imageSize = new Size(size, size);
    image.cornerRadius = size * 0.24;
    row.addSpacer(6);
  }
  const name = row.addText("FlashBot");
  name.font = Font.boldSystemFont(size * 0.78);
  name.textColor = C.text;
  row.addSpacer();
  if (right) {
    const tag = row.addText(right);
    tag.font = Font.mediumSystemFont(size * 0.62);
    tag.textColor = C.muted;
  }
  return row;
}

function metric(stack, label, value, color) {
  const box = stack.addStack();
  box.layoutVertically();
  const title = box.addText(label);
  title.font = Font.mediumSystemFont(11);
  title.textColor = C.muted;
  box.addSpacer(2);
  const number = box.addText(value);
  number.font = Font.boldRoundedSystemFont(20);
  number.textColor = color;
  number.minimumScaleFactor = 0.6;
  number.lineLimit = 1;
}

function chart(series, width, height) {
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;
  const points = series.length > 1 ? series : [0, series[0] || 0];
  const max = Math.max(...points, 1);
  const step = width / 23; // the day's 24 hours; the line stops at the current hour
  const y = (v) => height - 6 - (v / max) * (height - 16);
  const line = new Path();
  line.move(new Point(0, y(points[0])));
  points.forEach((v, i) => line.addLine(new Point(i * step, y(v))));
  const area = new Path();
  area.move(new Point(0, height));
  points.forEach((v, i) => area.addLine(new Point(i * step, y(v))));
  area.addLine(new Point((points.length - 1) * step, height));
  area.closeSubpath();
  ctx.addPath(area);
  ctx.setFillColor(new Color("#8b5cf6", 0.22));
  ctx.fillPath();
  // glow under the line, then the line itself
  [[6, 0.18], [3, 0.35], [1.6, 1]].forEach(([w, a]) => {
    ctx.addPath(line);
    ctx.setStrokeColor(new Color("#b07cff", a));
    ctx.setLineWidth(w);
    ctx.strokePath();
  });
  const last = new Point((points.length - 1) * step, y(points[points.length - 1]));
  ctx.setFillColor(new Color("#b07cff", 0.3));
  ctx.fillEllipse(new Rect(last.x - 7, last.y - 7, 14, 14));
  ctx.setFillColor(Color.white());
  ctx.fillEllipse(new Rect(last.x - 3, last.y - 3, 6, 6));
  return ctx.getImage();
}

function background(widget, purple) {
  const gradient = new LinearGradient();
  gradient.colors = purple ? [C.bgTop, C.bgBottom] : [new Color("#1c1030"), C.dark];
  gradient.locations = [0, 1];
  widget.backgroundGradient = gradient;
}

function large(data, logo) {
  const w = new ListWidget();
  background(w, true);
  w.setPadding(16, 16, 14, 16);
  header(w, logo, 22, "Hoje");
  w.addSpacer(12);
  const row = w.addStack();
  metric(row, "Faturamento", brl(data.revenue), C.text);
  row.addSpacer();
  metric(row, "Lucro", brl(data.profit), C.green);
  w.addSpacer(10);
  const pix = w.addStack();
  pix.backgroundColor = C.soft;
  pix.cornerRadius = 10;
  pix.setPadding(7, 10, 7, 10);
  const conversion = data.pix_generated ? Math.round((100 * data.pix_paid) / data.pix_generated) : 0;
  const pixText = pix.addText(data.pix_generated + " pix gerados  ·  " + data.pix_paid + " pagos  ·  " + conversion + "% conversão");
  pixText.font = Font.mediumSystemFont(12);
  pixText.textColor = C.text;
  w.addSpacer(10);
  const graph = w.addImage(chart(data.series || [0], 306, 150));
  graph.imageSize = new Size(306, 150);
  w.addSpacer(4);
  const axis = w.addStack();
  [["00h", C.muted], [null], ["Faturamento por hora", C.muted], [null], [data.updated_at + (data.offline ? " · offline" : ""), C.muted]].forEach(([t, c]) => {
    if (!t) return axis.addSpacer();
    const label = axis.addText(t);
    label.font = Font.systemFont(10);
    label.textColor = c;
  });
  return w;
}

function compact(data, logo, family) {
  const w = new ListWidget();
  background(w, false);
  const small = family === "small";
  w.setPadding(14, 16, 14, 16);
  header(w, logo, small ? 18 : 22, small ? null : data.pix_paid + " vendas");
  w.addSpacer();
  const value = w.addText(brl(data.revenue));
  value.font = Font.boldRoundedSystemFont(small ? 24 : 40);
  value.textColor = C.text;
  value.minimumScaleFactor = 0.5;
  value.lineLimit = 1;
  if (small) {
    w.addSpacer(2);
    const count = w.addText(data.pix_paid + " vendas hoje");
    count.font = Font.mediumSystemFont(11);
    count.textColor = C.muted;
  }
  return w;
}

function lockScreen(data, family) {
  const w = new ListWidget();
  if (family === "accessoryInline") {
    w.addText("⚡ " + brl(data.revenue) + " · " + data.pix_paid + " vendas");
    return w;
  }
  const name = w.addText("FlashBot · " + data.pix_paid + " vendas");
  name.font = Font.mediumSystemFont(11);
  const value = w.addText(brl(data.revenue));
  value.font = Font.boldRoundedSystemFont(20);
  value.minimumScaleFactor = 0.6;
  return w;
}

function failure(message) {
  const w = new ListWidget();
  background(w, true);
  const title = w.addText("FlashBot");
  title.font = Font.boldSystemFont(15);
  title.textColor = C.text;
  w.addSpacer(6);
  const text = w.addText(message);
  text.font = Font.systemFont(12);
  text.textColor = C.muted;
  return w;
}

const family = config.widgetFamily || "large";
let widget;
try {
  const [data, logo] = await Promise.all([loadData(), loadLogo()]);
  if (family.startsWith("accessory")) widget = lockScreen(data, family);
  else if (family === "large" || family === "extraLarge") widget = large(data, logo);
  else widget = compact(data, logo, family);
} catch (error) {
  widget = failure(String(error.message || error));
}
widget.refreshAfterDate = new Date(Date.now() + 5 * 60 * 1000);
widget.url = ${JSON.stringify(`${base}/feature/bots`)};
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentLarge();
Script.complete();
`;
}
