/**
 * Publishes the newest widget script as a template the installed widgets update themselves
 * from: public/widget/flash-widget.js (site and key left as placeholders) and
 * public/widget/version.json. Runs before every build.
 */
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  WIDGET_TEMPLATE_BASE,
  WIDGET_TEMPLATE_TOKEN,
  WIDGET_TEMPLATE_VERSION,
  scriptableWidgetScript,
} from "../src/lib/scriptableWidget.ts";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "widget");
const draft = scriptableWidgetScript(WIDGET_TEMPLATE_BASE, WIDGET_TEMPLATE_TOKEN, "roxo", WIDGET_TEMPLATE_VERSION);
const version = createHash("sha256").update(draft).digest("hex").slice(0, 12);
const template = draft.replace(JSON.stringify(WIDGET_TEMPLATE_VERSION), JSON.stringify(version));
mkdirSync(out, { recursive: true });
writeFileSync(join(out, "flash-widget.js"), template);
writeFileSync(join(out, "version.json"), JSON.stringify({ version }) + "\n");
console.log(`widget template ${version}`);
