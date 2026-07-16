import assert from 'node:assert/strict';
import test from 'node:test';

import {
  completeBlogLocales,
  hasCompleteBlogLocale,
} from '../src/lib/blogLocale.mjs';

function post(overrides = {}) {
  return {
    title: { en: 'English title', es: 'Título', pt: 'Título' },
    excerpt: { en: 'English excerpt', es: 'Resumen', pt: 'Resumo' },
    content: { en: '<p>English</p>', es: '<p>Español</p>', pt: '<p>Português</p>' },
    ...overrides,
  };
}

test('requires title, excerpt, and content in the same locale', () => {
  const value = post({
    excerpt: { en: 'English excerpt', es: '   ', pt: 'Resumo' },
  });

  assert.equal(hasCompleteBlogLocale(value, 'en'), true);
  assert.equal(hasCompleteBlogLocale(value, 'es'), false);
  assert.equal(hasCompleteBlogLocale(value, 'pt'), true);
  assert.deepEqual(completeBlogLocales(value), ['en', 'pt']);
});

test('does not treat another locale as a translation fallback', () => {
  const value = post({
    title: { en: 'English title', es: '', pt: '' },
    excerpt: { en: 'English excerpt', es: '', pt: '' },
    content: { en: '<p>English</p>', es: '', pt: '' },
  });

  assert.deepEqual(completeBlogLocales(value), ['en']);
});

test('rejects posts without any complete locale', () => {
  const value = post({
    title: { en: '', es: '', pt: '' },
  });

  assert.deepEqual(completeBlogLocales(value), []);
});
