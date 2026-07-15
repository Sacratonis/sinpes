export const normalizeFontSearch = (value = '') => String(value)
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, ' ')
  .trim();

export const filterFontSearchIndexes = (query, indexes, exactTerms = indexes.map(() => [])) => {
  const normalizedQuery = normalizeFontSearch(query);
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  if (!tokens.length) return indexes.map(() => true);

  const normalizedIndexes = indexes.map(value => {
    const normalized = normalizeFontSearch(value);
    return { normalized, words: normalized.split(/\s+/).filter(Boolean) };
  });

  // A complete name/slug match is intentional and should not be polluted by
  // longer words such as "interface" when the user searches for "Inter".
  const normalizedExactTerms = exactTerms.map(terms => terms.map(normalizeFontSearch));
  const exactPhraseExists = normalizedExactTerms.some(terms => terms.includes(normalizedQuery));
  if (exactPhraseExists) {
    return normalizedExactTerms.map(terms => terms.includes(normalizedQuery));
  }

  const exactTokenResultExists = normalizedIndexes.some(({ words }) =>
    tokens.every(token => words.includes(token))
  );

  return normalizedIndexes.map(({ words }) => tokens.every(token =>
    exactTokenResultExists
      ? words.includes(token)
      : words.some(word => word.startsWith(token))
  ));
};
