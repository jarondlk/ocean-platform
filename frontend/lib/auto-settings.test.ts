import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readAutoPlan, effectiveChatSettings} from './auto-settings.ts';
import {defaultScope, defaultSettings, decodeSettings, encodeSettings} from './chat-settings.ts';

test('old settings default to manual; AUTO preference persists without generated results', () => {
  const {autoSettings: _old, ...old} = defaultSettings;
  assert.equal(decodeSettings(JSON.stringify({version: 1, settings: old, scope: defaultScope()})).settings.autoSettings, false);
  const encoded = encodeSettings({...defaultSettings, autoSettings: true}, defaultScope());
  assert.equal(decodeSettings(encoded).settings.autoSettings, true);
  assert(!encoded.includes('planning'));
});

test('only validated applied scope is displayed and failures retain the explanation', () => {
  assert.equal(readAutoPlan({planning: {status: 'invalid', message: 'Use an exact protocol.'}})?.scope, undefined);
  assert.equal(readAutoPlan({planning: {status: 'invalid', message: 'Use an exact protocol.'}})?.explanation, 'Use an exact protocol.');
  const scope = defaultScope();
  assert.deepEqual(readAutoPlan({planning: {status: 'applied'}, evidence_scope: scope})?.scope, scope);
  assert.equal(readAutoPlan({planning: {status: 'applied'}, evidence_scope: {version: 99}})?.scope, undefined);
});

test('effective retrieval/context can be copied into manual settings without changing generation', () => {
  const manual = {...defaultSettings, autoSettings: true, k: 20, temperature: .5};
  const options = {planning: {status: 'applied'}, evidence_scope: defaultScope(),
    retrieval: {k: 8, expand_evidence: false}, context: {inject_analysis: false, run_answer_audit: true}};
  const effective = effectiveChatSettings(manual, options);
  assert.equal(effective.k, 8); assert.equal(effective.expandEvidence, false);
  assert.equal(effective.injectAnalysis, false); assert.equal(effective.temperature, .5);
  assert.equal(manual.k, 20);
  assert.equal(effectiveChatSettings(manual, {planning: {status: 'invalid'}, retrieval: {k: 8}}), manual);
});
