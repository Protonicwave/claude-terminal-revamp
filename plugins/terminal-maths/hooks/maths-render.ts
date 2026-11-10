// Draws a parsed maths tree as terminal text: `renderInline` gives one line
// of Unicode, `renderDisplay` a block of lines with stacked fractions, raised
// scripts, tall brackets and aligned grids.

import type { MathsList, MathsNode, MathsRows } from './maths-parse'
import {
  ACCENT_ROW_GLYPH,
  type AtomClass,
  COMBINING,
  RAISED_MARKS,
  SUBSCRIPTS,
  SUPERSCRIPTS,
} from './maths-symbols'

// TeX's inter-atom spacing, reduced to "space or not" for a monospace grid.
const SPACED_PAIRS: ReadonlyMap<AtomClass, ReadonlySet<AtomClass>> = new Map([
  ['ord', new Set<AtomClass>(['op', 'bin', 'rel'])],
  ['op', new Set<AtomClass>(['ord', 'op', 'rel'])],
  ['bin', new Set<AtomClass>(['ord', 'op', 'open'])],
  ['rel', new Set<AtomClass>(['ord', 'op', 'open'])],
  ['close', new Set<AtomClass>(['op', 'bin', 'rel'])],
  ['punct', new Set<AtomClass>(['ord', 'op', 'rel', 'open', 'close', 'punct'])],
  ['open', new Set<AtomClass>()],
])
const UNARY_CONTEXT = new Set<AtomClass | null>([null, 'bin', 'op', 'rel', 'open', 'punct'])

const ENVIRONMENT_FENCES: ReadonlyMap<string, readonly [string, string]> = new Map([
  ['pmatrix', ['(', ')']], ['bmatrix', ['[', ']']], ['Bmatrix', ['{', '}']],
  ['vmatrix', ['|', '|']], ['Vmatrix', ['‖', '‖']], ['matrix', ['', '']],
  ['smallmatrix', ['', '']], ['array', ['', '']], ['cases', ['{', '']],
  ['dcases', ['{', '']], ['rcases', ['', '}']],
])
const MATRIX_GAP = '  '
const ROOT_SIGNS: ReadonlyMap<string, string> = new Map([['', '√'], ['3', '∛'], ['4', '∜']])

type Classed = { readonly node: MathsNode; readonly cls: AtomClass | null }

function classOf(node: MathsNode): AtomClass | null {
  switch (node.kind) {
    case 'atom':
      return node.cls
    case 'op':
      return 'op'
    case 'scripts':
      return classOf(node.base)
    case 'space':
      return null
    default:
      return 'ord'
  }
}

/** Each node with its effective class; a binary operator with no left operand acts as ordinary. */
function classify(list: MathsList): Classed[] {
  const out: Classed[] = []
  let previous: AtomClass | null = null
  for (const node of list) {
    let cls = classOf(node)
    if (cls === 'bin' && UNARY_CONTEXT.has(previous)) cls = 'ord'
    out.push({ node, cls })
    if (node.kind !== 'space') previous = cls
  }
  return out
}

function isSpacedPair(left: AtomClass | null, right: AtomClass | null): boolean {
  if (left === null || right === null) return false
  return SPACED_PAIRS.get(left)?.has(right) ?? false
}

/** Interleaves `render(node)` with single spaces where TeX would leave a gap. */
function spaced<T>(list: MathsList, isTight: boolean, render: (node: MathsNode) => T, gap: () => T): T[] {
  const classed = classify(list)
  const out: T[] = []
  classed.forEach((item, index) => {
    const before = classed[index - 1]
    if (!isTight && before && isSpacedPair(before.cls, item.cls)) out.push(gap())
    out.push(render(item.node))
  })
  return out
}

function mapAll(text: string, table: ReadonlyMap<string, string>): string | null {
  let out = ''
  for (const char of text) {
    const mapped = table.get(char)
    if (mapped === undefined) return null
    out += mapped
  }
  return out
}

const SCRIPT_CHARACTERS = new Set([...SUPERSCRIPTS.values(), ...SUBSCRIPTS.values(), ...RAISED_MARKS])
const NUMBER = /^\d+(?:\.\d+)?/u
const BRACKET_PAIRS: ReadonlyMap<string, string> = new Map([['(', ')'], ['[', ']']])

function isScriptTail(chars: readonly string[]): boolean {
  return chars.every(char => SCRIPT_CHARACTERS.has(char) || /\p{M}/u.test(char))
}

/** The index just past the bracket closing the one at the start of `chars`, or -1. */
function bracketEnd(chars: readonly string[]): number {
  const close = BRACKET_PAIRS.get(chars[0] ?? '')
  if (close === undefined) return -1
  let depth = 0
  for (const [index, char] of chars.entries()) {
    if (char === chars[0]) depth += 1
    else if (char === close && --depth === 0) return index + 1
  }
  return -1
}

/** True when `text` reads as one operand: a number, one symbol, a bracketed group or a root of one, with scripts. */
function isAtomic(text: string): boolean {
  const chars = [...text]
  if (chars.length <= 1) return true
  if (chars[0] === '√' || chars[0] === '∛' || chars[0] === '∜') return isAtomic(chars.slice(1).join(''))
  const number = NUMBER.exec(text)
  if (number !== null) return isScriptTail([...text.slice(number[0].length)])
  const end = bracketEnd(chars)
  if (end > 0) return isScriptTail(chars.slice(end))
  return !SCRIPT_CHARACTERS.has(chars[0] ?? '') && isScriptTail(chars.slice(1))
}

function bracket(text: string): string {
  return isAtomic(text) ? text : `(${text})`
}

/** `text` in Unicode superscript characters, or null when one has none. Marks that already sit high stay as written. */
function toSuperscript(text: string): string | null {
  if ([...text].every(char => RAISED_MARKS.has(char))) return text
  return mapAll(text, SUPERSCRIPTS)
}

/** `text` in Unicode subscript characters, or null when one has none. */
function toSubscript(text: string): string | null {
  return mapAll(text, SUBSCRIPTS)
}

function superscriptText(text: string): string {
  return toSuperscript(text) ?? `^${bracket(text)}`
}

function subscriptText(text: string): string {
  return toSubscript(text) ?? `_${bracket(text)}`
}

function accentText(text: string, accent: keyof typeof COMBINING): string {
  const letters = [...text.normalize('NFD')].filter(char => !/\p{M}/u.test(char))
  if (letters.length === 1) return `${text}${COMBINING[accent]}`
  if (accent === 'bar' || accent === 'underline') return [...text].map(char => `${char}${COMBINING[accent]}`).join('')
  return `${accent}(${text})`
}

/** One line of Unicode for `rows`, with `;` between rows. */
export function renderInline(rows: MathsRows): string {
  return rows.map(cells => inlineList(cells.flat(), false)).join('; ')
}

function inlineList(list: MathsList, isTight: boolean): string {
  return spaced(list, isTight, node => inlineNode(node, isTight), () => ' ').join('')
}

function inlineNode(node: MathsNode, isTight: boolean): string {
  switch (node.kind) {
    case 'atom':
    case 'text':
    case 'op':
      return node.text
    case 'space':
      return ' '.repeat(node.width)
    case 'group':
      return inlineList(node.body, isTight)
    case 'frac':
      return `${bracket(inlineList(node.numerator, true))}/${bracket(inlineList(node.denominator, true))}`
    case 'binom':
      return `C(${inlineList(node.top, true)}, ${inlineList(node.bottom, true)})`
    case 'sqrt':
      return inlineRoot(node.index, node.body)
    case 'accent':
      return accentText(inlineList(node.body, true), node.accent)
    case 'scripts':
      return inlineScripts(node)
    case 'delimited':
      return `${node.open}${inlineList(node.body, isTight)}${node.close}`
    case 'grid':
      return inlineGrid(node.env, node.rows)
  }
}

function inlineRoot(index: MathsList | null, body: MathsList): string {
  const degree = index === null ? '' : inlineList(index, true)
  const radicand = bracket(inlineList(body, true))
  const sign = ROOT_SIGNS.get(degree) ?? `${superscriptText(degree)}√`
  return `${sign}${radicand}`
}

function inlineScripts(node: Extract<MathsNode, { kind: 'scripts' }>): string {
  const base = inlineNode(node.base, true)
  const sub = node.sub === null ? '' : subscriptText(inlineList(node.sub, true))
  const sup = node.sup === null ? '' : superscriptText(inlineList(node.sup, true))
  return `${node.base.kind === 'frac' ? `(${base})` : base}${sub}${sup}`
}

function inlineGrid(env: string, rows: MathsRows): string {
  const isMatrix = ENVIRONMENT_FENCES.has(env) && !env.includes('cases')
  const drawRow = (cells: ReadonlyArray<MathsList>): string => {
    if (isMatrix) return cells.map(cell => inlineList(cell, false)).join(' ')
    if (env.includes('cases')) return cells.map(cell => inlineList(cell, false)).join(', ')
    return inlineList(cells.flat(), false)
  }
  const body = rows.map(drawRow).join('; ')
  const [open, close] = ENVIRONMENT_FENCES.get(env) ?? ['', '']
  if (isMatrix) return `${open || '['}${body}${close || ']'}`
  return `${open}${open ? ' ' : ''}${body}${close ? ' ' : ''}${close}`
}

type Box = { readonly lines: readonly string[]; readonly baseline: number; readonly width: number }

/** Lines of text drawing `rows` in two dimensions, `suffix` on the baseline; trailing spaces removed. */
export function renderDisplay(rows: MathsRows, suffix: string): string[] {
  const box =
    rows.length === 1 && rows[0]?.length === 1
      ? layoutList(rows[0]?.[0] ?? [], false)
      : layoutGrid('aligned', rows)
  return joinBoxes([box, textBox(suffix)]).lines.map(line => line.trimEnd())
}

// East Asian wide characters take two terminal columns; combining marks take none.
const WIDE_CHARACTER = /[ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹏＀-｠￠-￦\u{20000}-\u{3FFFD}]/u

/** The number of terminal columns `text` occupies. */
export function displayWidth(text: string): number {
  let width = 0
  for (const char of text) {
    if (/\p{M}/u.test(char)) continue
    width += WIDE_CHARACTER.test(char) ? 2 : 1
  }
  return width
}

function padTo(text: string, width: number): string {
  return text + ' '.repeat(Math.max(0, width - displayWidth(text)))
}

function textBox(text: string): Box {
  return { lines: [text], baseline: 0, width: displayWidth(text) }
}

function blank(width: number): string {
  return ' '.repeat(width)
}

function centre(box: Box, width: number): string[] {
  const left = Math.floor((width - box.width) / 2)
  return box.lines.map(line => padTo(blank(left) + line, width))
}

/** Joins boxes left to right, lining up their baselines. */
function joinBoxes(boxes: readonly Box[]): Box {
  const above = Math.max(0, ...boxes.map(box => box.baseline))
  const below = Math.max(0, ...boxes.map(box => box.lines.length - box.baseline - 1))
  const height = above + below + 1
  const lines = Array.from({ length: height }, () => '')
  for (const box of boxes) {
    const top = above - box.baseline
    for (let row = 0; row < height; row += 1) {
      const line = row >= top && row < top + box.lines.length ? (box.lines[row - top] ?? '') : ''
      lines[row] += padTo(line, box.width)
    }
  }
  return { lines, baseline: above, width: boxes.reduce((sum, box) => sum + box.width, 0) }
}

function stack(parts: readonly Box[], baselineRow: number): Box {
  const width = Math.max(0, ...parts.map(part => part.width))
  return { lines: parts.flatMap(part => centre(part, width)), baseline: baselineRow, width }
}

function layoutList(list: MathsList, isTight: boolean): Box {
  const boxes = spaced(list, isTight, node => layoutNode(node, isTight), () => textBox(' '))
  return boxes.length === 0 ? textBox('') : joinBoxes(boxes)
}

function layoutNode(node: MathsNode, isTight: boolean): Box {
  switch (node.kind) {
    case 'frac': {
      const top = layoutList(node.numerator, true)
      const bottom = layoutList(node.denominator, true)
      const rule = textBox('─'.repeat(Math.max(top.width, bottom.width) + 2))
      return stack([top, rule, bottom], top.lines.length)
    }
    case 'binom':
      return fence('(', stack([layoutList(node.top, true), layoutList(node.bottom, true)], 0), ')')
    case 'sqrt': {
      const body = layoutList(node.body, true)
      const isShort = body.lines.length === 1 && isAtomic(body.lines[0] ?? '')
      return isShort ? textBox(inlineRoot(node.index, node.body)) : layoutRoot(node.index, body)
    }
    case 'accent':
      return layoutAccent(node.accent, node.body)
    case 'scripts':
      return layoutScripts(node)
    case 'delimited':
      return fence(node.open, layoutList(node.body, isTight), node.close)
    case 'grid':
      return layoutGrid(node.env, node.rows)
    case 'group':
      return layoutList(node.body, isTight)
    default:
      return textBox(inlineNode(node, isTight))
  }
}

function layoutRoot(index: MathsList | null, body: Box): Box {
  const degree = index === null ? '' : inlineList(index, true)
  const sign = ROOT_SIGNS.get(degree) ?? `${superscriptText(degree)}√`
  const signWidth = displayWidth(sign)
  const lines = [
    blank(signWidth) + '─'.repeat(body.width),
    ...body.lines.map((line, row) =>
      // The bar sits in the radical's last column, directly above the √.
      (row === body.lines.length - 1 ? sign : `${blank(signWidth - 1)}│`) + padTo(line, body.width),
    ),
  ]
  return { lines, baseline: body.baseline + 1, width: signWidth + body.width }
}

function layoutAccent(accent: keyof typeof COMBINING, body: MathsList): Box {
  const box = layoutList(body, true)
  if (box.lines.length === 1 && displayWidth(box.lines[0] ?? '') <= 1) {
    return textBox(accentText(box.lines[0] ?? '', accent))
  }
  const glyph = ACCENT_ROW_GLYPH[accent]
  const isRule = glyph === '─'
  const mark = textBox(isRule ? glyph.repeat(box.width) : glyph)
  return accent === 'underline' ? stack([box, mark], box.baseline) : stack([mark, box], box.baseline + 1)
}

function layoutScripts(node: Extract<MathsNode, { kind: 'scripts' }>): Box {
  const base = layoutNode(node.base, true)
  const sup = node.sup === null ? null : layoutList(node.sup, true)
  const sub = node.sub === null ? null : layoutList(node.sub, true)
  if (node.limits) {
    const parts = [sup, base, sub].filter((part): part is Box => part !== null)
    return stack(parts, (sup?.lines.length ?? 0) + base.baseline)
  }
  const supText = node.sup === null ? '' : toSuperscript(inlineList(node.sup, true))
  const subText = node.sub === null ? '' : toSubscript(inlineList(node.sub, true))
  const areScriptsOneLine = [sup, sub].every(part => part === null || part.lines.length === 1)
  if (supText === null || subText === null || !areScriptsOneLine) return raiseScripts(base, sup, sub)
  if (base.lines.length === 1) return textBox(inlineScripts(node))
  return besideScripts(base, supText, subText)
}

/** Unicode scripts written beside a tall base: the superscript at its top, the subscript at its foot. */
function besideScripts(base: Box, supText: string, subText: string): Box {
  const width = base.width + Math.max(displayWidth(supText), displayWidth(subText))
  const last = base.lines.length - 1
  const lines = base.lines.map((line, row) => {
    const script = row === 0 ? supText : row === last ? subText : ''
    return padTo(padTo(line, base.width) + script, width)
  })
  return { ...base, lines, width }
}

function raiseScripts(base: Box, sup: Box | null, sub: Box | null): Box {
  const scriptWidth = Math.max(sup?.width ?? 0, sub?.width ?? 0)
  const width = base.width + scriptWidth
  const offset = blank(base.width)
  const lines = [
    ...(sup?.lines ?? []).map(line => padTo(offset + line, width)),
    ...base.lines.map(line => padTo(line, width)),
    ...(sub?.lines ?? []).map(line => padTo(offset + line, width)),
  ]
  return { lines, baseline: (sup?.lines.length ?? 0) + base.baseline, width }
}

const TALL_PIECES: ReadonlyMap<string, readonly [string, string, string, string]> = new Map([
  ['(', ['⎛', '⎜', '⎝', '⎜']], [')', ['⎞', '⎟', '⎠', '⎟']],
  ['[', ['⎡', '⎢', '⎣', '⎢']], [']', ['⎤', '⎥', '⎦', '⎥']],
  ['{', ['⎧', '⎪', '⎩', '⎨']], ['}', ['⎫', '⎪', '⎭', '⎬']],
  ['|', ['│', '│', '│', '│']], ['‖', ['‖', '‖', '‖', '‖']],
  ['⌈', ['⎡', '⎢', '⎢', '⎢']], ['⌉', ['⎤', '⎥', '⎥', '⎥']],
  ['⌊', ['⎢', '⎢', '⎣', '⎢']], ['⌋', ['⎥', '⎥', '⎦', '⎥']],
  ['⟨', ['╱', ' ', '╲', '⟨']], ['⟩', ['╲', ' ', '╱', '⟩']],
])

/** A delimiter as tall as `box`, drawn from bracket pieces. */
function tallDelimiter(char: string, box: Box): Box {
  const height = box.lines.length
  if (char === '') return { lines: Array.from({ length: height }, () => ''), baseline: box.baseline, width: 0 }
  const pieces = TALL_PIECES.get(char)
  if (height === 1 || pieces === undefined) {
    const lines = Array.from({ length: height }, (_, row) => (row === box.baseline ? char : ' '))
    return { lines, baseline: box.baseline, width: 1 }
  }
  const [top, middle, bottom, centreMark] = pieces
  const centreRow = Math.floor((height - 1) / 2)
  const lines = Array.from({ length: height }, (_, row) => {
    if (row === 0) return top
    if (row === height - 1) return bottom
    return row === centreRow ? centreMark : middle
  })
  return { lines, baseline: box.baseline, width: 1 }
}

function fence(open: string, box: Box, close: string): Box {
  return joinBoxes([tallDelimiter(open, box), box, tallDelimiter(close, box)])
}

function layoutGrid(env: string, rows: MathsRows): Box {
  const isAligned = !ENVIRONMENT_FENCES.has(env) && !CENTRED_ENVIRONMENTS.has(env)
  const cells = rows.map(row =>
    row.map((cell, column) => layoutList(isAligned && column % 2 === 1 ? anchorLeadingOperator(cell) : cell, false)),
  )
  const columns = Math.max(0, ...cells.map(row => row.length))
  const widths = Array.from({ length: columns }, (_, column) =>
    Math.max(0, ...cells.map(row => row[column]?.width ?? 0)),
  )
  const placed = cells.map(row => {
    const parts: Box[] = []
    widths.forEach((width, column) => {
      const cell = row[column] ?? textBox('')
      if (column > 0) parts.push(textBox(isAligned && column % 2 === 1 ? '' : MATRIX_GAP))
      parts.push(alignCell(cell, width, cellSide(env, isAligned, column)))
    })
    return joinBoxes(parts)
  })
  const height = placed.reduce((sum, row) => sum + row.lines.length, 0)
  const gridWidth = Math.max(0, ...placed.map(row => row.width))
  const grid: Box = {
    lines: placed.flatMap(row => row.lines.map(line => padTo(line, gridWidth))),
    baseline: Math.floor((height - 1) / 2),
    width: gridWidth,
  }
  const [open, close] = ENVIRONMENT_FENCES.get(env) ?? ['', '']
  const padded = open === '' && close === '' ? grid : joinBoxes([textBox(' '), grid, textBox(' ')])
  return fence(open, { ...padded, baseline: grid.baseline }, close)
}

// In aligned work the `&` sits just before the relation or operator, which
// then starts a cell with nothing to its left. An empty operand in front, as
// `&{}+` does in TeX, keeps it spaced as a relation or binary operator.
function anchorLeadingOperator(cell: MathsList): MathsList {
  const first = cell[0] === undefined ? null : classOf(cell[0])
  return first === 'rel' || first === 'bin' ? [{ kind: 'atom', text: '', cls: 'ord' }, ...cell] : cell
}

function cellSide(env: string, isAligned: boolean, column: number): 'left' | 'right' | 'centre' {
  if (isAligned) return column % 2 === 0 ? 'right' : 'left'
  return env.includes('cases') ? 'left' : 'centre'
}

// Environments whose rows are each centred rather than aligned on `&`.
const CENTRED_ENVIRONMENTS = new Set(['gather', 'gather*', 'gathered', 'multline', 'multline*', 'equation', 'equation*'])

function alignCell(cell: Box, width: number, side: 'left' | 'right' | 'centre'): Box {
  const spare = width - cell.width
  const left = side === 'right' ? spare : side === 'centre' ? Math.floor(spare / 2) : 0
  return { ...cell, lines: cell.lines.map(line => padTo(blank(left) + line, width)), width }
}
