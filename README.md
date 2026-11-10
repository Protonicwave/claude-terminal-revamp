# claude-terminal-revamp

Makes Claude Code in the VS Code integrated terminal read more like the Claude app. It changes four things:

- **Maths renders in the terminal.** The `terminal-maths` mod asks Claude to write maths as LaTeX and draws it as Unicode on screen. Inline maths becomes one line (`E = mc²`, `∑ᵢ₌₁ⁿ xᵢ`). Display maths becomes a two-dimensional block with stacked fractions, limits, tall brackets, matrices, cases and aligned rows. The VS Code chat panel and the desktop app typeset LaTeX themselves, so the mod leaves those alone.
- **`/typeset`** writes the last reply to `~/.claude/typeset/latest.md` and opens it in VS Code's Markdown preview, which typesets the maths with KaTeX.
- **A two-line status line** shows the model, effort, folder, git branch and output style, then a context bar, cost, lines changed and the five-hour limit.
- **One palette everywhere ("Claude Warm").** It covers the VS Code terminal colours, font and cursor, a custom Claude Code theme, physics spinner verbs, a 100-column reading width, fullscreen mode, and a matching PowerShell prompt with PSReadLine colours.

```
     ∂            ⎛  ℏ²       ⎞
  iℏ────Ψ(𝐫, t) = ⎜−────∇² + V⎟Ψ
     ∂t           ⎝  2m       ⎠
```

## Requirements

- Claude Code 2.1.322 or later, Python 3.12 or later, git, VS Code with the `code` command on `PATH`.
- The PowerShell prompt is for Windows PowerShell 5.1 or PowerShell 7. Elsewhere the installer skips it.
- The font stack expects Cascadia Code and falls back to Cambria Math for maths glyphs. Both ship with Windows 11.

## Install

```
git clone https://github.com/Protonicwave/claude-terminal-revamp.git
cd claude-terminal-revamp
python install.py
```

The installer backs up each settings file it touches (`*.terminal-kit-<timestamp>.bak`) and records every value it replaces in `~/.claude/terminal-kit-state.json`. On Windows it sets the PowerShell execution policy to `RemoteSigned` for the current user if it was stricter, because a profile script cannot run otherwise.

Afterwards, reload the VS Code window, restart Claude Code, and run `/terminal-setup` once inside Claude Code in the VS Code terminal to bind Shift+Enter.

To install only the maths mod:

```
claude plugin marketplace add Protonicwave/claude-terminal-revamp
claude plugin install terminal-maths@claude-terminal-revamp
```

## Uninstall

```
python install.py --uninstall
```

This restores every value the installer replaced, unless you have changed it since, in which case your value stays and the output lists it. It also removes the theme, the profile block and the mod, and restores the execution policy.

## Configure

- Colours: `config/vscode.json` (terminal), `config/themes/claude-warm.json` (Claude Code), `config/prompt.ps1` (PowerShell), `statusline/statusline.py` (status line). Run `python install.py` again after editing.
- Claude Code settings applied: `config/claude.json`. Remove a key there to keep your own value.
- Mod edits apply in place: the mod is read from this folder, so run `/reload-plugins` in Claude Code.

## Development

```
python -m pytest                   # status line and installer
python -m pytest -m timing -s      # status line against its 150 ms budget
python -m ruff check .
claude plugin test plugins/terminal-maths       # maths renderer and mod; prints render time against a 5 ms budget
claude plugin validate plugins/terminal-maths
```

## Limits

- The VS Code terminal cannot show inline images, so typeset equations live in `/typeset`, not in the chat.
- Display maths wider than the terminal falls back to the one-line form. Superscripts and subscripts without a Unicode form fall back to `^(…)` and `_(…)`.
- Maths glyph widths depend on the fallback font. Cambria Math is not monospaced, so some symbols can sit slightly off the grid.
