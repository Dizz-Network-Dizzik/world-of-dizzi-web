# og-bild.ps1 - renders statisch/bilder/og.png (1200x630).
# Uses GDI+ from the .NET framework that ships with Windows, so the build needs
# no image library. Fonts come from the OFL sources the font pipeline fetched.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$tmp  = Join-Path $env:TEMP "wod-fonts"
$out  = Join-Path $root "statisch\bilder\og.png"

$fonts = New-Object System.Drawing.Text.PrivateFontCollection
foreach ($f in @("Orbitron-wght.ttf", "ChakraPetch-Regular.ttf")) {
  $p = Join-Path $tmp $f
  if (-not (Test-Path $p)) { throw "missing font source $p - run werkzeug\schriften.ps1 first" }
  $fonts.AddFontFile($p)
}
$orbi   = $fonts.Families | Where-Object { $_.Name -like "Orbitron*" }    | Select-Object -First 1
$chakra = $fonts.Families | Where-Object { $_.Name -like "Chakra*" }      | Select-Object -First 1

$W = 1200; $H = 630
$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g   = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode     = "AntiAlias"
$g.TextRenderingHint = "ClearTypeGridFit"
$g.InterpolationMode = "HighQualityBicubic"

function Rgb($hex) {
  [System.Drawing.ColorTranslator]::FromHtml($hex)
}

# ---- background -----------------------------------------------------------
$g.Clear((Rgb "#080b12"))

# faint raster, same texture as the hero on the site
$grid = New-Object System.Drawing.Pen((([System.Drawing.Color]::FromArgb(10, 255, 255, 255))), 1)
for ($x = 0; $x -lt $W; $x += 68) { $g.DrawLine($grid, $x, 0, $x, $H) }
for ($y = 0; $y -lt $H; $y += 68) { $g.DrawLine($grid, 0, $y, $W, $y) }

# violet / cyan glow in the corners
$glow = New-Object System.Drawing.Drawing2D.GraphicsPath
$glow.AddEllipse(-260, -320, 1100, 760)
$gb = New-Object System.Drawing.Drawing2D.PathGradientBrush($glow)
$gb.CenterColor    = [System.Drawing.Color]::FromArgb(46, 139, 108, 255)
$gb.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 8, 11, 18))
$g.FillPath($gb, $glow)

# ---- the house gradient ---------------------------------------------------
function GradBrush($x1, $x2) {
  $b = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (New-Object System.Drawing.PointF($x1, 0)),
    (New-Object System.Drawing.PointF($x2, 0)),
    (Rgb "#ff3ea5"), (Rgb "#2ee6d6"))
  $cb = New-Object System.Drawing.Drawing2D.ColorBlend(3)
  $cb.Colors    = @((Rgb "#ff3ea5"), (Rgb "#8b6cff"), (Rgb "#2ee6d6"))
  $cb.Positions = @(0.0, 0.5, 1.0)
  $b.InterpolationColors = $cb
  return $b
}

$g.FillRectangle((GradBrush 0 $W), 0, 0, $W, 7)

# ---- text -----------------------------------------------------------------
$white = New-Object System.Drawing.SolidBrush((Rgb "#e8ebf2"))
$muted = New-Object System.Drawing.SolidBrush((Rgb "#9aa4b6"))

$fWord = New-Object System.Drawing.Font($orbi, 30, [System.Drawing.FontStyle]::Bold, "Pixel")
$g.DrawString("the world of dizzi", $fWord, (GradBrush 78 378), 78, 72)

$fH1 = New-Object System.Drawing.Font($orbi, 50, [System.Drawing.FontStyle]::Bold, "Pixel")
$g.DrawString("One person. Ten applications.", $fH1, $white, 74, 158)
$g.DrawString("One architecture.",             $fH1, $white, 74, 232)

$fLede = New-Object System.Drawing.Font($chakra, 25, [System.Drawing.FontStyle]::Regular, "Pixel")
$g.DrawString("A local-first AI network for a whole life — built by one person", $fLede, $muted, 78, 322)
$g.DrawString("directing AI build chats under written law.",                    $fLede, $muted, 78, 358)

$g.FillRectangle((GradBrush 80 420), 80, 428, 330, 3)

# ---- the four numbers -----------------------------------------------------
$fNum = New-Object System.Drawing.Font($orbi,   38, [System.Drawing.FontStyle]::Bold,    "Pixel")
$fLbl = New-Object System.Drawing.Font($chakra, 17, [System.Drawing.FontStyle]::Regular, "Pixel")

$cols = @(
  @{ n = "10";       l = "applications" },
  @{ n = "2,600+";   l = "commits since June 2026" },
  @{ n = "~100,000"; l = "lines of Python" },
  @{ n = "2,623";    l = "tests in the snapshot" }
)
$x = 78
foreach ($c in $cols) {
  $g.DrawString($c.n, $fNum, $white, $x, 470)
  $g.DrawString($c.l, $fLbl, $muted, $x + 3, 528)
  $x += 272
}

$fFoot = New-Object System.Drawing.Font($chakra, 17, [System.Drawing.FontStyle]::Regular, "Pixel")
$g.DrawString("Source-visible showcase, not open source.   Independent project — incorporation ahead.",
              $fFoot, (New-Object System.Drawing.SolidBrush((Rgb "#8792a6"))), 78, 578)

# ---- write ----------------------------------------------------------------
$g.Dispose()
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"{0}  {1:N0} bytes" -f $out, (Get-Item $out).Length | Write-Host
