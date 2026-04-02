/**
 * Theme system — ported from Kode-Agent src/utils/theme/index.ts.
 *
 * 4 built-in themes: dark, light, dark-daltonized, light-daltonized.
 * Rendered via Chalk 5 on the TypeScript side.
 */

export type Theme = {
  /** Primary brand color */
  kode: string
  /** Primary text */
  text: string
  /** Secondary text */
  secondaryText: string
  /** Permission dialog accent */
  permission: string
  /** Plan mode accent */
  planMode: string
  /** Success messages */
  success: string
  /** Error messages */
  error: string
  /** Warning messages */
  warning: string
  /** Diff added lines */
  diffAdded: string
  /** Diff removed lines */
  diffRemoved: string
  /** Active/selected item */
  active: string
  /** Muted text */
  muted: string
  /** Bash/command output */
  bash: string
  /** Tool use indicator */
  tool: string
  /** Thinking indicator */
  thinking: string
  /** Cost display */
  cost: string
  /** User input prompt */
  prompt: string
}

export const darkTheme: Theme = {
  kode: "#FF6B35",
  text: "#E8E8E8",
  secondaryText: "#888888",
  permission: "#FFD700",
  planMode: "#00CED1",
  success: "#00FF7F",
  error: "#FF6B6B",
  warning: "#FFD93D",
  diffAdded: "#55FF55",
  diffRemoved: "#FF5555",
  active: "#00BFFF",
  muted: "#666666",
  bash: "#98FB98",
  tool: "#DDA0DD",
  thinking: "#9370DB",
  cost: "#FFD700",
  prompt: "#00CED1",
}

export const lightTheme: Theme = {
  kode: "#D4500A",
  text: "#1A1A1A",
  secondaryText: "#666666",
  permission: "#B8860B",
  planMode: "#008B8B",
  success: "#228B22",
  error: "#CC0000",
  warning: "#B8860B",
  diffAdded: "#228B22",
  diffRemoved: "#CC0000",
  active: "#0066CC",
  muted: "#999999",
  bash: "#2E8B57",
  tool: "#8B008B",
  thinking: "#6A5ACD",
  cost: "#B8860B",
  prompt: "#008B8B",
}

export const darkDaltonizedTheme: Theme = {
  kode: "#FFB347",
  text: "#E8E8E8",
  secondaryText: "#888888",
  permission: "#87CEEB",
  planMode: "#FF69B4",
  success: "#4FC3F7",
  error: "#FF8A80",
  warning: "#87CEEB",
  diffAdded: "#4FC3F7",
  diffRemoved: "#FF8A80",
  active: "#FFD54F",
  muted: "#666666",
  bash: "#81D4FA",
  tool: "#CE93D8",
  thinking: "#B39DDB",
  cost: "#87CEEB",
  prompt: "#FF69B4",
}

export const lightDaltonizedTheme: Theme = {
  kode: "#E65100",
  text: "#1A1A1A",
  secondaryText: "#666666",
  permission: "#0277BD",
  planMode: "#AD1457",
  success: "#0277BD",
  error: "#B71C1C",
  warning: "#0277BD",
  diffAdded: "#0277BD",
  diffRemoved: "#B71C1C",
  active: "#E65100",
  muted: "#999999",
  bash: "#00695C",
  tool: "#6A1B9A",
  thinking: "#4527A0",
  cost: "#0277BD",
  prompt: "#AD1457",
}

const themes: Record<string, Theme> = {
  dark: darkTheme,
  light: lightTheme,
  "dark-daltonized": darkDaltonizedTheme,
  "light-daltonized": lightDaltonizedTheme,
}

let currentTheme: Theme = darkTheme

export function getTheme(): Theme {
  return currentTheme
}

export function setTheme(name: string): void {
  currentTheme = themes[name] ?? darkTheme
}

export function getThemeNames(): string[] {
  return Object.keys(themes)
}
