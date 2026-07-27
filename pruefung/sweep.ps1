# sweep.ps1 - the disclosure gate. Run before every push.
#
# The website and its repository are public. This scans the sources, the baked
# output and the commit messages against a private list of strings that must
# not appear in either: third-party names, personal data and local paths.
#
# Target: zero findings outside the declared exceptions.
#   pwsh pruefung/sweep.ps1          exit 0 = clean, 1 = findings, 2 = could not check

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# The terms themselves are NOT in this file, and that is the point. This
# repository is public and its README invites the reader in - so until
# 26.07.2026 the list of words that must never be published was itself
# published here, together with a comment announcing that a separate business
# exists. A gate that hangs out its own watch list guards nothing.
#
# The list now lives outside every public repository, in one place that three
# scripts read: this one, the outgoing-mail sweep and the generic text sweep.
# Set DIZZI_SPERRLISTE to override the path.
#
# Entries are "<mode> <term>"; exceptions are "except <term> <path> <reason>".
# Two modes: word = whole word only, which most short terms need, because a
# four-letter name buried inside an ordinary English word would otherwise
# report a finding on every page; sub = anywhere, for strings already unique
# on their own. The examples that used to stand here were themselves terms
# from the list - the first run of this rewrite caught them.
$listenPfad = if ($env:DIZZI_SPERRLISTE) { $env:DIZZI_SPERRLISTE }
              else { Join-Path (Split-Path -Parent (Split-Path -Parent $root)) "Projektzentrale\pruefung\sperrbegriffe.txt" }

if (-not (Test-Path $listenPfad)) {
  Write-Host "ABORT: term list not found at $listenPfad" -ForegroundColor Red
  Write-Host "Nothing was checked. Do not push." -ForegroundColor Red
  Write-Host "(Working copy only - a clone of this public repository cannot run this gate," -ForegroundColor DarkGray
  Write-Host " which is deliberate: the list is what must stay private.)" -ForegroundColor DarkGray
  exit 2
}

$patterns = @(); $exceptions = @()
foreach ($zeile in Get-Content -Path $listenPfad -Encoding UTF8) {
  $z = ($zeile -split '#', 2)[0].Trim()
  if (-not $z) { continue }
  # Split off the mode ONLY. A term may contain spaces; splitting too early
  # leaves the first word standing in for the whole phrase, which both
  # over-reports and never checks the phrase it was written for.
  $modus, $rest = $z -split '\s+', 2
  if (-not $rest) {
    Write-Host "ABORT: line without a term in $listenPfad : $z" -ForegroundColor Red; exit 2
  }
  switch ($modus.ToLower()) {
    'word'   { $patterns += @{ p = $rest.Trim(); mode = 'word' } }
    'sub'    { $patterns += @{ p = $rest.Trim(); mode = 'sub'  } }
    'except' {
      $eBegriff, $ePfad, $eGrund = $rest -split '\s+', 3
      if (-not $eGrund) {
        Write-Host "ABORT: malformed exception in $listenPfad : $z" -ForegroundColor Red; exit 2
      }
      $exceptions += @{ pattern = $eBegriff; path = $ePfad; match = '*'; why = $eGrund }
    }
    default {
      Write-Host "ABORT: unknown mode '$modus' in $listenPfad" -ForegroundColor Red; exit 2
    }
  }
}
if (-not $patterns.Count) {
  Write-Host "ABORT: $listenPfad holds no terms. Nothing was checked." -ForegroundColor Red
  exit 2
}

# One exception is safe to name here, because it names nothing: the copied
# system map is public in the other repository already, and editing it is
# forbidden. Every other exception quotes a term and therefore lives with the
# terms, in the private list.
$exceptions += @{
  pattern = '*'
  path    = '*\karte\*'
  match   = '*'
  why     = 'byte-identical copy of _netzwerk/SYSTEM_KARTE.html from the public repository; editing it is forbidden by handover section 5.9. The vendor names it contains are not a leak this gate can close: the same names stand in the public showcase repository the map is copied from - measured 26.07.2026, whole-word, across its whole history: 22 files carry one, 15 another, in engine code, research notes and the MCP gateway. Scrubbing the copy here would hide nothing and would only make the two versions differ'
}

# This list is an allowlist, and an allowlist is a promise that nothing lands
# outside it. The code snapshot did exactly that: 966 files moved into this
# repository on 27.07.2026 and the gate reported "clean" over 54 files without
# ever opening one of them. A disclosure gate that does not see what is being
# published is worse than none, because it signs off on it.
# The code snapshot is a byte-identical copy of material that is already public
# under the same account. Every term it carries - the local build path and the
# names of AI vendors - stands in that public copy today; this gate only started
# seeing them when the folder moved in on 27.07.2026, measured then: 277 hits
# over 251 files. Scrubbing them here would not un-publish anything. It would
# make the public extract differ from the curated original it claims to be, and
# every later refresh would have to repeat the scrub or silently undo it. Same
# reasoning as the copied system map above, applied to the folder it came from.
# Decided by David, 27.07.2026.
#
# This is deliberately NOT silence: the hits stay counted and are printed as a
# per-term summary on every run. If that number moves, something entered the
# folder that was not in the curated snapshot, and it is meant to be noticed.
$exceptions += @{
  pattern = '*'
  path    = '*\snapshot\*'
  match   = '*'
  why     = 'code snapshot: byte-identical copy of the already-public curated extract'
}

$scan = @(
  "$root\bake.py", "$root\netlify.toml", "$root\README.md",
  "$root\vorlagen", "$root\seiten", "$root\statisch",
  "$root\pruefung", "$root\werkzeug", "$root\dist",
  "$root\snapshot"
) | Where-Object { Test-Path $_ }

$files = foreach ($p in $scan) {
  if (Test-Path $p -PathType Container) { Get-ChildItem $p -Recurse -File } else { Get-Item $p }
}

# Scan what could actually be published, not what happens to lie on the disk.
# A stray __pycache__ carries the absolute build path inside its bytecode and
# reports as a finding every time, although .gitignore means it can never reach
# the remote. Findings nobody can act on are how a gate teaches people to look
# away, so ask git which files are real candidates and judge only those.
if (Test-Path "$root\.git") {
  $verfolgt = @{}
  try {
    foreach ($rel in @(git -C $root ls-files --cached --others --exclude-standard)) {
      if ($rel) { $verfolgt[(Join-Path $root ($rel -replace '/', '\'))] = $true }
    }
  } catch { $verfolgt = @{} }
  if ($verfolgt.Count) {
    $files = $files | Where-Object { $verfolgt.ContainsKey($_.FullName) }
  }
}
# binaries carry no readable text. This script is scanned like everything else -
# it no longer holds the terms, so it has nothing to be excused for.
$files = $files | Where-Object { $_.Extension -notin '.woff2', '.png', '.ico' }

Write-Host "sweep over $($files.Count) files in $((Split-Path $root -Leaf))`n"

$hard = @(); $accepted = @()
foreach ($f in $files) {
  $rel = $f.FullName.Substring($root.Length + 1)
  foreach ($entry in $patterns) {
    $pat = $entry.p
    if ($entry.mode -eq 'word') {
      $rx = '\b' + [regex]::Escape($pat) + '\b'
      $hits = Select-String -Path $f.FullName -Pattern $rx -AllMatches -ErrorAction SilentlyContinue
    } else {
      $hits = Select-String -Path $f.FullName -Pattern $pat -SimpleMatch -AllMatches -ErrorAction SilentlyContinue
    }
    foreach ($h in $hits) {
      $line = $h.Line.Trim()
      $ok = $false; $why = ""
      foreach ($e in $exceptions) {
        $pOk = ($e.pattern -eq '*') -or ($e.pattern -eq $pat)
        $fOk = ($e.path -eq '*') -or ($f.FullName -like $e.path)
        $mOk = ($e.match -eq '*') -or ($line -like "*$($e.match)*")
        if ($pOk -and $fOk -and $mOk) { $ok = $true; $why = $e.why; break }
      }
      $row = [pscustomobject]@{
        pattern = $pat; file = $rel; line = $h.LineNumber
        text = $line.Substring(0, [Math]::Min(90, $line.Length)); why = $why
      }
      if ($ok) { $accepted += $row } else { $hard += $row }
    }
  }
}

# commit messages count as published text too
$msgs = @()
if (Test-Path "$root\.git") {
  $log = @()
  try { $log = @(git -C $root log --pretty=format:"%H|%s|%b") } catch { $log = @() }
  foreach ($l in $log) {
    foreach ($entry in $patterns) {
      if ($l -and $l.ToLower().Contains($entry.p.ToLower())) { $msgs += "commit: $l" }
    }
  }
}

# The snapshot's hits are summarised per term instead of per file: 277 lines of
# the same reason would bury the handful of exceptions that are actually about
# this website. The totals stay in view, which is the part that has to be read.
$ausz = $accepted | Where-Object { $_.file -like "snapshot\*" }
$eigen = $accepted | Where-Object { $_.file -notlike "snapshot\*" }

if ($eigen.Count) {
  Write-Host "ACCEPTED EXCEPTIONS ($($eigen.Count) hits)" -ForegroundColor DarkYellow
  $eigen | Group-Object file, pattern | ForEach-Object {
    $r = $_.Group[0]
    "  {0,-34} {1,-12} x{2,-4} {3}" -f $r.file, $r.pattern, $_.Count, $r.why | Write-Host
  }
  Write-Host ""
}

if ($ausz.Count) {
  $dn = ($ausz.file | Sort-Object -Unique).Count
  Write-Host ("CODE SNAPSHOT ($($ausz.Count) hits over $dn files, all declared)") -ForegroundColor DarkYellow
  Write-Host "  already public in the curated extract this folder copies - see the note in this script" -ForegroundColor DarkGray
  $ausz | Group-Object pattern | Sort-Object Count -Descending | ForEach-Object {
    "    {0,-14} x{1}" -f $_.Name, $_.Count | Write-Host
  }
  Write-Host ""
}

if ($hard.Count -or $msgs.Count) {
  Write-Host "FINDINGS" -ForegroundColor Red
  $hard | ForEach-Object { "  {0}:{1}  [{2}]  {3}" -f $_.file, $_.line, $_.pattern, $_.text | Write-Host }
  $msgs | ForEach-Object { "  $_" | Write-Host }
  Write-Host "`n$($hard.Count + $msgs.Count) finding(s). Do not push." -ForegroundColor Red
  exit 1
}

Write-Host "sweep clean - 0 findings, $($accepted.Count) declared exceptions." -ForegroundColor Green
exit 0
