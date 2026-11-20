import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { apply } from '../integrations/dsh/index.mjs';

test('DSH observers always delegate and disposal cancels receiver processes', () => {
  const listeners = new Map();
  let cleanup;
  const agent = { id: 'root', session: { id: 'root', events: [], header: {} } };
  const ctx = {
    agents: { get: id => id === agent.id ? agent : undefined },
    on: (event, callback, options) => { listeners.set(event, callback); assert.equal(options.global, true); },
    effect: (callback) => { cleanup = callback(); },
  };
  apply(ctx, { python: '/usr/bin/true', receiver: '/unused' });
  let delegated = 0;
  const next = () => { delegated++; return Promise.resolve({ kind: 'continue' }); };
  listeners.get('user-questions/request')({ agent }, next);
  listeners.get('approval/request')({ agent }, next);
  assert.equal(delegated, 2);
  cleanup();
});

test('observer failure does not reject or answer a human request', () => {
  const listeners = new Map();
  let cleanup;
  const ctx = {
    agents: { get: () => { throw new Error('registry unavailable'); } },
    on: (name, callback) => listeners.set(name, callback),
    effect: callback => { cleanup = callback(); },
  };
  apply(ctx, { python: '/usr/bin/true', receiver: '/unused' });
  const original = console.error;
  console.error = () => {};
  try {
    const expected = Promise.resolve('original answerer');
    assert.equal(listeners.get('user-questions/request')({ agent: { id: 'x' } }, () => expected), expected);
    assert.equal(listeners.get('approval/request')({ agent: { id: 'x' } }, () => expected), expected);
  } finally { console.error = original; cleanup(); }
});

test('committed completions and human requests deliver metadata; subagents and cancellations do not', async () => {
  const folder = mkdtempSync(new URL('../work/dsh-test-', import.meta.url).pathname);
  const capture = join(folder, 'capture.mjs');
  writeFileSync(capture, `import {writeFileSync} from 'node:fs'; import {randomUUID} from 'node:crypto';
let input='';process.stdin.on('data', c=>input+=c);process.stdin.on('end',()=>writeFileSync(${JSON.stringify(folder)}+'/'+randomUUID()+'.json',input));`);
  const listeners = new Map();
  let cleanup;
  const root = { id: 'root', session: { id: 'root', header: {} } };
  const child = { id: 'child', session: { id: 'child', header: { origin: 'subagent' } } };
  const ctx = {
    agents: { get: id => id === 'root' ? root : id === 'child' ? child : undefined },
    on: (name, callback) => listeners.set(name, callback),
    effect: callback => { cleanup = callback(); },
  };
  try {
    apply(ctx, { python: process.execPath, receiver: capture });
    listeners.get('session/event')(root.session, { type: 'turn/end', seq: 8, data: { turn: 1, reason: { kind: 'completed' } } });
    listeners.get('user-questions/request')({ agent: root }, () => Promise.resolve());
    listeners.get('approval/request')({ agent: root }, () => Promise.resolve());
    listeners.get('user-questions/request')({ agent: child }, () => Promise.resolve());
    listeners.get('session/event')(child.session, { type: 'turn/end', data: { reason: { kind: 'completed' } } });
    listeners.get('session/event')(root.session, { type: 'turn/end', data: { reason: { kind: 'cancelled' } } });
    const deadline = Date.now() + 4000;
    while (readdirSync(folder).filter(f => f.endsWith('.json')).length < 4 && Date.now() < deadline) await delay(30);
    const received = readdirSync(folder).filter(f => f.endsWith('.json')).map(f => JSON.parse(readFileSync(join(folder, f), 'utf8')));
    assert.deepEqual(received.map(x => x.hook_event_name).sort(), ['ApprovalRequested', 'QuestionRequested', 'Ready', 'TurnCompleted']);
    assert.equal(received.some(x => JSON.stringify(x).includes('transcript')), false);
  } finally { cleanup?.(); rmSync(folder, { recursive: true, force: true }); }
});
