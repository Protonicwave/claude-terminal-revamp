import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'

const REPLY = {
  plugin: 'terminal-maths',
  component: 'AssistantMessage',
  requestId: 'message-1',
  props: { text: 'Energy $E = mc^2$.', isFirstOfReply: true },
} as const

const TURN = { durationMs: 10, isAborted: false, turnId: 'turn-1', reason: 'answer' } as const
const TYPESET = {
  command: 'typeset',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 120 },
} as const
const COMPOSE = {
  model: 'claude-opus-5-5',
  promptModel: 'claude-opus-5-5',
  surfaces: ['terminal'],
  tools: [],
  outputStyle: null,
  traits: [],
} as const
const RAN = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } as const
const HOME = 'C:\\Users\\someone'
const LATEST = 'C:/Users/someone/.claude/typeset/latest.md'

// These hooks stand for the engine: the environment variables given, a file
// system held in memory and the toast stack.
function stubEngine(on: On, env: Readonly<Record<string, string>>) {
  const files = new Map<string, string>()
  const toasts: string[] = []
  on('turn.complete', () => ({ text: '' }))
  on('env.get', (_, e) => ({ value: env[e.name] }))
  on('fs.write', (_, e) => {
    // The engine hands the hook the path in the platform's own form.
    files.set(e.path.replaceAll('\\', '/'), e.text)
    return { value: undefined }
  })
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  return { files, toasts }
}

test('the terminal draws maths as Unicode; graphical surfaces get the LaTeX', async ($, on) => {
  // This hook stands for the engine, which draws whatever text reaches it.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{e.component === 'AssistantMessage' ? e.props.text : ''}</Text>
  })

  for (const [surface, expected] of [
    ['terminal', 'Energy E = mc².'],
    ['vscode', 'Energy $E = mc^2$.'],
    ['desktop', 'Energy $E = mc^2$.'],
  ] as const) {
    const ui = await $.ui.mount({ ...REPLY, surface })
    expect((await ui.find({ type: 'Text' }))?.text).toBe(expected)
    await ui.unmount()
  }
})

test('a reply without maths reaches the engine unchanged', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>{e.component === 'AssistantMessage' ? e.props.text : ''}</Text>
  })

  const ui = await $.ui.mount({ ...REPLY, surface: 'terminal', props: { ...REPLY.props, text: 'No maths.' } })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('No maths.')
  await ui.unmount()
})

test('the system prompt gains the maths section last', async ($, on) => {
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'Hello.', scope: 'shared' }] }))

  const { sections } = await $.prompt.compose(COMPOSE)

  expect(sections.map(section => section.id)).toEqual(['intro', 'terminal-maths:maths'])
  expect(sections.at(-1)?.text).toMatch(/\$\$\.\.\.\$\$/)
})

test('/typeset writes the last main reply and opens it in VS Code', async ($, on) => {
  const written: Array<{ path: string; text: string }> = []
  const started: Array<{ argv: string[]; cwd: string | undefined }> = []
  on('turn.complete', () => ({ text: '' }))
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? HOME : e.name === 'OS' ? 'Windows_NT' : undefined }))
  on('fs.write', (_, e) => {
    written.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('process.run', (_, e) => {
    started.push({ argv: [...e.argv], cwd: e.init?.cwd })
    return { value: RAN }
  })

  await $.turn.complete({ ...TURN, answer: 'Main $x^2$.' })
  await $.turn.complete({ ...TURN, turnId: 'turn-2', agentId: 'agent-1', answer: 'Subagent report.' })
  const result = await $.command.run(TYPESET)

  // The turn writes the main reply, and /typeset writes it again before opening it.
  expect(written.map(file => file.path.replaceAll('\\', '/'))).toEqual([LATEST, LATEST])
  expect(written.map(file => file.text)).toEqual(['Main $x^2$.', 'Main $x^2$.'])
  // The path is relative to the home folder, so nothing from it reaches cmd.exe's parser.
  expect(started).toEqual([
    { argv: ['cmd.exe', '/d', '/c', 'code', '-r', '.claude/typeset/latest.md'], cwd: HOME },
  ])
  expect(result.text).toMatch(/^Opened the typeset reply/)
})

test('a main reply updates the typeset file without /typeset', async ($, on) => {
  const { files } = stubEngine(on, { USERPROFILE: HOME })

  await $.turn.complete({ ...TURN, answer: 'Main $x^2$.' })

  expect([...files]).toEqual([[LATEST, 'Main $x^2$.']])
})

test('a subagent reply leaves the typeset file alone', async ($, on) => {
  const { files } = stubEngine(on, { USERPROFILE: HOME })

  await $.turn.complete({ ...TURN, agentId: 'agent-1', answer: 'Subagent report.' })

  expect(files.size).toBe(0)
})

test('an empty answer leaves the typeset file alone', async ($, on) => {
  const { files } = stubEngine(on, { USERPROFILE: HOME })

  await $.turn.complete({ ...TURN, answer: '' })

  expect(files.size).toBe(0)
})

test('each main reply replaces the one before in the typeset file', async ($, on) => {
  const { files } = stubEngine(on, { USERPROFILE: HOME })

  await $.turn.complete({ ...TURN, answer: 'First.' })
  await $.turn.complete({ ...TURN, turnId: 'turn-2', answer: 'Second.' })

  expect([...files]).toEqual([[LATEST, 'Second.']])
})

test('a failed write of the typeset file raises a toast and the turn still completes', async ($, on) => {
  const toasts: string[] = []
  on('turn.complete', () => ({ text: 'Turn done.' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/someone' : undefined }))
  on('fs.write', () => ({ deny: 'EACCES: permission denied' }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })

  const result = await $.turn.complete({ ...TURN, answer: 'Reply.' })

  expect(result.text).toBe('Turn done.')
  expect(toasts).toHaveLength(1)
  expect(toasts[0]).toMatch(/EACCES: permission denied/)
})

test('without a home folder a reply writes nothing and raises no toast', async ($, on) => {
  const { files, toasts } = stubEngine(on, {})

  await $.turn.complete({ ...TURN, answer: 'Reply.' })

  expect(files.size).toBe(0)
  expect(toasts).toEqual([])
})

test('/typeset before any reply says so', async $ => {
  const result = await $.command.run(TYPESET)
  expect(result.text).toBe('There is no reply to typeset yet.')
})

test('/typeset reports a failed editor launch and keeps the file', async ($, on) => {
  on('turn.complete', () => ({ text: '' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/someone' : undefined }))
  on('fs.write', () => ({ value: undefined }))
  on('process.run', () => ({ value: { ...RAN, exitCode: 1, stderr: 'not found' } }))

  await $.turn.complete({ ...TURN, answer: 'Reply.' })
  const result = await $.command.run(TYPESET)

  expect(result.text).toBe(
    'Saved /home/someone/.claude/typeset/latest.md, but `code` exited with 1. Open the file in VS Code to see it typeset.',
  )
})
