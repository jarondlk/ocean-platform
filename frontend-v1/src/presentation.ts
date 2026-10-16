/** Presentation-only storage. No identity, capabilities, scope or investigation state. */
import type { Locale } from "./model.ts";

export const PRESENTATION_STORAGE_KEY = "ocean-v1-presentation-v1";
export type PresentationPreferences = {
  locale: Locale; theme: "light" | "dark"; workspaceWidth: number;
  workspaceOpen: boolean; mobilePane: "chat" | "workspace";
};
export const DEFAULT_PRESENTATION: Readonly<PresentationPreferences> = Object.freeze({
  locale: "en", theme: "light", workspaceWidth: 390, workspaceOpen: true, mobilePane: "chat",
});
export function defaultPresentation(): PresentationPreferences { return { ...DEFAULT_PRESENTATION }; }
export function parsePresentation(value: unknown): PresentationPreferences {
  const result = defaultPresentation();
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return result;
  const data = value as Record<string, unknown>;
  if (data.locale === "en" || data.locale === "ja") result.locale = data.locale;
  if (data.theme === "light" || data.theme === "dark") result.theme = data.theme;
  if (typeof data.workspaceWidth === "number" && Number.isSafeInteger(data.workspaceWidth) && data.workspaceWidth >= 320 && data.workspaceWidth <= 620) result.workspaceWidth = data.workspaceWidth;
  if (typeof data.workspaceOpen === "boolean") result.workspaceOpen = data.workspaceOpen;
  if (data.mobilePane === "chat" || data.mobilePane === "workspace") result.mobilePane = data.mobilePane;
  return result;
}
export function restorePresentation(raw: string | null): PresentationPreferences {
  if (raw === null || raw.length > 8192) return defaultPresentation();
  try { return parsePresentation(JSON.parse(raw)); } catch { return defaultPresentation(); }
}
export function serializePresentation(value: unknown): string { return JSON.stringify(parsePresentation(value)); }
