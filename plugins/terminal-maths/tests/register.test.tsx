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
  const started: string[][] = []
  on('turn.complete', () => ({ text: '' }))
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? 'C:\\Users\\someone' : e.name === 'OS' ? 'Windows_NT' : undefined }))
  on('fs.write', (_, e) => {
    written.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('process.run', (_, e) => {
    started.push([...e.argv])
    return { value: RAN }
  })

  await $.turn.complete({ ...TURN, answer: 'Main $x^2$.' })
  await $.turn.complete({ ...TURN, turnId: 'turn-2', agentId: 'agent-1', answer: 'Subagent report.' })
  const result = await $.command.run(TYPESET)

  // The engine hands the hook the path in the platform's own form.
  expect(written.map(file => file.path.replaceAll('\\', '/'))).toEqual(['C:/Users/someone/.claude/typeset/latest.md'])
  expect(written.map(file => file.text)).toEqual(['Main $x^2$.'])
  expect(started).toEqual([['cmd.exe', '/d', '/c', 'code', '-r', 'C:/Users/someone/.claude/typeset/latest.md']])
  expect(result.text).toMatch(/^Opened the typeset reply/)
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
