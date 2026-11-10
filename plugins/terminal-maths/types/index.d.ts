/** The text of the last main-loop reply, kept for /typeset. */
export type StoredAnswer = string

declare module 'claude-code' {
  interface PluginState {
    'terminal-maths': { lastAnswer: Shaped<StoredAnswer> }
  }
}
