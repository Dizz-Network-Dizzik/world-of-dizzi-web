# Workflow-Katalog — ComfyUI-Graphen als DATEN (E6.3)

Jede Fähigkeit der Bild-/Video-Generierung liegt hier als versionierte
ComfyUI-**API-Format**-Vorlage: neue Fähigkeit = neue Datei, kein Code-Umbau.
`creatorapp/bild.py` füllt die Platzhalter (`fuelle_workflow`, pur + getestet)
und schickt den Graphen über `engine.generator.ComfyUIGenerator` (:8188).

## Platzhalter-Konvention
`__NAME__` als **kompletter** String-Wert wird TYP-ERHALTEND ersetzt
(`"__SEED__"` → `123` als Zahl); übrig gebliebene Platzhalter lösen einen
ehrlichen Fehler aus (kein stilles Weiterlaufen mit kaputtem Graphen).

| Vorlage | Zweck | Platzhalter |
|---|---|---|
| `bild_txt2img.json` | profilgesteuerte Generierung (SDXL-Klasse UND Flux-FP8-Komplett-Checkpoints — gleiche Knoten, andere Parameter) | `__CHECKPOINT__ __CLIP_SKIP__ __PROMPT__ __NEGATIV__ __BREITE__ __HOEHE__ __SEED__ __STEPS__ __CFG__ __SAMPLER__ __SCHEDULER__` |
| `bild_inpaint.json` | Veredlung: maskiertes Neu-Malen (E4; iterativ ≤25–30 %/Pass) | txt2img-Satz + `__BILD__ __MASKE__ __MASKE_WACHSEN__ __DENOISE__` |
| `bild_upscale.json` | Veredlung: ESRGAN-Klasse-Upscale (NICHT für Pixel-Art — Profil-Veredlung beachten) | `__BILD__ __UPSCALE_MODELL__` |
| `bild_hires.json` | Veredlung: Hires-Fix/Zwei-Pass (§R-G G3.1 — Latent-Upscale 1.5–2× + 2. Sampler-Pass denoise 0.35–0.55, der größte Detail-Sprung) | txt2img-Satz (ohne Maße) + `__BILD__ __FAKTOR__ __DENOISE__` |
| `bild_outpaint.json` | **P3.5 Outpainting** (Bild über den Rand erweitern: `ImagePadForOutpaint` polstert + liefert die Maske, dann Inpaint-Pass). **Core-ComfyUI, KEIN Custom-Node/Download.** | txt2img-Satz + `__BILD__ __LINKS__ __OBEN__ __RECHTS__ __UNTEN__ __FEATHERING__ __MASKE_WACHSEN__ __DENOISE__` |
| `video_wan_t2v.json` | Wan-2.2-T2V, offizielles Zwei-Stufen-Layout (High-Noise→Low-Noise, 14B-FP8, Apache-2.0); `__WECHSEL__` = Stufen-Grenze (Default steps/2), `__LAENGE__` = Frames auf 4n+1-Raster | `__UNET_HIGH__ __UNET_LOW__ __TEXTENCODER__ __VAE__ __PROMPT__ __NEGATIV__ __SEED__ __STEPS__ __CFG__ __SHIFT__ __WECHSEL__ __BREITE__ __HOEHE__ __LAENGE__ __FPS__` |
| `video_wan_i2v.json` | Wan-2.2-**I2V** (Bild→Video, §R-G G2: der Qualitäts-Trick — erst perfektes Standbild, dann animieren); wie T2V, aber `WanImageToVideo` + `__BILD__`-Startbild, I2V-UNETs | t2v-Satz + `__BILD__` (UNET-Defaults = `…i2v_high/low…`) |

### §R-G-Ausbau-Vorlagen — Custom-Nodes nötig (OPT-IN, sonst ehrlicher Job-Fehler)
> Diese Graphen brauchen ComfyUI-**Custom-Nodes + Modelle**, die NICHT zum Core
> gehören. Ohne sie liefert ComfyUI einen Fehler ⇒ der Job scheitert ehrlich
> (Gesetz 5: dokumentierte Vorbereitung). Modell-/Node-Namen sind via `params`
> übersteuerbar (Daten-Wahrheit liegt beim Nutzer-Setup), die Vorlagen sind
> geprüfte Start-Templates — je nach Custom-Node-Version evtl. anzupassen.

| Vorlage | Zweck | Custom-Node-Pack | Platzhalter |
|---|---|---|---|
| `bild_tile_upscale.json` | Tile-ControlNet-Upscale (§R-G G3.4 — Detail-Maximum) | Tile-ControlNet-Modell (`__CONTROLNET__`, je Checkpoint-Klasse) | Sampler-Satz + `__BILD__ __FAKTOR__ __STAERKE__ __DENOISE__ __CONTROLNET__` |
| `bild_sam_inpaint.json` | **P3 Text→Maske→Inpaint** („ändere nur die Jacke": GroundingDINO findet aus dem Text die Box, SAM verfeinert zur Maske, dann Inpaint-Pass) | `comfyui_segment_anything` (GroundingDINO + SAM ViT-H; Ordner `grounding-dino/`+`sams/` + `bert-base-uncased`) | Inpaint-Satz + `__MASKE_TEXT__ __MASKE_SCHWELLE__ __GDINO_MODELL__ __SAM_MODELL__` |
| `bild_controlnet.json` | **P3 ControlNet** (Struktur halten, Inhalt neu: Präprozessor liest Pose/Tiefe/Kanten, ControlNet zwingt die Generierung darauf, Prompt = Inhalt) | `comfyui_controlnet_aux` (AIO-Präprozessor) + ControlNet-Modell (Union-SDXL geladen) | Sampler-Satz + `__BILD__ __PRAEPROZESSOR__ __AUFLOESUNG__ __CONTROLNET__ __STAERKE__ __BREITE__ __HOEHE__` |
| `bild_ipadapter.json` | **P3 IP-Adapter** (Referenz-Stil/-Gesicht ohne Training: Quellbild = Referenz, Prompt = neuer Inhalt) | `ComfyUI_IPAdapter_plus` (cubiq) + IP-Adapter- + CLIP-Vision-Modelle (geladen) | Sampler-Satz + `__BILD__ __BREITE__ __HOEHE__ __PRESET__ __STAERKE__ __GEWICHT_TYP__` |
| `bild_relight.json` | **P9 IC-Light Relight V1** (Bild neu beleuchten per Licht-Prompt; **SD1.5 = verkaufs-sicher**, V2/Flux non-commercial). Eigener SD1.5-Checkpoint, NICHT das Bild-Profil. | `kijai/ComfyUI-IC-Light` (+KJNodes) + `iclight_sd15_fc/fbc` (models/unet) + SD1.5-Checkpoint | `__CHECKPOINT__ __ICLIGHT_MODELL__ __PROMPT__ __NEGATIV__ __BILD__ __SEED__ __STEPS__ __CFG__ __SAMPLER__ __SCHEDULER__ __DENOISE__` |
| `bild_anweisung.json` | **P13 Instruktions-Bearbeitung** (in Worten sagen, was sich ändert — „mach die Jacke rot"; **Qwen-Image-Edit-2511 = Apache-2.0 verkaufs-sicher**, ComfyUI-nativ). ⚠ Topologie best-effort, e2e-Finalisierung nach Modell-Download. | Modell-Downloads: Qwen-Diffusion + `qwen_2.5_vl`-Encoder + `qwen_image_vae` (16 GB ⇒ GGUF-Q4) | `__UNET__ __DTYPE__ __TEXTENCODER__ __VAE__ __BILD__ __PROMPT__ __NEGATIV__ __SEED__ __STEPS__ __CFG__ __SAMPLER__ __SCHEDULER__ __DENOISE__` |

`__BILD__`/`__MASKE__` sind ComfyUI-**Input-Namen** (vorher per
`POST /upload/image` hochgeladen — macht `ComfyUIGenerator.upload_bild`).
„Sampler-Satz" = `__CHECKPOINT__ __CLIP_SKIP__ __PROMPT__ __NEGATIV__ __SEED__
__STEPS__ __CFG__ __SAMPLER__ __SCHEDULER__`.

## Rezept-System (E3)
Ein Asset speichert NICHT den gefüllten Graphen, sondern `workflow`-Name +
Platzhalter-`werte` — Vorlage (versioniert, hier) + Werte = exakte
Reproduktion, kompakt im DAM-`meta.rezept`.

Video-VEREDLUNG (reframe/captions/interpolation/upscale) läuft bewusst über
ffmpeg-Befehlsbauer (engine/editor.py), nicht über ComfyUI-Graphen.
Geplant (Paket d): `audio_ace_step.json` — gleiche Konvention.
