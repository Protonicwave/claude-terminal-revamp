// Unicode tables for TeX maths: symbols with their spacing class, script
// characters and alphabet styles. Data only; the parser and renderer read it.

export type AtomClass = 'ord' | 'op' | 'bin' | 'rel' | 'open' | 'close' | 'punct'

export type SymbolEntry = { readonly text: string; readonly cls: AtomClass }

function table(cls: AtomClass, pairs: Record<string, string>): Array<[string, SymbolEntry]> {
  return Object.entries(pairs).map(([name, text]) => [name, { text, cls }])
}

const ORDINARY = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ϵ', varepsilon: 'ε',
  zeta: 'ζ', eta: 'η', theta: 'θ', vartheta: 'ϑ', iota: 'ι', kappa: 'κ',
  lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', omicron: 'ο', pi: 'π', varpi: 'ϖ',
  rho: 'ρ', varrho: 'ϱ', sigma: 'σ', varsigma: 'ς', tau: 'τ', upsilon: 'υ',
  phi: 'ϕ', varphi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π',
  Sigma: 'Σ', Upsilon: 'Υ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
  hbar: 'ℏ', hslash: 'ℏ', ell: 'ℓ', Re: 'ℜ', Im: 'ℑ', aleph: 'ℵ', wp: '℘',
  partial: '∂', nabla: '∇', infty: '∞', emptyset: '∅', varnothing: '∅',
  prime: '′', angle: '∠', triangle: '△', forall: '∀', exists: '∃',
  nexists: '∄', neg: '¬', lnot: '¬', top: '⊤', bot: '⊥', degree: '°',
  dagger: '†', ddagger: '‡', ldots: '…', cdots: '⋯', vdots: '⋮', ddots: '⋱',
  dots: '…', dotsc: '…', dotsb: '⋯', checkmark: '✓', square: '□', Box: '□',
  diamond: '⋄', mho: '℧', Angstrom: 'Å', imath: 'ı', jmath: 'ȷ',
  vert: '|', Vert: '‖', '|': '‖', '#': '#', '$': '$', '%': '%', '&': '&',
  _: '_', infin: '∞', surd: '√', flat: '♭', natural: '♮', sharp: '♯',
}

const BINARY = {
  pm: '±', mp: '∓', times: '×', div: '÷', cdot: '·', ast: '∗', star: '⋆',
  circ: '∘', bullet: '∙', oplus: '⊕', ominus: '⊖', otimes: '⊗', oslash: '⊘',
  odot: '⊙', cup: '∪', cap: '∩', sqcup: '⊔', sqcap: '⊓', vee: '∨',
  wedge: '∧', lor: '∨', land: '∧', setminus: '∖', wr: '≀', uplus: '⊎',
  amalg: '⨿', triangleleft: '◁', triangleright: '▷', bigtriangleup: '△',
}

const RELATION = {
  leq: '≤', le: '≤', geq: '≥', ge: '≥', neq: '≠', ne: '≠', approx: '≈',
  simeq: '≃', sim: '∼', cong: '≅', equiv: '≡', propto: '∝', ll: '≪', gg: '≫',
  lesssim: '≲', gtrsim: '≳', prec: '≺', succ: '≻', preceq: '⪯', succeq: '⪰',
  subset: '⊂', supset: '⊃', subseteq: '⊆', supseteq: '⊇', subsetneq: '⊊',
  in: '∈', notin: '∉', ni: '∋', mid: '∣', parallel: '∥', perp: '⊥',
  vdash: '⊢', dashv: '⊣', models: '⊨', to: '→', rightarrow: '→',
  leftarrow: '←', gets: '←', leftrightarrow: '↔', Rightarrow: '⇒',
  Leftarrow: '⇐', Leftrightarrow: '⇔', implies: '⟹', impliedby: '⟸',
  iff: '⟺', mapsto: '↦', longrightarrow: '⟶', longleftarrow: '⟵',
  longleftrightarrow: '⟷', Longrightarrow: '⟹', Longleftarrow: '⟸',
  Longleftrightarrow: '⟺', longmapsto: '⟼', uparrow: '↑', downarrow: '↓',
  updownarrow: '↕', Uparrow: '⇑', Downarrow: '⇓', nearrow: '↗', searrow: '↘',
  swarrow: '↙', nwarrow: '↖', hookrightarrow: '↪', hookleftarrow: '↩',
  rightleftharpoons: '⇌', leftrightharpoons: '⇋', rightharpoonup: '⇀',
  doteq: '≐', triangleq: '≜', coloneqq: '≔', approxeq: '≊', asymp: '≍',
  nleq: '≰', ngeq: '≱', nsim: '≁', ncong: '≇', nsubseteq: '⊈', nmid: '∤',
  nparallel: '∦', sqsubseteq: '⊑', sqsupseteq: '⊒', vDash: '⊨', Vdash: '⊩',
  therefore: '∴', because: '∵', colon: ':', bowtie: '⋈',
}

const OPENING = {
  langle: '⟨', lceil: '⌈', lfloor: '⌊', lvert: '|', lVert: '‖', '{': '{',
  lbrace: '{', lbrack: '[',
}

const CLOSING = {
  rangle: '⟩', rceil: '⌉', rfloor: '⌋', rvert: '|', rVert: '‖', '}': '}',
  rbrace: '}', rbrack: ']',
}

export const SYMBOLS: ReadonlyMap<string, SymbolEntry> = new Map([
  ...table('ord', ORDINARY),
  ...table('bin', BINARY),
  ...table('rel', RELATION),
  ...table('open', OPENING),
  ...table('close', CLOSING),
])

/** Large operators; `limits` puts scripts above and below in display maths. */
export const LARGE_OPERATORS: ReadonlyMap<string, { text: string; limits: boolean }> = new Map(
  Object.entries({
    sum: '∑', prod: '∏', coprod: '∐', bigcup: '⋃', bigcap: '⋂', bigoplus: '⨁',
    bigotimes: '⨂', bigodot: '⨀', bigvee: '⋁', bigwedge: '⋀', bigsqcup: '⨆',
  })
    .map(([name, text]): [string, { text: string; limits: boolean }] => [name, { text, limits: true }])
    .concat(
      Object.entries({ int: '∫', iint: '∬', iiint: '∭', oint: '∮', oiint: '∯' }).map(
        ([name, text]): [string, { text: string; limits: boolean }] => [name, { text, limits: false }],
      ),
    ),
)

const LIMIT_NAMES = ['lim', 'max', 'min', 'sup', 'inf', 'det', 'Pr', 'gcd', 'argmax', 'argmin']
const PLAIN_NAMES = [
  'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'arcsin', 'arccos', 'arctan', 'sinh',
  'cosh', 'tanh', 'coth', 'log', 'ln', 'lg', 'exp', 'dim', 'ker', 'deg', 'arg',
  'hom', 'tr', 'Tr',
]

/** Operator names set upright, such as `\sin`; `limits` as for large operators. */
export const OPERATOR_NAMES: ReadonlyMap<string, { text: string; limits: boolean }> = new Map([
  ...LIMIT_NAMES.map((name): [string, { text: string; limits: boolean }] => [name, { text: name, limits: true }]),
  ['limsup', { text: 'lim sup', limits: true }],
  ['liminf', { text: 'lim inf', limits: true }],
  ...PLAIN_NAMES.map((name): [string, { text: string; limits: boolean }] => [name, { text: name, limits: false }]),
])

/** Single characters typed directly in maths mode and the class TeX gives them. */
export const CHARACTER_CLASSES: ReadonlyMap<string, SymbolEntry> = new Map([
  ['+', { text: '+', cls: 'bin' }],
  ['-', { text: '−', cls: 'bin' }],
  ['*', { text: '∗', cls: 'bin' }],
  ['=', { text: '=', cls: 'rel' }],
  ['<', { text: '<', cls: 'rel' }],
  ['>', { text: '>', cls: 'rel' }],
  [':', { text: ':', cls: 'rel' }],
  [',', { text: ',', cls: 'punct' }],
  [';', { text: ';', cls: 'punct' }],
  ['(', { text: '(', cls: 'open' }],
  ['[', { text: '[', cls: 'open' }],
  [')', { text: ')', cls: 'close' }],
  [']', { text: ']', cls: 'close' }],
  ['!', { text: '!', cls: 'close' }],
])

/** Negated forms for `\not` followed by a relation. */
export const NEGATIONS: ReadonlyMap<string, string> = new Map([
  ['=', '≠'], ['∈', '∉'], ['≡', '≢'], ['∼', '≁'], ['≤', '≰'], ['≥', '≱'],
  ['⊂', '⊄'], ['⊃', '⊅'], ['⊆', '⊈'], ['⊇', '⊉'], ['<', '≮'], ['>', '≯'],
  ['≈', '≉'], ['≅', '≇'], ['∣', '∤'], ['∥', '∦'],
])

export type AccentKind = 'hat' | 'bar' | 'vec' | 'dot' | 'ddot' | 'tilde' | 'underline'

export const ACCENTS: ReadonlyMap<string, AccentKind> = new Map([
  ['hat', 'hat'], ['widehat', 'hat'], ['bar', 'bar'], ['overline', 'bar'],
  ['vec', 'vec'], ['overrightarrow', 'vec'], ['dot', 'dot'], ['ddot', 'ddot'],
  ['tilde', 'tilde'], ['widetilde', 'tilde'], ['underline', 'underline'],
])

/** Combining mark per accent, placed after the character it decorates. */
export const COMBINING: Readonly<Record<AccentKind, string>> = {
  hat: '̂', bar: '̅', vec: '⃗', dot: '̇', ddot: '̈',
  tilde: '̃', underline: '̲',
}

/** The glyph drawn on its own row above (or below, for underline) a wide base. */
export const ACCENT_ROW_GLYPH: Readonly<Record<AccentKind, string>> = {
  hat: '^', bar: '─', vec: '→', dot: '·', ddot: '¨', tilde: '~', underline: '─',
}

function zip(from: string, to: string): ReadonlyMap<string, string> {
  const target = [...to]
  return new Map([...from].map((char, index) => [char, target.at(index) ?? '']))
}

export const SUPERSCRIPTS = zip(
  '0123456789+−=()ni' + 'abcdefghjklmoprstuvwxyz' + 'ABDEGHIJKLMNOPRTUVW' + 'αβγδεθιφχ',
  '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ' + 'ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ' + 'ᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ' + 'ᵅᵝᵞᵟᵋᶿᶥᵠᵡ',
)

export const SUBSCRIPTS = zip(
  '0123456789+−=()' + 'aehijklmnoprstuvx' + 'βγρφχ',
  '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎' + 'ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ' + 'ᵦᵧᵨᵩᵪ',
)

/** Characters that already sit high, so a superscript of only these is appended as is. */
export const RAISED_MARKS: ReadonlySet<string> = new Set(['′', '″', '‴', '†', '‡', '∗', '*', '∘', '°'])

export type AlphabetStyle = 'blackboard' | 'calligraphic' | 'fraktur' | 'bold'

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

function alphabet(start: number, exceptions: Record<string, string>): ReadonlyMap<string, string> {
  return new Map(
    [...LETTERS].map((letter, index) => [letter, exceptions[letter] ?? String.fromCodePoint(start + index)]),
  )
}

const DOUBLE_STRUCK_DIGITS = new Map([...'0123456789'].map((d, i) => [d, String.fromCodePoint(0x1d7d8 + i)]))
const BOLD_DIGITS = new Map([...'0123456789'].map((d, i) => [d, String.fromCodePoint(0x1d7ce + i)]))

// The Letterlike Symbols block holds some letters that the Mathematical
// Alphanumeric block leaves as unassigned holes.
export const ALPHABETS: Readonly<Record<AlphabetStyle, ReadonlyMap<string, string>>> = {
  blackboard: new Map([
    ...alphabet(0x1d538, { C: 'ℂ', H: 'ℍ', N: 'ℕ', P: 'ℙ', Q: 'ℚ', R: 'ℝ', Z: 'ℤ' }),
    ...DOUBLE_STRUCK_DIGITS,
  ]),
  calligraphic: alphabet(0x1d49c, {
    B: 'ℬ', E: 'ℰ', F: 'ℱ', H: 'ℋ', I: 'ℐ', L: 'ℒ', M: 'ℳ', R: 'ℛ', e: 'ℯ', g: 'ℊ', o: 'ℴ',
  }),
  fraktur: alphabet(0x1d504, { C: 'ℭ', H: 'ℌ', I: 'ℑ', R: 'ℜ', Z: 'ℨ' }),
  bold: new Map([...alphabet(0x1d400, {}), ...BOLD_DIGITS]),
}

export const FONT_COMMANDS: ReadonlyMap<string, AlphabetStyle> = new Map([
  ['mathbb', 'blackboard'], ['Bbb', 'blackboard'], ['mathcal', 'calligraphic'],
  ['mathscr', 'calligraphic'], ['mathfrak', 'fraktur'], ['mathbf', 'bold'],
  ['boldsymbol', 'bold'], ['bm', 'bold'],
])
