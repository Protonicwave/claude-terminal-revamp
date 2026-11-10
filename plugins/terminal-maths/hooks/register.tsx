import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import { renderMathsInMarkdown } from './markdown-maths'

const PLUGIN = 'terminal-maths'
const DEFAULT_COLUMNS = 80
const EDITOR_TIMEOUT_MS = 15_000

// Change the shape tag if the stored value's type changes: it declines what
// an earlier version stored, which outlives a reload.
const lastAnswer = atom({ plugin: 'terminal-maths', key: 'lastAnswer' } as const, '', { shape: 'answer-1' })

const MATHS_GUIDANCE = [
  'Mathematics in replies: write it as LaTeX, with $...$ inline and $$...$$ on a line of its own for display equations.',
  'Use the aligned, cases and matrix environments for multi-line work, and \\text{...} for words inside maths.',
  'Never put maths in code spans or code blocks: the terminal draws LaTeX as Unicode, and /typeset opens a fully typeset copy.',
  'Write a literal dollar sign as \\$ in any reply that also contains maths.',
].join(' ')

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

  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined && e.answer !== '') await update($, lastAnswer, () => e.answer)
    return next(e)
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
    const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME'))
    if (home === undefined) return { text: 'Cannot typeset: neither USERPROFILE nor HOME is set.' }
    const path = `${home.replaceAll('\\', '/')}/.claude/typeset/latest.md`
    await $.fs.write(path, answer)
    const isWindows = (await $.env.get('OS')) === 'Windows_NT'
    // `code` is a batch file on Windows, which only cmd.exe can start.
    const argv = isWindows ? ['cmd.exe', '/d', '/c', 'code', '-r', path] : ['code', '-r', path]
    try {
      const { exitCode } = await $.process.run(argv, { timeoutMs: EDITOR_TIMEOUT_MS })
      if (exitCode === 0) return { text: `Opened the typeset reply in VS Code (${path}).` }
      return { text: `Saved ${path}, but \`code\` exited with ${exitCode}. Open the file in VS Code to see it typeset.` }
    } catch (error: unknown) {
      const reason = error instanceof Error ? error.message : String(error)
      return { text: `Saved ${path}, but could not start VS Code (${reason}). Open the file there to see it typeset.` }
    }
  })
}
