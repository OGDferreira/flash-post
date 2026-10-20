import assert from 'node:assert/strict';
import test from 'node:test';
import { scriptableWidgetScript } from '../src/lib/scriptableWidget.ts';

for (const theme of ['azul', 'dark', 'white'] as const) {
  test(`complete valid Scriptable script (${theme})`, () => {
    const script = scriptableWidgetScript('https://flashpost.example/', 'fpw_test_token', theme);
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    assert.doesNotThrow(() => new AsyncFunction(script));
    assert.ok(script.includes('const API = "https://flashpost.example/api/widget/today"'));
    assert.ok(script.includes('const TOKEN = "fpw_test_token"'));
    assert.ok(script.includes('Authorization: "Bearer " + TOKEN'));
    assert.ok(script.includes(`args.widgetParameter || "${theme}"`));
    assert.ok(script.includes('Script.complete()'));
    assert.ok(!script.includes('undefined'));
  });
}
