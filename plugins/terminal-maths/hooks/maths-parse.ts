// Parses a TeX maths string into a small tree. Covers the notation people
// write in prose: symbols, scripts, fractions, roots, accents, alphabets,
// \left...\right, environments and operator names. Anything it cannot read
// raises MathsParseError so the caller can leave the source as written.

import {
  ACCENTS,
  ALPHABETS,
  type AccentKind,
  type AtomClass,
  CHARACTER_CLASSES,
  FONT_COMMANDS,
  LARGE_OPERATORS,
  NEGATIONS,
  OPERATOR_NAMES,
  SYMBOLS,
} from './maths-symbols'

export type MathsNode =
  | { readonly kind: 'atom'; readonly text: string; readonly cls: AtomClass }
  | { readonly kind: 'text'; readonly text: string }
  | { readonly kind: 'space'; readonly width: number }
  | { readonly kind: 'group'; readonly body: MathsList }
  | { readonly kind: 'op'; readonly text: string; readonly limits: boolean }
  | { readonly kind: 'frac'; readonly numerator: MathsList; readonly denominator: MathsList }
  | { readonly kind: 'binom'; readonly top: MathsList; readonly bottom: MathsList }
  | { readonly kind: 'sqrt'; readonly index: MathsList | null; readonly body: MathsList }
  | { readonly kind: 'accent'; readonly accent: AccentKind; readonly body: MathsList }
  | {
      readonly kind: 'scripts'
      readonly base: MathsNode
      readonly sup: MathsList | null
      readonly sub: MathsList | null
      readonly limits: boolean
    }
  | { readonly kind: 'delimited'; readonly open: string; readonly body: MathsList; readonly close: string }
  | { readonly kind: 'grid'; readonly env: string; readonly rows: MathsRows }

export type MathsList = readonly MathsNode[]
export type MathsRows = ReadonlyArray<ReadonlyArray<MathsList>>

export class MathsParseError extends Error {}

const MAX_NESTING_DEPTH = 24
const MAX_SOURCE_CHARS = 4000

const SPACING_COMMANDS: ReadonlyMap<string, number> = new Map([
  [',', 1], [':', 1], [';', 1], ['>', 1], [' ', 1], ['!', 0], ['quad', 2], ['qquad', 4],
  ['enspace', 1], ['thinspace', 1], ['medspace', 1], ['thickspace', 1],
])
const IGNORED_COMMANDS = new Set([
  'displaystyle', 'textstyle', 'scriptstyle', 'scriptscriptstyle', 'nonumber', 'notag',
  'limits', 'nolimits', 'mathstrut', 'strut', 'allowbreak', 'nobreak',
])
const IGNORED_WITH_ARGUMENT = new Set(['label', 'tag', 'color', 'hspace', 'vspace', 'phantom'])
const TEXT_COMMANDS = new Set(['text', 'textrm', 'textit', 'textbf', 'textsf', 'texttt', 'mbox', 'textnormal'])
const UPRIGHT_COMMANDS = new Set(['mathrm', 'mathit', 'mathsf', 'mathtt', 'mathnormal', 'textcolor'])
const FRACTION_COMMANDS = new Set(['frac', 'dfrac', 'tfrac', 'cfrac'])
const BINOMIAL_COMMANDS = new Set(['binom', 'dbinom', 'tbinom'])
const SIZE_COMMANDS = new Set([
  'big', 'Big', 'bigg', 'Bigg', 'bigl', 'Bigl', 'biggl', 'Biggl', 'bigr', 'Bigr', 'biggr', 'Biggr',
  'bigm', 'Bigm',
])
const PRIMES = ['′', '″', '‴']

type Stop = '}' | ']' | '&' | 'row' | 'right' | 'end' | 'eof'

/** Parses `source` into rows of cells; a plain expression is one row of one cell. */
export function parseMaths(source: string): MathsRows {
  if (source.length > MAX_SOURCE_CHARS) {
    throw new MathsParseError(`expected at most ${MAX_SOURCE_CHARS} characters, got ${source.length}`)
  }
  let pos = 0

  const peek = (): string => source[pos] ?? ''
  const fail = (what: string): never => {
    throw new MathsParseError(`${what} at offset ${pos} of ${JSON.stringify(source)}`)
  }
  const skipSpaces = (): void => {
    while (/\s/.test(peek())) pos += 1
  }

  /** The command name at `pos` (which holds a backslash) without consuming it. */
  const peekCommand = (): string => {
    const letters = /^[A-Za-z]+/.exec(source.slice(pos + 1, pos + 40))
    return letters ? letters[0] : source.charAt(pos + 1)
  }
  const readCommand = (): string => {
    const name = peekCommand()
    if (name === '') fail('backslash at end of input')
    pos += 1 + name.length
    return name
  }

  const expect = (char: string): void => {
    skipSpaces()
    if (peek() !== char) fail(`expected ${JSON.stringify(char)}`)
    pos += 1
  }

  /** Reads `{...}` as raw text, balancing nested braces. */
  const readRawGroup = (): string => {
    expect('{')
    const start = pos
    let depth = 1
    while (pos < source.length) {
      const char = source[pos]
      if (char === '\\') pos += 1
      else if (char === '{') depth += 1
      else if (char === '}' && --depth === 0) break
      pos += 1
    }
    if (depth !== 0) fail('unclosed group')
    pos += 1
    return source.slice(start, pos - 1)
  }

  const atStop = (stops: ReadonlySet<Stop>): boolean => {
    const char = peek()
    if (char === '') {
      if (stops.has('eof')) return true
      return fail('unexpected end of input')
    }
    if (char === '}' || char === ']' || char === '&') return stops.has(char)
    if (char !== '\\') return false
    const name = peekCommand()
    if (name === '\\') return stops.has('row')
    return (name === 'right' && stops.has('right')) || (name === 'end' && stops.has('end'))
  }

  const parseList = (depth: number, stops: ReadonlySet<Stop>): MathsNode[] => {
    if (depth > MAX_NESTING_DEPTH) fail(`nesting deeper than ${MAX_NESTING_DEPTH}`)
    const list: MathsNode[] = []
    for (;;) {
      skipSpaces()
      if (atStop(stops)) return list
      const char = peek()
      if (char === '}' || char === '&' || (char === '\\' && peekCommand() === '\\')) {
        fail(`unexpected ${JSON.stringify(char)}`)
      }
      const atom = parseAtom(depth)
      if (atom !== null) list.push(parseScripts(depth, atom))
    }
  }

  const readArgument = (depth: number): MathsList => {
    skipSpaces()
    if (peek() === '{') {
      pos += 1
      const body = parseList(depth + 1, new Set(['}']))
      pos += 1
      return body
    }
    const atom = parseAtom(depth + 1)
    return atom === null ? [] : [atom]
  }

  const parseScripts = (depth: number, base: MathsNode): MathsNode => {
    let sup: MathsNode[] | null = null
    let sub: MathsList | null = null
    let limits = base.kind === 'op' && base.limits
    for (;;) {
      skipSpaces()
      const char = peek()
      if (char === "'") {
        let count = 0
        while (peek() === "'") {
          count += 1
          pos += 1
        }
        sup = [...(sup ?? []), { kind: 'atom', text: PRIMES[count - 1] ?? '′'.repeat(count), cls: 'ord' }]
      } else if (char === '^' || char === '_') {
        pos += 1
        const script = readArgument(depth)
        if (char === '^') sup = [...(sup ?? []), ...script]
        else if (sub === null) sub = script
        else fail('double subscript')
      } else if (char === '\\' && (peekCommand() === 'limits' || peekCommand() === 'nolimits')) {
        limits = readCommand() === 'limits'
      } else {
        break
      }
    }
    return sup === null && sub === null ? base : { kind: 'scripts', base, sup, sub, limits }
  }

  const readDelimiter = (): string => {
    skipSpaces()
    if (peek() === '\\') {
      const name = readCommand()
      return SYMBOLS.get(name)?.text ?? fail(`unknown delimiter \\${name}`)
    }
    const char = peek()
    if (char === '') fail('missing delimiter')
    pos += 1
    return char === '.' ? '' : char
  }

  const parseEnvironment = (depth: number): MathsNode => {
    const env = readRawGroup().trim()
    if (env === 'array' || env === 'subarray') readRawGroup()
    const rows = parseRows(depth + 1, 'end')
    readCommand()
    if (readRawGroup().trim() !== env) fail(`expected \\end{${env}}`)
    return { kind: 'grid', env, rows }
  }

  const parseCommand = (depth: number): MathsNode | null => {
    const name = readCommand()
    const symbol = SYMBOLS.get(name)
    if (symbol) return { kind: 'atom', ...symbol }
    const spacing = SPACING_COMMANDS.get(name)
    if (spacing !== undefined) return { kind: 'space', width: spacing }
    const operator = LARGE_OPERATORS.get(name) ?? OPERATOR_NAMES.get(name)
    if (operator) return { kind: 'op', ...operator }
    const accent = ACCENTS.get(name)
    if (accent) return { kind: 'accent', accent, body: readArgument(depth) }
    const style = FONT_COMMANDS.get(name)
    if (style) return { kind: 'group', body: restyle(readArgument(depth), ALPHABETS[style]) }
    if (FRACTION_COMMANDS.has(name)) {
      return { kind: 'frac', numerator: readArgument(depth), denominator: readArgument(depth) }
    }
    if (BINOMIAL_COMMANDS.has(name)) return { kind: 'binom', top: readArgument(depth), bottom: readArgument(depth) }
    if (TEXT_COMMANDS.has(name)) return { kind: 'text', text: plainText(readRawGroup()) }
    if (name === 'textcolor') readRawGroup()
    if (UPRIGHT_COMMANDS.has(name)) return { kind: 'group', body: readArgument(depth) }
    if (name === 'operatorname') {
      const hasLimits = peek() === '*'
      if (hasLimits) pos += 1
      return { kind: 'op', text: readRawGroup().trim(), limits: hasLimits }
    }
    if (IGNORED_COMMANDS.has(name)) return null
    if (IGNORED_WITH_ARGUMENT.has(name)) {
      readRawGroup()
      return null
    }
    return parseStructure(depth, name)
  }

  const parseStructure = (depth: number, name: string): MathsNode => {
    switch (name) {
      case 'sqrt': {
        skipSpaces()
        let index: MathsList | null = null
        if (peek() === '[') {
          pos += 1
          index = parseList(depth + 1, new Set<Stop>([']']))
          pos += 1
        }
        return { kind: 'sqrt', index, body: readArgument(depth) }
      }
      case 'left': {
        const open = readDelimiter()
        const body = parseList(depth + 1, new Set(['right']))
        readCommand()
        return { kind: 'delimited', open, body, close: readDelimiter() }
      }
      case 'middle':
        return { kind: 'atom', text: readDelimiter(), cls: 'rel' }
      case 'begin':
        return parseEnvironment(depth)
      case 'not':
        return negate(parseAtom(depth + 1))
      case 'bmod':
      case 'mod':
        return { kind: 'op', text: 'mod', limits: false }
      case 'pmod':
        return { kind: 'group', body: [{ kind: 'text', text: ' (mod ' }, ...readArgument(depth), { kind: 'text', text: ')' }] }
      case 'overset':
      case 'stackrel': {
        const over = readArgument(depth)
        return { kind: 'scripts', base: { kind: 'group', body: readArgument(depth) }, sup: over, sub: null, limits: true }
      }
      case 'underset': {
        const under = readArgument(depth)
        return { kind: 'scripts', base: { kind: 'group', body: readArgument(depth) }, sup: null, sub: under, limits: true }
      }
      default:
        if (SIZE_COMMANDS.has(name)) return sizedDelimiter(name, readDelimiter())
        // Shown as written, spaced like an operator name so it stays readable.
        return { kind: 'atom', text: `\\${name}`, cls: 'op' }
    }
  }

  const parseAtom = (depth: number): MathsNode | null => {
    if (depth > MAX_NESTING_DEPTH) fail(`nesting deeper than ${MAX_NESTING_DEPTH}`)
    skipSpaces()
    const char = peek()
    if (char === '{') return { kind: 'group', body: readArgument(depth) }
    if (char === '\\') return parseCommand(depth)
    if (char === '^' || char === '_') return { kind: 'group', body: [] }
    if (char === '~') {
      pos += 1
      return { kind: 'space', width: 1 }
    }
    if (char === '' || char === '}') fail('missing argument')
    const codePoint = String.fromCodePoint(source.codePointAt(pos) ?? 0)
    pos += codePoint.length
    return { kind: 'atom', ...(CHARACTER_CLASSES.get(codePoint) ?? { text: codePoint, cls: 'ord' }) }
  }

  const parseRows = (depth: number, end: 'end' | 'eof'): MathsRows => {
    const rows: MathsList[][] = [[]]
    for (;;) {
      const cell = parseList(depth, new Set<Stop>(['&', 'row', end]))
      rows.at(-1)?.push(cell)
      if (peek() === '&') {
        pos += 1
      } else if (peek() === '\\' && peekCommand() === '\\') {
        pos += 2
        skipSpaces()
        if (peek() === '[') readUntil(']')
        rows.push([])
      } else {
        break
      }
    }
    return dropTrailingEmptyRow(rows)
  }

  const readUntil = (char: string): void => {
    const end = source.indexOf(char, pos)
    if (end === -1) fail(`expected ${JSON.stringify(char)}`)
    pos = end + 1
  }

  return parseRows(0, 'eof')
}

/** The text of a `\text{...}` argument: escaped characters unescaped, control spaces as spaces. */
function plainText(raw: string): string {
  return raw.replace(/\\([%&#$_{}])/g, '$1').replace(/\\ |~/g, ' ')
}

function dropTrailingEmptyRow(rows: MathsList[][]): MathsRows {
  const last = rows.at(-1)
  const isEmpty = last !== undefined && last.every(cell => cell.length === 0)
  return rows.length > 1 && isEmpty ? rows.slice(0, -1) : rows
}

function restyle(list: MathsList, letters: ReadonlyMap<string, string>): MathsList {
  return list.map(node =>
    node.kind === 'atom' && node.cls === 'ord' ? { ...node, text: letters.get(node.text) ?? node.text } : node,
  )
}

function negate(node: MathsNode | null): MathsNode {
  if (node?.kind !== 'atom') return { kind: 'atom', text: '̸', cls: 'rel' }
  return { ...node, cls: 'rel', text: NEGATIONS.get(node.text) ?? `${node.text}̸` }
}

function sizedDelimiter(name: string, text: string): MathsNode {
  const cls: AtomClass = name.endsWith('l') ? 'open' : name.endsWith('r') ? 'close' : name.endsWith('m') ? 'rel' : 'ord'
  return { kind: 'atom', text, cls }
}
