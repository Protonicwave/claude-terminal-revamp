// Finds TeX maths in Markdown and replaces it with terminal text. Inline maths
// ($...$, \(...\)) becomes one line of Unicode; display maths ($$...$$,
// \[...\]) on a line of its own becomes a plain code block holding the
// two-dimensional drawing. Code spans, fenced code and escaped dollars are
// left alone, and so is any span that does not parse.

import { MathsParseError, parseMaths } from './maths-parse'
import { renderDisplay, renderInline } from './maths-render'

const FENCE_OPENING = /^ {0,3}(`{3,}|~{3,})/
// How far a display span may run before its closing delimiter is presumed missing.
const MAX_DISPLAY_SEARCH_CHARS = 4000
const DISPLAY_INDENT = '  '
const TRAILING_PUNCTUATION = /^[ \t]*([.,;:]?)[ \t]*$/
const MARKDOWN_ACTIVE = /[\\`*_[\]<>~|]/g

type Span = { readonly start: number; readonly end: number; readonly source: string; readonly isDisplay: boolean }

/** `markdown` with its maths drawn for a terminal `columns` wide. */
export function renderMathsInMarkdown(markdown: string, columns: number): string {
  if (!/\$|\\\(|\\\[/.test(markdown)) return markdown
  const out: string[] = []
  let prose: string[] = []
  let fence: string | null = null
  const flushProse = (): void => {
    if (prose.length > 0) out.push(renderProse(prose.join('\n'), columns))
    prose = []
  }
  for (const line of markdown.split('\n')) {
    if (fence !== null) {
      out.push(line)
      if (line.trimStart().startsWith(fence)) fence = null
      continue
    }
    const opening = FENCE_OPENING.exec(line)
    if (opening?.[1] === undefined) {
      prose.push(line)
      continue
    }
    flushProse()
    fence = opening[1]
    out.push(line)
  }
  flushProse()
  return out.join('\n')
}

function renderProse(text: string, columns: number): string {
  let out = ''
  let pos = 0
  while (pos < text.length) {
    const next = nextSignificant(text, pos)
    out += text.slice(pos, next)
    pos = next
    if (pos >= text.length) break
    const char = text.charAt(pos)
    if (char === '`') {
      const end = codeSpanEnd(text, pos)
      out += text.slice(pos, end)
      pos = end
      continue
    }
    const span = findSpan(text, pos)
    if (span === null) {
      const step = char === '\\' ? 2 : 1
      out += text.slice(pos, pos + step)
      pos += step
      continue
    }
    const drawn = span.isDisplay ? drawDisplay(text, span, columns) : null
    if (drawn === null) {
      out += drawInline(span) ?? text.slice(span.start, span.end)
      pos = span.end
    } else {
      out += drawn.text
      pos = drawn.end
    }
  }
  return out
}

/** The index of the next character that can start a code span, an escape or maths. */
function nextSignificant(text: string, pos: number): number {
  const pattern = /[`$\\]/g
  pattern.lastIndex = pos
  return pattern.exec(text)?.index ?? text.length
}

/** The index just past the code span opening at `pos`, or past its backticks if it never closes. */
function codeSpanEnd(text: string, pos: number): number {
  let run = 0
  while (text.charAt(pos + run) === '`') run += 1
  const ticks = '`'.repeat(run)
  const close = text.indexOf(ticks, pos + run)
  return close === -1 ? pos + run : close + run
}

function findSpan(text: string, pos: number): Span | null {
  if (text.startsWith('$$', pos)) return delimitedSpan(text, pos, '$$', '$$', true)
  if (text.startsWith('\\[', pos)) return delimitedSpan(text, pos, '\\[', '\\]', true)
  if (text.startsWith('\\(', pos)) return delimitedSpan(text, pos, '\\(', '\\)', false)
  if (text.charAt(pos) === '$') return dollarSpan(text, pos)
  return null
}

function delimitedSpan(text: string, pos: number, open: string, close: string, isDisplay: boolean): Span | null {
  const from = pos + open.length
  const end = text.indexOf(close, from)
  if (end === -1 || end - from > MAX_DISPLAY_SEARCH_CHARS) return null
  const source = text.slice(from, end)
  if (source.trim() === '' || /\n[ \t]*\n/.test(source)) return null
  return { start: pos, end: end + close.length, source, isDisplay }
}

// Pandoc's rule, so prices survive: the opening $ has a non-space to its
// right; the first later $ on the line closes it only if it has a non-space
// to its left and no digit to its right.
function dollarSpan(text: string, pos: number): Span | null {
  const first = text.charAt(pos + 1)
  if (first === '' || /\s/.test(first)) return null
  const lineEnd = text.indexOf('\n', pos)
  const limit = lineEnd === -1 ? text.length : lineEnd
  let close = pos + 1
  do {
    close = text.indexOf('$', close + 1)
  } while (close !== -1 && close < limit && text.charAt(close - 1) === '\\')
  if (close === -1 || close >= limit) return null
  if (/\s/.test(text.charAt(close - 1)) || /\d/.test(text.charAt(close + 1))) return null
  // A backtick inside means the closing $ belongs to a code span, not to maths.
  if (text.slice(pos, close).includes('`')) return null
  return { start: pos, end: close + 1, source: text.slice(pos + 1, close), isDisplay: false }
}

function parseOrNull(source: string): ReturnType<typeof parseMaths> | null {
  try {
    return parseMaths(source)
  } catch (error: unknown) {
    if (error instanceof MathsParseError) return null
    throw error
  }
}

function drawInline(span: Span): string | null {
  const rows = parseOrNull(span.source)
  return rows === null ? null : renderInline(rows).replace(MARKDOWN_ACTIVE, '\\$&')
}

/** A display span on a line of its own, drawn as a code block; null to draw it inline. */
function drawDisplay(text: string, span: Span, columns: number): { text: string; end: number } | null {
  const lineStart = text.lastIndexOf('\n', span.start - 1) + 1
  const indent = text.slice(lineStart, span.start)
  const newline = text.indexOf('\n', span.end)
  const lineEnd = newline === -1 ? text.length : newline
  const trailing = TRAILING_PUNCTUATION.exec(text.slice(span.end, lineEnd))
  if (indent.trim() !== '' || trailing === null) return null
  const rows = parseOrNull(span.source)
  if (rows === null) return null
  const lines = renderDisplay(rows, trailing[1] ?? '')
  const widest = Math.max(0, ...lines.map(line => [...line].length))
  if (indent.length + DISPLAY_INDENT.length + widest + 1 > columns) return null
  const body = lines.map(line => `${indent}${DISPLAY_INDENT}${line}`)
  return { text: ['```', ...body, `${indent}\`\`\``].join('\n'), end: lineEnd }
}
