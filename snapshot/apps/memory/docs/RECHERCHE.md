# Recherche-Dossier — Dizz Knowledge (Wissen & Archiv)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> Zweck: Konnektoren, Standards und **jetzt vorzusehende** Verbindungs-Vorbereitungen.

## 1. Feature-Baseline (Marktstandard)
Notizen/Wissens-Basis mit **Markdown**, **bidirektionalen Links** + Graph, Tags, Volltextsuche,
Web-Clipping, Highlights/Lesezeichen, Quellen-/Zitat-Verwaltung, **RAG-fähige Wissensablage** (zu
Dizzis L3-RAG passend). Vorbilder: **Obsidian** (lokal, Markdown, „linked thinking", Plugins),
Logseq, Zettelkasten-Prinzip; Referenz-Manager **Zotero**; Highlights **Readwise**.

## 2. Standard-Datenquellen & Konnektoren
- **Format-Standard: Markdown + YAML-Frontmatter** (portabel, zukunftssicher, lokal). Import/Export
  Markdown/CSV/JSON.
- **Highlights/Read-it-later:** Readwise/Reader, Raindrop (Bookmarks), Pocket-Export.
- **Referenzen/Wissenschaft:** **Zotero** (Bibliografie/Zitate), BibTeX.
- **Web-Clipping:** Browser-Extension/Bookmarklet → Artikel als Markdown.
- **KI-Brücke: MCP** ist 2025 der De-facto-Weg, mit dem Agenten auf Obsidian/Notion/Zotero/Readwise
  zugreifen — passt exakt zu Dizzis MCP-Architektur (Knowledge wird zur **Wissensquelle für Dizzi**).
- **Querverbindung:** **Dizz News** liefert Artikel/Clips, **Dizz Creating** zieht Recherche.

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **Markdown-Vault als kanonisches Speicherformat** (Dateien, kein DB-Lock-in) → maximale Portabilität,
  direkt RAG-indexierbar.
- **`KnowledgeImporter`-Interface**: `MarkdownImport`, `ReadwiseImport`, `ZoteroImport`, `WebClip`.
- **RAG-Index-Brücke zu Dizzi L3** (sqlite-vec + bge-m3 wird bereits im Kern genutzt) — Knowledge
  exponiert seine Inhalte für Dizzis Gedächtnis (klar als Vorbereitung dokumentieren).
- **MCP-Server** mit Such-/Lese-Tools (Dizzi fragt das Wissen ab).

## 4. App-eigener KI-Wächter-Kern
Auto-Verschlagwortung, **Verknüpfungs-/Ähnlichkeits-Vorschläge** (verwandte Notizen), „verwaiste"
Notizen, Zusammenfassungen, Wissenslücken. Synthese über Quellen — Stärke der RAG-Anbindung.

## 5. Sensible Daten & Sicherheit
Wissen kann private Inhalte enthalten → lokal-first respektieren; öffentliche Recherche darf Boost
nutzen, private Notizen nicht (Sensibel-Kennzeichnung pro Notiz/Vault-Bereich).

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **Markdown-Dateien + Frontmatter** statt proprietärer Blobs; Links als `[[wikilink]]` (Dizzis
  Gedächtnis nutzt dasselbe Muster → Konsistenz).
- Ein Importer-Interface; Such-Index (FTS) + Vektor-Index getrennt, beide ableitbar aus dem Vault.
- Keine Doppelhaltung: Knowledge ist die **eine** Wissensquelle, Dizzi indexiert sie (nicht kopieren).

## 7. Offene Entscheidungsfragen → Fragerunde
1. **✅ ENTSCHIEDEN (F-Q1, Architektur-KI 11.06., docs/11 §6b): Markdown-Vault (Obsidian-kompatibel) als natives
   Speicherformat im eigenen Kern.** Obsidian selbst ist proprietär + Desktop-App → keine Einbettung;
   das offene Vault-Format IST der eigene schlanke Kern (Dateien + FTS-/Vektor-Index, kein DB-Lock-in).
2. Nutzt du heute **Obsidian/Notion/Zotero/Readwise** (Import-Bedarf)?
3. Soll Dizz Knowledge die **primäre RAG-Wissensquelle** für Dizzi sein (enge Kopplung an L3)?
4. Abgrenzung **Knowledge ↔ Admin** (Wissen vs. amtliche Dokumente) festlegen.

## Quellen
- [Obsidian für PKM (2025)](https://www.glukhov.org/post/2025/07/obsidian-for-personal-knowledge-management/)
- [MCP & PKM — Agenten auf Obsidian/Zotero/Readwise](https://chatforest.com/guides/mcp-personal-knowledge-management-pkm/)
- [Readwise–Obsidian-Integration](https://calmevo.com/readwise-obsidian-integration/)
- [Beste PKM-Apps 2026](https://toolfinder.com/best/pkm-apps)
