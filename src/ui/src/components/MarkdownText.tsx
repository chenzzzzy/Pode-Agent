/**
 * MarkdownText — renders markdown as clean terminal-friendly Ink output.
 *
 * Uses `marked` to parse markdown AST, then renders each block as
 * appropriate Ink elements. Prioritizes readability over fidelity:
 * - Headings: bold, no `#` symbols
 * - Lists: clean bullet points (•)
 * - Inline code: dim highlight, no backticks
 * - Code blocks: preserved with syntax highlighting
 * - Links: show text + URL cleanly
 * - Bold/italic: styled, no `**`/`_` leakage
 * - Paragraphs: proper spacing
 */

import React from "react"
import { Box, Text } from "ink"
import { marked, type Token, type Tokens } from "marked"
import { HighlightedCode } from "./HighlightedCode.js"

export interface MarkdownTextProps {
  text: string
  theme?: { muted?: string; active?: string; tool?: string }
}

export function MarkdownText({ text, theme }: MarkdownTextProps) {
  const mutedColor = theme?.muted ?? "#666666"
  const linkColor = theme?.tool ?? "#DDA0DD"

  // Parse markdown into tokens
  let tokens: Token[]
  try {
    tokens = marked.lexer(text)
  } catch {
    return <Text>{text}</Text>
  }

  return (
    <Box flexDirection="column">
      {tokens.map((token, i) => renderBlock(token, i, mutedColor, linkColor))}
    </Box>
  )
}

function renderBlock(
  token: Token,
  key: number,
  mutedColor: string,
  linkColor: string,
): React.ReactNode {
  switch (token.type) {
    case "heading": {
      const t = token as Tokens.Heading
      return (
        <Box key={key} marginTop={key > 0 ? 1 : 0}>
          <Text bold>{renderInlineTokens(t.tokens || [], linkColor)}</Text>
        </Box>
      )
    }

    case "paragraph": {
      const t = token as Tokens.Paragraph
      return (
        <Box key={key} marginTop={key > 0 ? 1 : 0}>
          <Text wrap="wrap">{renderInlineTokens(t.tokens || [], linkColor)}</Text>
        </Box>
      )
    }

    case "list": {
      const t = token as Tokens.List
      return (
        <Box key={key} flexDirection="column" marginTop={0}>
          {t.items.map((item, j) => (
            <Box key={j} paddingLeft={1}>
              <Text>
                {t.ordered ? `${j + 1}. ` : "– "}
              </Text>
              <Box flexDirection="column" flexGrow={1}>
                <Text wrap="wrap">
                  {item.tokens
                    ? renderInlineTokens(
                        flattenListItemTokens(item.tokens),
                        linkColor,
                      )
                    : item.text}
                </Text>
              </Box>
            </Box>
          ))}
        </Box>
      )
    }

    case "code": {
      const t = token as Tokens.Code
      return (
        <Box
          key={key}
          flexDirection="column"
          marginTop={1}
          marginBottom={0}
          paddingLeft={1}
          borderStyle="single"
          borderLeft
          borderRight={false}
          borderTop={false}
          borderBottom={false}
          borderColor={mutedColor}
        >
          {t.lang && (
            <Text color={mutedColor} dimColor>
              {t.lang}
            </Text>
          )}
          <HighlightedCode code={t.text} language={t.lang || undefined} />
        </Box>
      )
    }

    case "blockquote": {
      const t = token as Tokens.Blockquote
      const innerText = t.tokens
        ? t.tokens
            .map((inner) => {
              if ("text" in inner) return (inner as { text: string }).text
              return ""
            })
            .join("")
        : t.text
      return (
        <Box
          key={key}
          paddingLeft={1}
          marginTop={1}
          borderStyle="single"
          borderLeft
          borderRight={false}
          borderTop={false}
          borderBottom={false}
          borderColor={mutedColor}
        >
          <Text color={mutedColor} italic wrap="wrap">
            {innerText}
          </Text>
        </Box>
      )
    }

    case "hr":
      return (
        <Box key={key} marginTop={1}>
          <Text color={mutedColor}>{"─".repeat(40)}</Text>
        </Box>
      )

    case "space":
      return null

    case "html": {
      const t = token as Tokens.HTML
      // Strip HTML tags for terminal
      const stripped = t.text.replace(/<[^>]*>/g, "").trim()
      if (!stripped) return null
      return (
        <Box key={key} marginTop={1}>
          <Text wrap="wrap">{stripped}</Text>
        </Box>
      )
    }

    case "table": {
      const t = token as Tokens.Table
      return (
        <Box key={key} flexDirection="column" marginTop={1}>
          {/* Header */}
          <Text bold>
            {t.header
              .map((h) =>
                h.tokens ? tokenToPlainText(h.tokens) : h.text,
              )
              .join(" │ ")}
          </Text>
          <Text color={mutedColor}>
            {"─".repeat(40)}
          </Text>
          {/* Rows */}
          {t.rows.map((row, ri) => (
            <Text key={ri}>
              {row
                .map((cell) =>
                  cell.tokens
                    ? tokenToPlainText(cell.tokens)
                    : cell.text,
                )
                .join(" │ ")}
            </Text>
          ))}
        </Box>
      )
    }

    default: {
      // Fallback: render raw text if available
      if ("text" in token && typeof token.text === "string") {
        return (
          <Box key={key} marginTop={key > 0 ? 1 : 0}>
            <Text wrap="wrap">{token.text}</Text>
          </Box>
        )
      }
      return null
    }
  }
}

/** Flatten list item tokens — extract inline tokens from paragraph wrappers. */
function flattenListItemTokens(tokens: Token[]): Token[] {
  const result: Token[] = []
  for (const t of tokens) {
    if (t.type === "paragraph" && "tokens" in t && Array.isArray(t.tokens)) {
      result.push(...(t as Tokens.Paragraph).tokens)
    } else if (t.type === "text" && "tokens" in t && Array.isArray(t.tokens)) {
      result.push(...(t as Tokens.Text).tokens)
    } else {
      result.push(t)
    }
  }
  return result
}

/** Render inline tokens (bold, italic, code, link, text) as React elements. */
function renderInlineTokens(
  tokens: Token[],
  linkColor: string,
): React.ReactNode[] {
  return tokens.map((t, i) => renderInlineToken(t, i, linkColor))
}

function renderInlineToken(
  token: Token,
  key: number,
  linkColor: string,
): React.ReactNode {
  switch (token.type) {
    case "text": {
      const t = token as Tokens.Text
      // Handle nested tokens in text
      if (t.tokens && t.tokens.length > 0) {
        return <React.Fragment key={key}>{renderInlineTokens(t.tokens, linkColor)}</React.Fragment>
      }
      return <React.Fragment key={key}>{t.text}</React.Fragment>
    }

    case "strong": {
      const t = token as Tokens.Strong
      return (
        <Text key={key} bold>
          {t.tokens ? renderInlineTokens(t.tokens, linkColor) : t.text}
        </Text>
      )
    }

    case "em": {
      const t = token as Tokens.Em
      return (
        <Text key={key} italic>
          {t.tokens ? renderInlineTokens(t.tokens, linkColor) : t.text}
        </Text>
      )
    }

    case "codespan": {
      const t = token as Tokens.Codespan
      return (
        <Text key={key} dimColor bold>
          {t.text}
        </Text>
      )
    }

    case "link": {
      const t = token as Tokens.Link
      const label = t.tokens
        ? tokenToPlainText(t.tokens)
        : t.text
      if (label === t.href) {
        return (
          <Text key={key} color={linkColor} underline>
            {t.href}
          </Text>
        )
      }
      return (
        <Text key={key}>
          <Text color={linkColor} underline>
            {label}
          </Text>
          <Text dimColor> ({t.href})</Text>
        </Text>
      )
    }

    case "image": {
      const t = token as Tokens.Image
      return (
        <Text key={key} dimColor>
          [image: {t.text || t.href}]
        </Text>
      )
    }

    case "br":
      return <Text key={key}>{"\n"}</Text>

    case "del": {
      const t = token as Tokens.Del
      return (
        <Text key={key} strikethrough>
          {t.tokens ? renderInlineTokens(t.tokens, linkColor) : t.text}
        </Text>
      )
    }

    case "escape": {
      const t = token as Tokens.Escape
      return <React.Fragment key={key}>{t.text}</React.Fragment>
    }

    default: {
      if ("text" in token && typeof token.text === "string") {
        return <React.Fragment key={key}>{token.text}</React.Fragment>
      }
      return null
    }
  }
}

/** Extract plain text from inline tokens for labels. */
function tokenToPlainText(tokens: Token[]): string {
  return tokens
    .map((t) => {
      if ("text" in t && typeof t.text === "string") return t.text
      if ("tokens" in t && Array.isArray(t.tokens))
        return tokenToPlainText(t.tokens as Token[])
      return ""
    })
    .join("")
}
