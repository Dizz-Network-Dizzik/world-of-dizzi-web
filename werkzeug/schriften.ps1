# schriften.ps1 - font pipeline (build tool, not a site dependency)
# Downloads the SIL OFL sources from github.com/google/fonts, subsets them to the
# characters this site actually uses and writes WOFF2 into statisch/schrift/.
# Run once; the resulting .woff2 + OFL.txt files are committed.

$ErrorActionPreference = "Stop"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "no python on PATH" }
$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root "statisch\schrift"
$tmp  = Join-Path $env:TEMP "wod-fonts"

New-Item -ItemType Directory -Force -Path $out, $tmp | Out-Null

Write-Host "== 1/4 build tools =="
& $py -m pip install --quiet --disable-pip-version-check fonttools brotli
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "== 2/4 sources (SIL OFL, github.com/google/fonts) =="
$base = "https://raw.githubusercontent.com/google/fonts/main"
# local names stay bracket-free: PowerShell treats [ ] in -OutFile as a wildcard
$files = @(
  @{ url = "$base/ofl/orbitron/Orbitron%5Bwght%5D.ttf";        file = "Orbitron-wght.ttf" },
  @{ url = "$base/ofl/orbitron/OFL.txt";                       file = "OFL-orbitron.txt" },
  @{ url = "$base/ofl/chakrapetch/ChakraPetch-Regular.ttf";    file = "ChakraPetch-Regular.ttf" },
  @{ url = "$base/ofl/chakrapetch/ChakraPetch-SemiBold.ttf";   file = "ChakraPetch-SemiBold.ttf" },
  @{ url = "$base/ofl/chakrapetch/OFL.txt";                    file = "OFL-chakra-petch.txt" }
)
foreach ($f in $files) {
  $dest = Join-Path $tmp $f.file
  Invoke-WebRequest -Uri $f.url -OutFile $dest -UseBasicParsing
  "{0,-30} {1,8} bytes" -f $f.file, (Get-Item $dest).Length | Write-Host
}
Copy-Item (Join-Path $tmp "OFL-orbitron.txt")     (Join-Path $out "OFL-orbitron.txt")     -Force
Copy-Item (Join-Path $tmp "OFL-chakra-petch.txt") (Join-Path $out "OFL-chakra-petch.txt") -Force

Write-Host "== 3/4 subset =="
# Latin + the punctuation, arrows and geometric marks this site uses.
$uni = "U+0000-00FF,U+0131,U+0152-0153,U+2000-206F,U+2070,U+2074-2079,U+20AC,U+2122,U+2190-2199,U+21B5,U+2212,U+2215,U+2248,U+2260-2265,U+25A0-25CF,U+25B6-25BA,U+2713-2714"

$jobs = @(
  @{ src = "Orbitron-wght.ttf";        dst = "orbitron-var.woff2" },
  @{ src = "ChakraPetch-Regular.ttf";  dst = "chakra-400.woff2" },
  @{ src = "ChakraPetch-SemiBold.ttf"; dst = "chakra-600.woff2" }
)
foreach ($j in $jobs) {
  $dst = Join-Path $out $j.dst
  & $py -m fontTools.subset (Join-Path $tmp $j.src) `
      "--unicodes=$uni" `
      "--layout-features=kern,liga,clig,calt,ccmp,locl,mark,mkmk,rlig" `
      "--flavor=woff2" `
      "--output-file=$dst"
  if ($LASTEXITCODE -ne 0) { throw "subset failed: $($j.src)" }
}

Write-Host "== 4/4 result =="
$total = 0
Get-ChildItem $out -Filter *.woff2 | ForEach-Object {
  "{0,-22} {1,7} bytes" -f $_.Name, $_.Length | Write-Host
  $total += $_.Length
}
"{0,-22} {1,7} bytes  (budget 122880)" -f "TOTAL", $total | Write-Host
if ($total -gt 122880) { throw "font budget exceeded" }
Write-Host "OK"
