import assert from 'node:assert/strict';
import test from 'node:test';
import { copyGeneratedText, copyText } from '../src/lib/clipboard.ts';
import { canChooseHome, homePath } from '../src/features/auth/homePanel.ts';
import type { User } from '../src/services/api.ts';

const owner = { role: 'OWNER', workspace_role: 'OWNER', home_panel: null } as User;
test('home destination follows persisted preference without granting FlashBot to collaborators', () => {
  assert.equal(homePath(owner), '/dashboard');
  assert.equal(homePath({ ...owner, home_panel: 'flashbot' }), '/feature/bots');
  const collaborator = { ...owner, role: 'COLLABORATOR', workspace_role: 'COLLABORATOR', home_panel: 'flashbot' } as User;
  assert.equal(canChooseHome(collaborator), false);
  assert.equal(homePath(collaborator), '/feature/accounts');
  assert.equal(homePath({ ...owner, role: 'SUPER_ADMIN', workspace_role: null }), '/admin');
});

test('async clipboard starts synchronously before generated text resolves', async () => {
  let resolve!: (text: string) => void;
  const pending = new Promise<string>((done) => { resolve = done; });
  let began = false;
  let copied = '';
  class Item { data: Record<string, Promise<Blob>>; constructor(data: Record<string, Promise<Blob>>) { this.data = data; } }
  const old = Object.getOwnPropertyDescriptor(globalThis, 'ClipboardItem');
  const clip = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  Object.defineProperty(globalThis, 'ClipboardItem', { configurable: true, value: Item });
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
    write: async (items: Item[]) => { began = true; copied = await (await items[0].data['text/plain']).text(); },
  } });
  try {
    const writing = copyGeneratedText(pending);
    assert.equal(began, true);
    resolve('complete script');
    await writing;
    assert.equal(copied, 'complete script');
  } finally {
    if (old) Object.defineProperty(globalThis, 'ClipboardItem', old); else Reflect.deleteProperty(globalThis, 'ClipboardItem');
    if (clip) Object.defineProperty(navigator, 'clipboard', clip); else Reflect.deleteProperty(navigator, 'clipboard');
  }
});

test('prepared text copies without network or token generation', async () => {
  let copied = '';
  const clip = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text: string) => { copied = text; } } });
  try { await copyText('full script'); assert.equal(copied, 'full script'); }
  finally { if (clip) Object.defineProperty(navigator, 'clipboard', clip); else Reflect.deleteProperty(navigator, 'clipboard'); }
});
