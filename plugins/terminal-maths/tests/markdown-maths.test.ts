import { describe, expect, test } from 'claude-code/testing'

import { renderMathsInMarkdown } from '../hooks/markdown-maths'
import { SUBSCRIPTS, SUPERSCRIPTS } from '../hooks/maths-symbols'

// The test environment has a console; the plugin's type library deliberately omits it.
declare const console: { log: (message: string) => void }

const WIDE = 100
const render = (markdown: string): string => renderMathsInMarkdown(markdown, WIDE)
const block = (...lines: string[]): string => ['```', ...lines, '```'].join('\n')

const INLINE: ReadonlyArray<readonly [string, string, string]> = [
  ['scripts and Greek', String.raw`$E = mc^2$, $\hbar\omega$, $\alpha_i^2 + \beta_{ij}$`, 'E = mc², ℏω, αᵢ² + βᵢⱼ'],
  ['unmappable script falls back', String.raw`$a_{\mu\nu}$`, 'a\\_(μν)'],
  ['raised marks append', String.raw`$\psi^\dagger$, $f'(x)$, $f''$`, 'ψ†, f′(x), f″'],
  ['fraction brackets', String.raw`$\frac{a+b}{2m}$`, '(a+b)/(2m)'],
  ['fraction of atoms', String.raw`$\frac{1}{2}$`, '1/2'],
  ['nested scripts in fraction', String.raw`$e^{-\frac{(x-\mu)^2}{2\sigma^2}}$`, 'e^(−(x−μ)²/(2σ²))'],
  ['roots', String.raw`$\sqrt{2\pi}$, $\sqrt[3]{x}$, $\sqrt[n]{y}$, $\sqrt[k]{z}$`, '√(2π), ∛x, ⁿ√y, ᵏ√z'],
  ['root with unmappable index', String.raw`$\sqrt[\mu]{z}$`, '^μ√z'],
  ['alphabets', String.raw`$\mathbb{R}^n$, $\mathcal{L}$, $\mathbf{v}$, $\mathfrak{g}$`, 'ℝⁿ, ℒ, 𝐯, 𝔤'],
  ['accents', String.raw`$\vec{v} \cdot \hat{n}$, $\bar{z}$, $\overline{AB}$, $\tilde{x}$`, 'v⃗ · n̂, z̅, A̅B̅, x̃'],
  ['wide accent', String.raw`$\vec{AB}$`, 'vec(AB)'],
  ['operator names', String.raw`$\sin x + \lim_{x \to 0} f$`, 'sin x + lim\\_(x→0) f'],
  ['starred operator name', String.raw`$\operatorname*{argmax}_\theta L$`, 'argmax\\_θ L'],
  ['large operators', String.raw`$\sum_{i=1}^n x_i$`, '∑ᵢ₌₁ⁿ xᵢ'],
  ['delimiters escape pipes', String.raw`$\langle \psi | \phi \rangle$, $\left| x \right|$`, '⟨ψ\\|ϕ⟩, \\|x\\|'],
  ['unary minus', String.raw`$-x + (-y) = -1$`, '−x + (−y) = −1'],
  ['negation', String.raw`$a \not= b$, $x \not\in S$, $p \not\models q$`, 'a ≠ b, x ∉ S, p ⊭ q'],
  ['text keeps spaces', String.raw`$x \text{ if } y$`, 'x if y'],
  ['spacing commands', String.raw`$a\,b\quad c\!d$`, 'a b  cd'],
  ['binomial', String.raw`$\binom{n}{k}$`, 'C(n, k)'],
  ['modulus', String.raw`$a \equiv b \pmod{n}$, $a \bmod b$`, 'a ≡ b (mod n), a mod b'],
  ['matrix inline', String.raw`$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$`, '(a b; c d)'],
  ['plain matrix inline', String.raw`$\begin{matrix} 1 & 0 \end{matrix}$`, String.raw`\[1 0\]`],
  ['cases inline', String.raw`$\begin{cases} 1 & x > 0 \\ 0 & \text{otherwise} \end{cases}$`, String.raw`{ 1, x \> 0; 0, otherwise`],
  ['aligned inline', String.raw`$\begin{aligned} a &= b \\ &= c \end{aligned}$`, 'a = b; = c'],
  ['ignored commands', String.raw`$\displaystyle x \label{eq} \color{red} y$`, 'xy'],
  ['coloured text', String.raw`$\textcolor{red}{x}$`, 'x'],
  ['sized delimiters', String.raw`$\bigl( x \bigr)$, $a \bigm| b$`, '(x), a \\| b'],
  ['overset and underset', String.raw`$\overset{!}{=}$, $\underset{n}{x}$`, '=^!, xₙ'],
  ['unknown command kept', String.raw`$\foo x$`, '\\\\foo x'],
  ['escaped symbols', String.raw`$50\% \{a\}$`, '50%{a}'],
  ['paren delimiters', String.raw`\(x^2\)`, 'x²'],
  ['middle bar', String.raw`$\left\{ x \middle| x > 0 \right\}$`, String.raw`{x \| x \> 0}`],
  ['empty superscript base', '$' + String.raw`{}^{14}C$`, '¹⁴C'],
  ['tilde space', String.raw`$a~b$`, 'a b'],
  ['ceiling', String.raw`$\lceil x \rceil$`, '⌈x⌉'],
  ['row break at top level', String.raw`$a \\ b$`, 'a; b'],
  ['array environment', String.raw`$\begin{array}{cc} 1 & 2 \end{array}$`, String.raw`\[1 2\]`],
  ['top-level ampersand aligns', '$a & b$', 'ab'],
  ['text with nested braces and escapes', String.raw`$\text{a{b}c, 50\% off}$`, 'a{b}c, 50% off'],
  ['four primes', "$f''''$", 'f′′′′'],
  ['script with no base', '$^3He$', '³He'],
  ['styled non-letters', String.raw`$\mathbf{a+1}$, $\mathcal{x1}$`, '𝐚 + 𝟏, 𝓍1'],
  ['negated non-relation', String.raw`$\not{=}$`, '̸'],
  ['plain big delimiter', String.raw`$\big( x \big)$`, '(x)'],
  ['roots as operands', String.raw`$\frac{1}{\sqrt{2}} + \frac{1}{\sqrt[3]{2}} + \frac{1}{\sqrt[4]{2}}$`, '1/√2 + 1/∛2 + 1/∜2'],
  ['unbalanced bracket operand', String.raw`$\frac{(a}{b}$`, '((a)/b'],
  ['powered fraction', String.raw`$\frac{a}{b}^2$`, '(a/b)²'],
  ['right cases', String.raw`$\begin{rcases} a \end{rcases}$`, 'a }'],
]

const UNCHANGED: ReadonlyArray<readonly [string, string]> = [
  ['prices', 'Prices: $5 and $10, or $3.50 each.'],
  ['escaped dollars', String.raw`Costs \$4 or \$5 today.`],
  ['code spans', 'Run `echo $HOME$` then `$x$`.'],
  ['dollar inside code after a price', 'Pay $10 then run `a$b`.'],
  ['space after opening', 'A $ x$ is not maths.'],
  ['space before closing', 'A $x $ is not maths.'],
  ['digit after closing', 'From $x$5 onwards.'],
  ['parse error', String.raw`Bad $\frac{a}$ stays.`],
  ['unclosed brace', String.raw`Bad $\sqrt{x$ stays.`],
  ['unclosed display while streaming', String.raw`Working: $$\frac{a}{b}`],
  ['unclosed paren delimiter', String.raw`Open \(x but never closed.`],
  ['empty display', 'Nothing $$  $$ here.'],
  ['display across a blank line', 'Start $$x\n\ny$$ end.'],
  ['unknown delimiter', String.raw`$\left\foo x \right)$`],
  ['double subscript', String.raw`$x_1_2$`],
  ['mismatched environment', String.raw`$\begin{matrix} a \end{pmatrix}$`],
  ['trailing backslash', '$x\\$'],
  ['stray closing brace', '$a}b$'],
  ['backslash at the end of maths', String.raw`See \(x\\) here.`],
  ['text without braces', String.raw`$\text x$`],
  ['unclosed text', String.raw`$\text{abc$`],
  ['missing delimiter', String.raw`$\left$`],
  ['nesting through bare arguments', `$${'\\sqrt'.repeat(30)}x$`],
  ['no maths at all', 'Plain *markdown* text.'],
]

describe('inline maths', () => {
  for (const [name, source, expected] of INLINE) {
    test(name, () => {
      expect(render(source)).toBe(expected)
    })
  }
})

describe('text left as written', () => {
  for (const [name, source] of UNCHANGED) {
    test(name, () => {
      expect(render(source)).toBe(source)
    })
  }
})

describe('code', () => {
  test('a fenced block is never converted, and maths after it is', () => {
    const source = ['```tex', '$x^2$', '```', '$y^2$'].join('\n')
    expect(render(source)).toBe(['```tex', '$x^2$', '```', 'y²'].join('\n'))
  })

  test('a tilde fence closes only on a matching fence', () => {
    const source = ['~~~', '$a$', '```', '$b$', '~~~', '$c$'].join('\n')
    expect(render(source)).toBe(['~~~', '$a$', '```', '$b$', '~~~', 'c'].join('\n'))
  })

  test('an unclosed code span leaves its backticks and converts the rest', () => {
    expect(render('A ` then $x^2$')).toBe('A ` then x²')
  })
})

describe('display maths', () => {
  test('a fraction sum is drawn in two dimensions', () => {
    const source = String.raw`$$\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}.$$`
    expect(render(source)).toBe(
      block('     ∞   1      π²', '     ∑  ──── = ────.', '    n=1  n²     6').replace(/^ {2}/gm, ''),
    )
  })

  test('an integral raises its limits and draws a short root inline', () => {
    const source = String.raw`$$\int_0^\infty e^{-x^2} \, dx = \frac{\sqrt{\pi}}{2}$$`
    expect(render(source)).toBe(block('   ∞  −x²       √π', '  ∫  e    dx = ────', '   0            2'))
  })

  test('tall brackets wrap a fraction', () => {
    const source = String.raw`$$\left( \frac{a}{b} \right)^2$$`
    expect(render(source)).toBe(block('  ⎛ a ⎞²', '  ⎜───⎟', '  ⎝ b ⎠'))
  })

  test('matrices and cases get tall fences', () => {
    const source = String.raw`$$\begin{bmatrix} a & b \\ c & d \end{bmatrix} \begin{cases} x & y \\ z & w \\ u & v \end{cases}$$`
    expect(render(source)).toBe(block('          ⎧ x  y', '  ⎡ a  b ⎤⎨ z  w', '  ⎣ c  d ⎦⎩ u  v'))
  })

  test('aligned equations line up on the relation', () => {
    const source = String.raw`\[\begin{aligned} f(x) &= (x+1)^2 \\ &= x^2 + 2x + 1 \end{aligned}\]`
    expect(render(source)).toBe(block('  f(x) = (x + 1)²', '       = x² + 2x + 1'))
  })

  test('rows without an environment stack as aligned rows', () => {
    expect(render(String.raw`$$a &= b \\ c &= d$$`)).toBe(block('  a = b', '  c = d'))
  })

  test('a long root gets an overbar and other environments align', () => {
    const source = String.raw`$$\sqrt{x+1} + \begin{vmatrix} \frac{1}{2} & 0 \end{vmatrix}$$`
    expect(render(source)).toBe(block('   ───   │  1     │', '  √x+1 + │ ───  0 │', '         │  2     │'))
  })

  test('raised scripts sit beside a tall base', () => {
    const source = String.raw`$$\left( \frac{1}{2} \right)_{\mu\nu}^{\alpha\omega}$$`
    expect(render(source)).toBe(block('       αω', '  ⎛ 1 ⎞', '  ⎜───⎟', '  ⎝ 2 ⎠', '       μν'))
  })

  test('accents over wide bases take their own row', () => {
    const source = String.raw`$$\overline{z+1} \quad \underline{ab} \quad \hat{xy} \quad \vec{\frac{a}{b}}$$`
    expect(render(source)).toBe(block('                →', '  ───      ^    a', '  z+1  ab  xy  ───', '       ──       b'))
  })

  test('limits commands move integral bounds above and below', () => {
    const source = String.raw`$$\int\limits_0^1 x \, dx + \sum\nolimits_{i} \frac{a}{b}$$`
    expect(render(source)).toBe(block('  1            a', '  ∫ x dx + ∑ᵢ ───', '  0            b'))
  })

  test('row spacing after a line break is skipped', () => {
    expect(render(String.raw`$$a \\[2pt] b$$`)).toBe(block('  a', '  b'))
  })

  test('an unclosed row spacing is left as written', () => {
    const source = String.raw`$$a \\[2pt b$$`
    expect(render(source)).toBe(source)
  })

  test('a braced group and a one-letter accent sit beside a fraction', () => {
    expect(render('$$' + String.raw`{\hat{x}} = \frac{a}{b}$$`)).toBe(block('       a', '  x̂ = ───', '       b'))
  })

  test('a delimiter with no tall form sits on the baseline', () => {
    expect(render(String.raw`$$\left/ \frac{a}{b} \right.$$`)).toBe(block('    a', '  /───', '    b'))
  })

  test('a limit sits under its operator', () => {
    expect(render(String.raw`$$\lim_{x \to 0} \frac{a}{b}$$`)).toBe(block('       a', '  lim ───', '  x→0  b'))
  })

  test('a trailing row break adds no empty row', () => {
    expect(render(String.raw`$$a \\ $$`)).toBe(block('  a'))
  })

  test('a root of a fraction, with and without a degree', () => {
    expect(render(String.raw`$$\sqrt[3]{\frac{a}{b}} \sqrt[n]{\frac{a}{b}}$$`)).toBe(
      block('   ───  ───', '  │ a  │ a', '  │─── │───', '  ∛ b ⁿ√ b'),
    )
  })

  test('a lone subscript is lowered beside a tall base', () => {
    expect(render(String.raw`$$\left( \frac{a}{b} \right)_{\mu}$$`)).toBe(block('  ⎛ a ⎞', '  ⎜───⎟', '  ⎝ b ⎠', '       μ'))
  })

  test('aligned rows starting with an operator keep their spacing', () => {
    const source = String.raw`$$\begin{aligned} a &+ b \\ &- c \end{aligned}$$`
    expect(render(source)).toBe(block('  a + b', '    − c'))
  })

  test('a ragged matrix pads its short rows', () => {
    const source = String.raw`$$\begin{pmatrix} a & b \\ c \end{pmatrix}$$`
    expect(render(source)).toBe(block('  ⎛ a  b ⎞', '  ⎝ c    ⎠'))
  })

  test('a binomial stacks inside tall parentheses', () => {
    expect(render(String.raw`$$\binom{n}{k}$$`)).toBe(block('  ⎛n⎞', '  ⎝k⎠'))
  })

  test('other tall delimiters', () => {
    const source = String.raw`$$\left\langle \frac{a}{b} \right\rangle \left\lfloor \frac{a}{b} \right. \left\| \frac{a}{b} \right\|$$`
    expect(render(source)).toBe(block('  ╱ a ╲⎢ a ‖ a ‖', '  ⟨───⟩⎢───‖───‖', '  ╲ b ╱⎣ b ‖ b ‖'))
  })

  test('a display keeps the indentation of a list item and trailing punctuation', () => {
    const source = '- step\n  $$\\frac{a}{b}$$,\n- next'
    expect(render(source)).toBe('- step\n  ```\n     a\n    ───,\n     b\n  ```\n- next')
  })

  test('display maths sharing its line with text is drawn inline', () => {
    expect(render(String.raw`See $$\frac{a}{b}$$ here.`)).toBe('See a/b here.')
  })

  test('display maths too wide for the terminal is drawn inline', () => {
    const source = String.raw`$$\frac{a}{b} + \frac{c}{d}$$`
    expect(renderMathsInMarkdown(source, 8)).toBe('a/b + c/d')
  })

  test('display maths that does not parse is left as written', () => {
    const source = String.raw`$$\frac{a}$$`
    expect(render(source)).toBe(source)
  })
})

describe('limits', () => {
  test('a span over the source limit is left as written', () => {
    const source = `$${'x'.repeat(4001)}$`
    expect(render(source)).toBe(source)
  })

  test('nesting deeper than the limit is left as written', () => {
    const source = `$${'{'.repeat(30)}x${'}'.repeat(30)}$`
    expect(render(source)).toBe(source)
  })

  test('a 10,000-character reply with 200 spans renders well inside the budget', () => {
    const paragraph = String.raw`The energy $E_n = \frac{n^2 \pi^2 \hbar^2}{2 m L^2}$ grows. `
    const reply = paragraph.repeat(200)
    const runs = 50
    for (let run = 0; run < 10; run += 1) render(reply)
    const timings: number[] = []
    for (let run = 0; run < runs; run += 1) {
      const started = performance.now()
      render(reply)
      timings.push(performance.now() - started)
    }
    const perRunMs = timings.sort((a, b) => a - b)[Math.floor(runs / 2)] ?? Number.POSITIVE_INFINITY
    // The figure is printed so a run shows it beside the budget.
    console.log(`median render of ${reply.length} characters: ${perRunMs.toFixed(2)} ms (budget 5 ms)`)
    // Five times the budget, so a slow machine does not fail the suite.
    expect(perRunMs).toBeLessThan(25)
  })
})

describe('symbol tables', () => {
  test('every script character has a Unicode form', () => {
    for (const table of [SUPERSCRIPTS, SUBSCRIPTS]) expect([...table.values()].includes('')).toBe(false)
  })
})
