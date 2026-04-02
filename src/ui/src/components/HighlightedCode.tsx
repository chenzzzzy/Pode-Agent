/**
 * HighlightedCode — syntax-highlighted code rendering for terminal.
 *
 * Ported from Kode-Agent/src/ui/components/HighlightedCode.tsx
 * Uses cli-highlight for syntax highlighting with fallback to plain text.
 */

import React from "react"
import { Text } from "ink"
import { highlight } from "cli-highlight"

export interface HighlightedCodeProps {
  code: string
  language?: string
  theme?: Record<string, string>
}

/**
 * Highlight code and return an array of styled Text elements.
 * Falls back to plain text if highlighting fails.
 */
export function HighlightedCode({ code, language, theme }: HighlightedCodeProps) {
  if (!code.trim()) return null

  try {
    const highlighted = highlight(code, {
      language: language || "plaintext",
      theme: theme || defaultTheme,
      ignoreIllegals: true,
    })

    // cli-highlight returns ANSI-escaped strings for Ink
    // We render them as-is since Ink handles ANSI colors
    return (
      <Text>
        {highlighted}
      </Text>
    )
  } catch {
    return <Text>{code}</Text>
  }
}

/** Default theme mapping token types to ANSI color codes. */
const defaultTheme: Record<string, string> = {
  keyword: "\x1b[35m",      // magenta
  built_in: "\x1b[36m",     // cyan
  type: "\x1b[33m",         // yellow
  literal: "\x1b[35m",      // magenta
  number: "\x1b[33m",       // yellow
  regexp: "\x1b[31m",       // red
  string: "\x1b[32m",       // green
  subst: "\x1b[32m",        // green
  symbol: "\x1b[36m",       // cyan
  class: "\x1b[33m\x1b[1m", // yellow bold
  function: "\x1b[36m",     // cyan
  title: "\x1b[36m",        // cyan
  params: "\x1b[37m",       // white
  comment: "\x1b[90m",      // bright black (gray)
  doctag: "\x1b[31m",       // red
  meta: "\x1b[90m",         // gray
  section: "\x1b[36m",      // cyan
  tag: "\x1b[33m",          // yellow
  name: "\x1b[36m",         // cyan
  attr: "\x1b[33m",         // yellow
  attribute: "\x1b[36m",    // cyan
  variable: "\x1b[37m",     // white
  bullet: "\x1b[36m",       // cyan
  code: "\x1b[32m",         // green
  emphasis: "\x1b[1m",      // bold
  strong: "\x1b[1m",        // bold
  formula: "\x1b[36m",      // cyan
  link: "\x1b[34m\x1b[4m",  // blue underline
  quote: "\x1b[90m",        // gray
  selector_tag: "\x1b[33m", // yellow
  selector_id: "\x1b[36m",  // cyan
  selector_class: "\x1b[36m", // cyan
  selector_attr: "\x1b[33m", // yellow
  selector_pseudo: "\x1b[36m", // cyan
  template_tag: "\x1b[90m", // gray
  addition: "\x1b[32m",     // green
  deletion: "\x1b[31m",     // red
}
