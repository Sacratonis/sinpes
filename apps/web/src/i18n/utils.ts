import { ui, defaultLang } from './ui';

export function useTranslations(lang: keyof typeof ui) {
  return function t(key: keyof typeof ui[typeof defaultLang]) {
    return ui[lang][key] || ui[defaultLang][key];
  }
}

export function getLanguageUrl(currentPath: string, currentLang: string, targetLang: string) {
  // Normalize the path just in case
  const path = currentPath.startsWith('/') ? currentPath : `/${currentPath}`;

  if (currentLang === targetLang) return path;

  // THE REGEX: ^ matches the start of the string.
  // (?=\/|$) is a positive lookahead: it ensures the match is followed by either a slash or the end of the string.
  // This completely protects paths like "/escobar" from being mutated.
  const prefixRegex = new RegExp(`^\\/${currentLang}(?=\\/|$)`);

  // Case 1: Moving to default English (Strip the prefix)
  if (targetLang === defaultLang) {
    const strippedPath = path.replace(prefixRegex, '');
    return strippedPath === '' ? '/' : strippedPath;
  }

  // Case 2: Moving from default English to another language (Add the prefix)
  if (currentLang === defaultLang) {
    return path === '/' ? `/${targetLang}` : `/${targetLang}${path}`;
  }

  // Case 3: Swapping between two non-default languages (e.g., /es/about -> /pt/about)
  return path.replace(prefixRegex, `/${targetLang}`);
}
