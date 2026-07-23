# sweep.ps1 - the disclosure gate. Run before every push.
#
# The website and its repository are public. This scans the sources, the baked
# output and the commit messages for anything that must never appear there:
# vendor and model names, personal names, private paths, and the topics of a
# separate business that has nothing to do with this site.
#
# Target: zero findings outside the declared exceptions.
#   pwsh pruefung/sweep.ps1          exit 0 = clean, 1 = findings

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# word = whole word only. Without it, "Elin" fires on timeline, baseline and
# pipelines, "rami" on ceramic, "nude" on denuded - the "comparison" class of
# false positive. Substring matching stays where the string is already unique.
$patterns = @(
  @{ p = 'anthropic'; mode = 'word' }, @{ p = 'claude';  mode = 'word' },
  @{ p = 'opus';      mode = 'word' }, @{ p = 'sonnet';  mode = 'word' },
  @{ p = 'haiku';     mode = 'word' }, @{ p = 'fable';   mode = 'word' },
  @{ p = 'rami';      mode = 'word' }, @{ p = 'lucy';    mode = 'word' },
  @{ p = 'krause';    mode = 'word' }, @{ p = 'nsfw';    mode = 'word' },
  @{ p = 'realismus'; mode = 'word' }, @{ p = 'realism'; mode = 'word' },
  @{ p = 'fanvue';    mode = 'word' }, @{ p = 'erotik';  mode = 'word' },
  @{ p = 'nude';      mode = 'word' }, @{ p = 'Sofia';   mode = 'word' },
  @{ p = 'Elin';      mode = 'word' }, @{ p = 'Yasmin';  mode = 'word' },
  @{ p = 'Brooke';    mode = 'word' },
  @{ p = 'david188';  mode = 'sub'  }, @{ p = '@gmail';    mode = 'sub' },
  @{ p = 'C:\Dizzik'; mode = 'sub'  }, @{ p = 'C:\Users';  mode = 'sub' },
  @{ p = 'persona_';  mode = 'sub'  }
)

# Declared, justified exceptions. Each one is argued in the closing protocol.
$exceptions = @(
  @{ pattern = '@gmail'
     path    = '*'
     match   = 'theworldofdizzi@gmail.com'
     why     = 'the published contact address (handover section 9)' },
  @{ pattern = 'krause'
     path    = '*impressum*'
     match   = 'David Michael Krause'
     why     = 'the provider name in the Impressum - the one place handover section 1.1 allows the surname, and section 5 DDG requires it' },
  @{ pattern = '*'
     path    = '*\karte\*'
     match   = '*'
     why     = 'byte-identical copy of _netzwerk/SYSTEM_KARTE.html from the public repository; editing it is forbidden by handover section 5.9, and every string in it is already public there' }
)

$scan = @(
  "$root\bake.py", "$root\netlify.toml", "$root\README.md",
  "$root\vorlagen", "$root\seiten", "$root\statisch",
  "$root\pruefung", "$root\werkzeug", "$root\dist"
) | Where-Object { Test-Path $_ }

$files = foreach ($p in $scan) {
  if (Test-Path $p -PathType Container) { Get-ChildItem $p -Recurse -File } else { Get-Item $p }
}
# binaries carry no readable text; this script necessarily contains every pattern
$files = $files | Where-Object {
  $_.Extension -notin '.woff2', '.png', '.ico' -and $_.FullName -ne $PSCommandPath
}

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

if ($accepted.Count) {
  Write-Host "ACCEPTED EXCEPTIONS ($($accepted.Count) hits)" -ForegroundColor DarkYellow
  $accepted | Group-Object file, pattern | ForEach-Object {
    $r = $_.Group[0]
    "  {0,-34} {1,-12} x{2,-4} {3}" -f $r.file, $r.pattern, $_.Count, $r.why | Write-Host
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
