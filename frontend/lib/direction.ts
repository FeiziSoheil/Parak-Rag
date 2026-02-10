/**
 * RTL language codes (right-to-left): Arabic, Persian, Hebrew, Urdu, etc.
 * https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/dir
 */
const RTL_CODES = new Set([
  "ar", // Arabic
  "fa", // Persian
  "he", // Hebrew
  "ur", // Urdu
  "yi", // Yiddish
  "dv", // Divehi
  "ku", // Kurdish (Sorani is RTL in practice)
]);

/**
 * Returns true if the given BCP 47 language code is a right-to-left language.
 */
export function isRtlLanguage(lang: string): boolean {
  const code = (lang || "").toLowerCase().split("-")[0].split("_")[0];
  return RTL_CODES.has(code);
}

/**
 * Returns "rtl" or "ltr" based on the language code.
 */
export function getTextDirection(lang: string): "rtl" | "ltr" {
  return isRtlLanguage(lang) ? "rtl" : "ltr";
}

/**
 * Gets the primary browser/ui language (e.g. from navigator.language).
 */
export function getBrowserLanguage(): string {
  if (typeof navigator === "undefined") return "en";
  return navigator.language || (navigator as { userLanguage?: string }).userLanguage || "en";
}
