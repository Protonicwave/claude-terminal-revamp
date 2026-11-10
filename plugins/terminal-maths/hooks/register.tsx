import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { renderMathsInMarkdown } from './markdown-maths'

const PLUGIN = 'terminal-maths'
const DEFAULT_COLUMNS = 80
const EDITOR_TIMEOUT_MS = 15_000
const TYPESET_FILE = '.claude/typeset/latest.md'

// Change the shape tag if the stored value's type changes: it declines what
// an earlier version stored, which outlives a reload. The plugin name is
// spelled out because the engine reads state references as literals.
const lastAnswer = atom({ plugin: 'terminal-maths', key: 'lastAnswer' } as const, '', { shape: 'answer-1' })

const MATHS_GUIDANCE = [
  'Mathematics in replies: write it as LaTeX, with $...$ inline and $$...$$ on a line of its own for display equations.',
  'Use the aligned, cases and matrix environments for multi-line work, and \\text{...} for words inside maths.',
  'Never put maths in code spans or code blocks: the terminal draws LaTeX as Unicode, and /typeset opens a fully typeset copy.',
  'Write a literal dollar sign as \\$ in any reply that also contains maths.',
].join(' ')

type TypesetLocation = { readonly home: string; readonly path: string }

async function typesetLocation($: EngineInterface): Promise<TypesetLocation | undefined> {
  const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME'))
  if (home === undefined) return undefined
  return { home, path: `${home.replaceAll('\\', '/')}/${TYPESET_FILE}` }
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'typeset',
      description: 'Open the last reply, fully typeset, in a VS Code Markdown preview',
    })
    return next(e)
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    const section = { id: `${PLUGIN}:maths`, text: MATHS_GUIDANCE, scope: 'session' } as const
    return { ...composed, sections: [...composed.sections, section] }
  })

  // An open preview reloads the file when it changes on disk, so writing
  // every main reply keeps the preview current without /typeset.
  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined || e.answer === '') return next(e)
    await update($, lastAnswer, () => e.answer)
    const result = await next(e)
    const location = await typesetLocation($)
    if (location === undefined) return result
    try {
      await $.fs.write(location.path, e.answer)
    } catch (error: unknown) {
      // A failed write must not fail the turn: /typeset writes the file again
      // when it runs. Each toast replaces this plugin's last, so a failure
      // that repeats every turn does not pile up.
      $.ui.toast(`Could not update the typeset preview: ${describeError(error)}`)
    }
    return result
  })

  // The VS Code panel and the desktop app typeset LaTeX themselves, so only
  // the terminal's drawing is rewritten.
  on('ui.render', { component: 'AssistantMessage' }, ($, e, next) => {
    if (e.surface !== 'terminal') return next(e)
    const text = renderMathsInMarkdown(e.props.text, e.viewport?.columns ?? DEFAULT_COLUMNS)
    return next(text === e.props.text ? e : { ...e, props: { ...e.props, text } })
  })

  on('command.run', { command: 'typeset' }, async $ => {
    const answer = await read($, lastAnswer)
    if (answer === '') return { text: 'There is no reply to typeset yet.' }
    const location = await typesetLocation($)
    if (location === undefined) return { text: 'Cannot typeset: neither USERPROFILE nor HOME is set.' }
    const { home, path } = location
    await $.fs.write(path, answer)
    const isWindows = (await $.env.get('OS')) === 'Windows_NT'
    // `code` is a batch file on Windows, which only cmd.exe can start. The
    // path goes relative to the home folder, so no character of the home
    // path (an `&` or a `%`) ever reaches cmd.exe's parser.
    const argv = isWindows ? ['cmd.exe', '/d', '/c', 'code', '-r', TYPESET_FILE] : ['code', '-r', TYPESET_FILE]
    try {
      const { exitCode } = await $.process.run(argv, { cwd: home, timeoutMs: EDITOR_TIMEOUT_MS })
      if (exitCode === 0) return { text: `Opened the typeset reply in VS Code (${path}).` }
      return { text: `Saved ${path}, but \`code\` exited with ${exitCode}. Open the file in VS Code to see it typeset.` }
    } catch (error: unknown) {
      return {
        text: `Saved ${path}, but could not start VS Code (${describeError(error)}). Open the file there to see it typeset.`,
      }
    }
  })
}
