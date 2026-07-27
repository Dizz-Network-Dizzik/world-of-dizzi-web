# make_icon.ps1 — rendert das Neon-Favicon-Design (Dashboard, index.html Zeile 8) als echte
# Multi-Size-.ico via GDI+ (PNG-basiert, 16..256 px). Reproduzierbar, keine Zusatztools.
# Ausgabe: backend\app\static\tradingbot.ico (genutzt von Desktop-Verknuepfung + Monitor-App).
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$root   = Split-Path -Parent $PSScriptRoot
$outIco = Join-Path $root "backend\app\static\tradingbot.ico"
$sizes  = 16,24,32,48,64,128,256
$pngs   = @()

foreach ($s in $sizes) {
  $bmp = New-Object System.Drawing.Bitmap($s, $s)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'
  $k = $s / 32.0   # Skalierung vom 32er-ViewBox des SVG-Favicons

  # Hintergrund: dunkler Verlauf in abgerundetem Rechteck + Cyan-Rand (wie SVG)
  $p = New-Object System.Drawing.Drawing2D.GraphicsPath
  $r = [float][Math]::Max(2, 8*$k); $x=[float](1.5*$k); $y=[float](1.5*$k); $w=[float](29*$k); $h=[float](29*$k)
  $p.AddArc($x, $y, 2*$r, 2*$r, 180, 90)
  $p.AddArc($x+$w-2*$r, $y, 2*$r, 2*$r, 270, 90)
  $p.AddArc($x+$w-2*$r, $y+$h-2*$r, 2*$r, 2*$r, 0, 90)
  $p.AddArc($x, $y+$h-2*$r, 2*$r, 2*$r, 90, 90)
  $p.CloseFigure()
  $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
      (New-Object System.Drawing.PointF(0,0)), (New-Object System.Drawing.PointF($s,$s)),
      [System.Drawing.Color]::FromArgb(255,20,11,40), [System.Drawing.Color]::FromArgb(255,9,7,23))
  $g.FillPath($grad, $p)
  $penB = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255,47,231,255), [float][Math]::Max(1,1.6*$k))
  $g.DrawPath($penB, $p)

  # Cyan-Chartlinie 6,21 -> 13,13 -> 17,17 -> 26,7
  $penC = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255,47,231,255), [float][Math]::Max(1.5,2.6*$k))
  $penC.StartCap='Round'; $penC.EndCap='Round'; $penC.LineJoin='Round'
  $ptsC = [System.Drawing.PointF[]]@(
    [System.Drawing.PointF]::new([float](6*$k),    [float](21*$k)),
    [System.Drawing.PointF]::new([float](13*$k),   [float](13*$k)),
    [System.Drawing.PointF]::new([float](17*$k),   [float](17*$k)),
    [System.Drawing.PointF]::new([float](26*$k),   [float](7*$k)))
  $g.DrawLines($penC, $ptsC)

  # Magenta-Pfeilspitze 20.5,7 -> 26,7 -> 26,12.5
  $penM = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255,255,61,240), [float][Math]::Max(1.5,2.6*$k))
  $penM.StartCap='Round'; $penM.EndCap='Round'; $penM.LineJoin='Round'
  $ptsM = [System.Drawing.PointF[]]@(
    [System.Drawing.PointF]::new([float](20.5*$k), [float](7*$k)),
    [System.Drawing.PointF]::new([float](26*$k),   [float](7*$k)),
    [System.Drawing.PointF]::new([float](26*$k),   [float](12.5*$k)))
  $g.DrawLines($penM, $ptsM)

  # Magenta-Punkt bei 13,13
  $br = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255,255,61,240))
  $rr = [float](1.7*$k)
  $g.FillEllipse($br, [float](13*$k-$rr), [float](13*$k-$rr), 2*$rr, 2*$rr)

  $g.Dispose()
  $ms = New-Object System.IO.MemoryStream
  $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
  $pngs += ,@{ Size=$s; Data=$ms.ToArray() }
  $bmp.Dispose(); $ms.Dispose()
}

# PNG-basierte ICO (ICONDIR + ICONDIRENTRYs + PNG-Blobs)
$fs = [System.IO.File]::Create($outIco)
$bw = New-Object System.IO.BinaryWriter($fs)
$bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]$pngs.Count)
$offset = 6 + 16*$pngs.Count
foreach ($q in $pngs) {
  $dim = if ($q.Size -ge 256) { 0 } else { $q.Size }
  $bw.Write([Byte]$dim); $bw.Write([Byte]$dim); $bw.Write([Byte]0); $bw.Write([Byte]0)
  $bw.Write([UInt16]1); $bw.Write([UInt16]32)
  $bw.Write([UInt32]$q.Data.Length); $bw.Write([UInt32]$offset)
  $offset += $q.Data.Length
}
foreach ($q in $pngs) { $bw.Write($q.Data) }
$bw.Close(); $fs.Close()
Write-Output ("ICO erstellt: " + $outIco + " (" + (Get-Item $outIco).Length + " Bytes)")
