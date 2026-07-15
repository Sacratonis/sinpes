import test from 'node:test';
import assert from 'node:assert/strict';
import { filterFontSearchIndexes, normalizeFontSearch } from '../src/utils/fontSearch.mjs';

const indexes = [
  'Inter inter Sans-Serif UI Design Web Typography',
  'Interface Sans interface-sans Sans-Serif Editorial Design',
  'Miama Nueva miama-nueva Script Wedding Invitations',
  'Wensley wensley Serif Editorial Design',
];
const exactTerms = [
  ['Inter', 'inter'],
  ['Interface Sans', 'interface-sans'],
  ['Miama Nueva', 'miama-nueva'],
  ['Wensley', 'wensley'],
];

test('normalizes accents, punctuation, and case', () => {
  assert.equal(normalizeFontSearch(' Míama—Nueva '), 'miama nueva');
});

test('an exact family name does not return prefix noise', () => {
  assert.deepEqual(filterFontSearchIndexes('Inter', indexes, exactTerms), [true, false, false, false]);
});

test('hyphenated family names match normal spaces', () => {
  assert.deepEqual(filterFontSearchIndexes('miama nueva', indexes, exactTerms), [false, false, true, false]);
});

test('category and use-case tokens filter every matching font', () => {
  assert.deepEqual(filterFontSearchIndexes('sans serif', indexes), [true, true, false, false]);
  assert.deepEqual(filterFontSearchIndexes('editorial', indexes), [false, true, false, true]);
});

test('prefix matching works when no exact token exists', () => {
  assert.deepEqual(filterFontSearchIndexes('wedd', indexes), [false, false, true, false]);
});
