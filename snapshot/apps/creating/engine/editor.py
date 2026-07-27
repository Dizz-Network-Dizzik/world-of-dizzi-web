"""Schneid-Instanz — Editor-Schnittstelle + ffmpeg-Fundament (R-A §B).

ffmpeg ist die verlässliche Basis JEDER Schnitt-/Analyse-Operation; MoviePy/
PySceneDetect/Whisper/Vision-LLM setzen später darauf auf (App-Schicht).
Die Befehls-BAUER sind pure Funktionen (exakt testbar ohne ffmpeg); die
AUSFÜHRUNG ist ein dünner subprocess-Rand. Stille-Erkennung parst die
``silencedetect``-Ausgabe — Grundlage für Auto-Cut („langweilige Segmente raus").
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol

from .jobs import Job


class Editor(Protocol):
    """Vertrags-Schnittstelle der Schneid-Instanz."""

    def health(self) -> bool: ...
    def probe(self, src: Path) -> dict[str, Any]: ...
    def cut(self, job: Job) -> dict[str, Any]: ...


# --- Befehls-Bauer (pur, exakt testbar) ---------------------------------------

def build_cut_args(src: str, dst: str, start_s: float, end_s: float,
                   reencode: bool = False) -> list[str]:
    """Schnitt eines Segments. Default Stream-Copy (verlustfrei, schnell);
    ``reencode`` für rahmengenaue Schnitte."""
    if end_s <= start_s:
        raise ValueError("end_s muss > start_s sein")
    base = ["ffmpeg", "-hide_banner", "-y", "-ss", f"{start_s:.3f}",
            "-to", f"{end_s:.3f}", "-i", src]
    codec = ["-c:v", "libx264", "-c:a", "aac"] if reencode else ["-c", "copy"]
    return base + codec + [dst]


def build_concat_args(listfile: str, dst: str) -> list[str]:
    """Verkettung vorbereiteter Segmente (concat-Demuxer, Stream-Copy) —
    schnell + verlustfrei, verlangt aber IDENTISCHE Codec-Parameter."""
    return ["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0",
            "-i", listfile, "-c", "copy", dst]


def build_concat_filter_args(srcs: list[str], dst: str, *, breite: int,
                             hoehe: int, fps: int = 24) -> list[str]:
    """Robuste Verkettung beliebiger (auch verschieden großer) Clips über den
    concat-Filter: jeder Clip wird auf ``breite×hoehe`` skaliert (Seiten-
    verhältnis erhalten, Rest gepadded) + auf ``fps`` gebracht, dann verkettet
    und neu kodiert. **Video-only** (``a=0``) — die generierten Wan-Clips sind
    stumm; der Ton kommt erst über die Vertonung (Symbiose) dazu. Pur/testbar."""
    if len(srcs) < 2:
        raise ValueError("Concat braucht mindestens 2 Quellen")
    if breite <= 0 or hoehe <= 0 or fps <= 0:
        raise ValueError("breite/hoehe/fps müssen > 0 sein")
    args = ["ffmpeg", "-hide_banner", "-y"]
    for s in srcs:
        args += ["-i", str(s)]
    norm = [
        f"[{i}:v]scale={breite}:{hoehe}:force_original_aspect_ratio=decrease,"
        f"pad={breite}:{hoehe}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]"
        for i in range(len(srcs))]
    ketten = "".join(f"[v{i}]" for i in range(len(srcs)))
    filter_complex = (";".join(norm) +
                      f";{ketten}concat=n={len(srcs)}:v=1:a=0[outv]")
    return args + ["-filter_complex", filter_complex, "-map", "[outv]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", dst]


def build_silence_args(src: str, noise_db: float = -35.0,
                       min_s: float = 1.5) -> list[str]:
    """Stille-Analyse (Auto-Cut-Grundlage); Ergebnis steht auf stderr."""
    return ["ffmpeg", "-hide_banner", "-i", src, "-af",
            f"silencedetect=noise={noise_db}dB:d={min_s}", "-f", "null", "-"]


def build_szenen_args(src: str, schwelle: float = 0.4) -> list[str]:
    """Szenen-Erkennung (Schnitt-Grenzen): ffmpeg ``select='gt(scene,…)'``
    + showinfo — die Treffer-Zeitpunkte stehen auf stderr (0-€-Boden;
    PySceneDetect = content-aware Ausbau, gleiche aus_szenen-Schnittstelle)."""
    return ["ffmpeg", "-hide_banner", "-i", src, "-vf",
            f"select='gt(scene,{schwelle})',showinfo", "-f", "null", "-"]


_SZENE_PTS = re.compile(r"pts_time:\s*([0-9.]+)")


def parse_szenen(ffmpeg_stderr: str) -> list[float]:
    """Parst showinfo-Ausgabe zu Szenen-Grenz-Zeitpunkten (pur, testbar)."""
    return [float(m.group(1)) for zeile in ffmpeg_stderr.splitlines()
            if "showinfo" in zeile
            for m in [_SZENE_PTS.search(zeile)] if m]


def build_reframe_args(src: str, dst: str,
                       seitenverhaeltnis: str = "9:16") -> list[str]:
    """Auto-Reframe auf Ziel-Seitenverhältnis (Center-Crop, Stufe 1).
    EHRLICH: AutoFlip-Salienz-Tracking (E4) ist vorbereiteter Ausbau —
    gleicher Befehlsbauer, schlauerer Crop-Pfad."""
    try:
        b, h = (int(x) for x in seitenverhaeltnis.split(":"))
        if b <= 0 or h <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"seitenverhaeltnis 'B:H' erwartet, "
                         f"nicht {seitenverhaeltnis!r}") from None
    crop = (f"crop=w='min(iw,ih*{b}/{h})':h='min(ih,iw*{h}/{b})'")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf", crop,
            "-c:a", "copy", dst]


def build_interpolation_args(src: str, dst: str, ziel_fps: int) -> list[str]:
    """Bewegungs-Interpolation (Slow-Mo/Smoothing) via ffmpeg minterpolate
    (motion-compensated, 0-€-Boden). RIFE = vorbereiteter Ausbau (E4;
    freie Modelle direkt, NICHT der AGPL-Enhancer)."""
    if ziel_fps <= 0:
        raise ValueError("ziel_fps muss > 0 sein")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf",
            f"minterpolate=fps={ziel_fps}:mi_mode=mci", "-c:a", "copy", dst]


def build_video_scale_args(src: str, dst: str, faktor: int = 2) -> list[str]:
    """Video-Upscale (Lanczos, 0-€-Boden); ESRGAN-Video = Ausbau (E4)."""
    if faktor < 2:
        raise ValueError("faktor muss >= 2 sein")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf",
            f"scale=iw*{faktor}:ih*{faktor}:flags=lanczos",
            "-c:a", "copy", dst]


def build_filmkorn_args(src: str, dst: str, staerke: float = 0.4) -> list[str]:
    """Film-Korn: SVT-AV1 In-Codec-Film-Grain — das Korn wird
    PRO FRAME beim Dekodieren neu synthetisiert (temporal flackerfrei, bitraten-
    billig, kein Detailverlust durch Encoder-Glättung; AR-Korn-Modell im Frame-
    Header signalisiert). Genau der natürliche „Fehler", der Video echt macht,
    OHNE den Bild-Asymmetrie-Warp (der wäre pro Frame identisch = Dauerverzerrung).
    Verkaufs-sicher: libsvtav1 = BSD-3 + AOM royalty-free, Werkzeug nicht
    eingebettet. ``staerke`` 0..1 → film-grain 0..~30. Braucht ein ffmpeg MIT
    libsvtav1 (sonst honest-fail über ffmpeg)."""
    g = max(0, min(50, round(max(0.0, min(1.0, staerke)) * 30)))
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-c:v", "libsvtav1",
            "-preset", "8", "-crf", "30",
            "-svtav1-params", f"film-grain={g}:film-grain-denoise=0",
            "-c:a", "copy", dst]


# --- Reel-Veredelung (P22-C: Loop-Montage · Export-Preset · Musik-Naht) ---------

def build_boomerang_args(src: str, dst: str) -> list[str]:
    """Pendel-Loop (E-F6 a): Clip vorwärts + rückwärts verkettet — verdoppelt die
    Länge und wirkt bei subtiler Bewegung natürlich nahtlos (der letzte Frame IST
    der erste). Video-only (Wan-Reels sind stumm; Ton kommt über die Musik-Naht)."""
    fc = "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[v]"
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-filter_complex", fc,
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", dst]


def build_xfade_loop_args(src: str, dst: str, *, dauer_s: float,
                          xfade_s: float = 0.5) -> list[str]:
    """Crossfade-Naht (E-F6 b): überblendet das Clip-Ende (ab ``dauer−xfade``) mit
    dem Anfang (die ersten ``xfade`` Sekunden) ⇒ nahtloser Loop, Länge ≈ ``dauer``.
    Video-only. ``dauer_s`` = Clip-Länge (aus ``FfmpegRand.dauer``)."""
    if dauer_s <= xfade_s:
        raise ValueError("dauer_s muss > xfade_s sein")
    if xfade_s <= 0:
        raise ValueError("xfade_s muss > 0 sein")
    off = dauer_s - xfade_s
    fc = (f"[0:v]split[a][b];"
          f"[b]trim=0:{xfade_s:.3f},setpts=PTS-STARTPTS[b2];"
          f"[a]setpts=PTS-STARTPTS[a2];"
          f"[a2][b2]xfade=transition=fade:duration={xfade_s:.3f}:"
          f"offset={off:.3f}[v]")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-filter_complex", fc,
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", dst]


def build_reel_export_args(src: str, dst: str, *, breite: int, hoehe: int,
                           fps: int = 24) -> list[str]:
    """Export auf ein Ziel-Format (Preset): skaliert seitenverhältnis-erhaltend in
    ``breite×hoehe`` (Rest gepadded), setzt ``fps``, kodiert nach H.264/yuv420p
    (breit abspielbar). Single-Input-Pendant zu ``build_concat_filter_args``."""
    if breite <= 0 or hoehe <= 0 or fps <= 0:
        raise ValueError("breite/hoehe/fps müssen > 0 sein")
    vf = (f"scale={breite}:{hoehe}:force_original_aspect_ratio=decrease,"
          f"pad={breite}:{hoehe}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", dst]


def build_audio_unter_args(video_src: str, audio_src: str, dst: str, *,
                           fade_s: float = 0.5, dauer_s: float = 0.0) -> list[str]:
    """Legt einen Musik-Track unter ein (stummes) Reel: ``afade`` in (0..fade_s)
    und – wenn die Länge bekannt ist – out (dauer−fade_s..dauer); Video-Stream
    verlustfrei kopiert, auf die kürzere Länge (``-shortest``). KEIN Ducking (kein
    O-Ton/Sprache — das ist ``symbiose.build_vertonung_args``' Domäne). W-V7:
    Reel + eigene Musik aus EINEM lizenzierten Haus."""
    fade_s = max(0.0, fade_s)
    af = f"afade=t=in:st=0:d={fade_s:.3f}"
    if dauer_s and dauer_s > fade_s:
        af += f",afade=t=out:st={dauer_s - fade_s:.3f}:d={fade_s:.3f}"
    return ["ffmpeg", "-hide_banner", "-y", "-i", video_src, "-i", audio_src,
            "-filter_complex", f"[1:a]{af}[a]", "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-shortest", dst]


def build_nn_scale_args(src: str, dst: str, faktor: int = 4) -> list[str]:
    """Nearest-Neighbor-Skalierung (Bild): die EINZIG richtige Vergrößerung
    für Pixel-Art (§R-F F2 — ESRGAN würde das Raster zerstören)."""
    if faktor < 2:
        raise ValueError("faktor muss >= 2 sein")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf",
            f"scale=iw*{faktor}:ih*{faktor}:flags=neighbor", dst]


def build_loudnorm_args(src: str, dst: str, lufs: float = -14.0,
                        tp: float = -1.5, lra: float = 11.0) -> list[str]:
    """Mastering-Endstufe (E4 Musik): ffmpeg ``loudnorm`` auf das
    Plattform-LUFS-Ziel (Streaming −14 / Apple −16 / Club −8, §R-F F4)."""
    if not (-70.0 <= lufs <= -5.0):
        raise ValueError(f"lufs außerhalb des sinnvollen Bereichs: {lufs}")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-af",
            f"loudnorm=I={lufs}:TP={tp}:LRA={lra}", "-ar", "48000", dst]


_LOUDNORM_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh",
                  "target_offset")


def build_loudnorm_measure_args(src: str, lufs: float = -14.0, tp: float = -1.5,
                                lra: float = 11.0) -> list[str]:
    """Mess-Pass (1/2) des 2-Pass-Loudnorm (§18 #6): analysiert die Eingabe und
    DRUCKT die gemessenen Werte als JSON nach stderr — kein Output-File
    (``-f null -``, der Lauf endet auf ``-`` ⇒ FfmpegRand wirft nicht)."""
    return ["ffmpeg", "-hide_banner", "-i", src, "-af",
            f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json",
            "-f", "null", "-"]


def parse_loudnorm_measured(stderr: str) -> dict[str, str] | None:
    """Extrahiert den (flachen) Loudnorm-JSON-Block aus dem Mess-Pass-stderr —
    ``input_i/tp/lra/thresh`` + ``target_offset``. ``None``, wenn kein gültiger
    Block da ist (⇒ ehrlicher Fallback auf den 1-Pass)."""
    for m in re.finditer(r"\{[^{}]*\}", stderr or ""):
        try:
            d = json.loads(m.group(0))
        except ValueError:
            continue
        if all(k in d for k in _LOUDNORM_KEYS):
            return {k: str(d[k]) for k in _LOUDNORM_KEYS}
    return None


def build_loudnorm_apply_args(src: str, dst: str, measured: dict[str, str],
                              lufs: float = -14.0, tp: float = -1.5,
                              lra: float = 11.0) -> list[str]:
    """Anwende-Pass (2/2): normalisiert mit den GEMESSENEN Werten + ``linear=true``
    — der präzise Mastering-Standard gegenüber dem einmaligen 1-Pass (§18 #6)."""
    if not (-70.0 <= lufs <= -5.0):
        raise ValueError(f"lufs außerhalb des sinnvollen Bereichs: {lufs}")
    af = (f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"
          f":measured_I={measured['input_i']}"
          f":measured_TP={measured['input_tp']}"
          f":measured_LRA={measured['input_lra']}"
          f":measured_thresh={measured['input_thresh']}"
          f":offset={measured['target_offset']}:linear=true:print_format=summary")
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-af", af,
            "-ar", "48000", dst]


def untertitel_filterpfad(srt_pfad: str) -> str:
    """Pfad-Escaping für den subtitles-Filter (Windows-Falle: Backslashes
    und Laufwerks-Doppelpunkt müssen escaped werden — pur, testbar)."""
    return srt_pfad.replace("\\", "/").replace(":", r"\:")


def build_untertitel_args(src: str, srt: str, dst: str) -> list[str]:
    """Brennt Untertitel (SRT) ins Bild (Caption-Pflicht der Kurzform-
    Profile, §R-F F3)."""
    return ["ffmpeg", "-hide_banner", "-y", "-i", src, "-vf",
            f"subtitles='{untertitel_filterpfad(srt)}'", "-c:a", "copy", dst]


_SIL_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SIL_END = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


def parse_silences(ffmpeg_stderr: str) -> list[dict[str, float]]:
    """Parst silencedetect-Ausgabe zu [{start, end, dauer}] (pur, testbar)."""
    out: list[dict[str, float]] = []
    start: float | None = None
    for line in ffmpeg_stderr.splitlines():
        m = _SIL_START.search(line)
        if m:
            start = float(m.group(1))
            continue
        m = _SIL_END.search(line)
        if m and start is not None:
            out.append({"start": start, "end": float(m.group(1)),
                        "dauer": float(m.group(2))})
            start = None
    return out


# --- Ausführung (dünner subprocess-Rand) ---------------------------------------

class FfmpegEditor:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def health(self) -> bool:
        return shutil.which(self.ffmpeg) is not None

    def probe(self, src: Path) -> dict[str, Any]:
        r = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(src)],
            capture_output=True, text=True, timeout=60, check=True)
        return json.loads(r.stdout)

    def hat_audio(self, src: Path) -> bool:
        """True, wenn die Datei mindestens einen Audio-Stream hat (für die
        Symbiose: tonlose Wan-Clips dürfen den ``[0:a]``-Filtergraph NICHT
        referenzieren). honest-fail: kann ffprobe es nicht prüfen, nehmen wir
        **False** an (= der nicht-crashende Musik-only-Pfad — konsistent mit
        ``video.FfmpegRand.hat_audio``)."""
        try:
            streams = self.probe(Path(src)).get("streams", [])
        except Exception:
            return False
        return any(s.get("codec_type") == "audio" for s in streams)

    def cut(self, job: Job) -> dict[str, Any]:
        """``job.params``: {src, dst, start_s, end_s, reencode?}."""
        p = job.params
        args = build_cut_args(str(p["src"]), str(p["dst"]),
                              float(p["start_s"]), float(p["end_s"]),
                              bool(p.get("reencode", False)))
        args[0] = self.ffmpeg
        subprocess.run(args, capture_output=True, text=True, timeout=1800,
                       check=True)
        job.report(1.0)
        return {"dst": str(p["dst"])}

    def silences(self, src: Path, noise_db: float = -35.0,
                 min_s: float = 1.5) -> list[dict[str, float]]:
        args = build_silence_args(str(src), noise_db, min_s)
        args[0] = self.ffmpeg
        r = subprocess.run(args, capture_output=True, text=True, timeout=1800)
        return parse_silences(r.stderr)
