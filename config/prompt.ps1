# Prompt and PSReadLine colours in the Claude Warm palette, dot-sourced from
# the PowerShell profile. The file is ASCII only: Windows PowerShell 5.1
# reads a script without a byte order mark in the ANSI code page, so every
# non-ASCII glyph is built from its code point.

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ClaudeWarmEscape = [char]27
$ClaudeWarmMaxParentDirectories = 64

function Get-ClaudeWarmColour([int]$Red, [int]$Green, [int]$Blue) {
    '{0}[38;2;{1};{2};{3}m' -f $ClaudeWarmEscape, $Red, $Green, $Blue
}

$ClaudeWarm = @{
    Accent = Get-ClaudeWarmColour 217 119 87
    Text   = Get-ClaudeWarmColour 232 230 220
    Muted  = Get-ClaudeWarmColour 143 139 128
    Amber  = Get-ClaudeWarmColour 227 178 97
    Green  = Get-ClaudeWarmColour 141 181 128
    Red    = Get-ClaudeWarmColour 224 122 111
    Blue   = Get-ClaudeWarmColour 125 162 206
    Violet = Get-ClaudeWarmColour 201 155 194
    Reset  = '{0}[0m' -f $ClaudeWarmEscape
}

# Reads the branch from .git/HEAD instead of running git, so the prompt
# costs no process start. A worktree's .git file points at its real folder.
function Get-ClaudeWarmBranch {
    $directory = $PWD.ProviderPath
    for ($level = 0; $level -lt $ClaudeWarmMaxParentDirectories -and $directory; $level++) {
        $marker = Join-Path $directory '.git'
        if (Test-Path -LiteralPath $marker -PathType Container) {
            $head = Join-Path $marker 'HEAD'
        } elseif (Test-Path -LiteralPath $marker -PathType Leaf) {
            $pointer = (Get-Content -LiteralPath $marker -TotalCount 1) -replace '^gitdir:\s*', ''
            $head = Join-Path $pointer 'HEAD'
        } else {
            $directory = Split-Path -Parent $directory
            continue
        }
        if (-not (Test-Path -LiteralPath $head)) { return $null }
        $reference = Get-Content -LiteralPath $head -TotalCount 1
        if ($reference -match '^ref: refs/heads/(.+)$') { return $Matches[1] }
        return $reference.Substring(0, [Math]::Min(7, $reference.Length))
    }
    return $null
}

function prompt {
    $succeeded = $?
    $diamond = [char]0x25C6
    $chevron = [char]0x276F
    $folder = Split-Path -Leaf $PWD.ProviderPath
    if (-not $folder) { $folder = $PWD.ProviderPath }
    $line = '{0}{1} {2}{3}' -f $ClaudeWarm.Accent, $diamond, $ClaudeWarm.Text, $folder
    $branch = Get-ClaudeWarmBranch
    if ($branch) { $line += ' {0}on {1}{2}' -f $ClaudeWarm.Muted, $ClaudeWarm.Amber, $branch }
    $arrowColour = if ($succeeded) { $ClaudeWarm.Accent } else { $ClaudeWarm.Red }
    "`n{0}`n{1}{2}{3} " -f $line, $arrowColour, $chevron, $ClaudeWarm.Reset
}

if (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue) {
    Set-PSReadLineOption -ContinuationPrompt ('{0}{1} {2}' -f $ClaudeWarm.Muted, [char]0x2502, $ClaudeWarm.Reset)
    Set-PSReadLineOption -Colors @{
        Command   = $ClaudeWarm.Accent
        Parameter = $ClaudeWarm.Blue
        Operator  = $ClaudeWarm.Muted
        String    = $ClaudeWarm.Green
        Number    = $ClaudeWarm.Amber
        Variable  = $ClaudeWarm.Violet
        Keyword   = $ClaudeWarm.Violet
        Type      = $ClaudeWarm.Blue
        Member    = $ClaudeWarm.Text
        Comment   = $ClaudeWarm.Muted
        Default   = $ClaudeWarm.Text
    }
}
