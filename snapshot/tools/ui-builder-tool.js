(function(){
var COLS=12,ROWH=40;
var GCOLS=12,GROWH=26;
var CATS=[
 ['Köpfe & Text',[['appkopf','App-Kopf'],['header','Kopfzeile'],['text','Text / Label']]],
 ['Struktur & Ebenen',[['panel','＋ Neues Panel'],['oberregister','Oberregister / Ebenen'],['subpanel','Unterpanel']]],
 ['Eingaben',[['input','Eingabe'],['textarea','Mehrzeiler'],['search','Suchzeile'],['range','Schieberegler'],['upload','Datei-Upload']]],
 ['Auswahl & Schalter',[['select','Auswahl'],['checkbox','Checkbox'],['radio','Radio'],['toggle','Schalter'],['tabs','Tabs'],['stepper','Stepper']]],
 ['Anzeige & Status',[['badge','Badge'],['progress','Fortschritt'],['table','Tabelle'],['kpi','KPI-Karte'],['metric','Metrik-Karte'],['icon','Icon']]],
 ['Daten-Visualisierung',[['chart','Mini-Chart'],['gauge','Gauge'],['scatter','Streudiagramm'],['ring','Aktivitäts-Ringe'],['timeline','Zeitstrahl / Gantt'],['heatmap','Heatmap'],['cockpit','Spalten-Cockpit']]],
 ['Listen, Board & Kalender',[['liste','Liste'],['board','Kanban-Board'],['kalender','Kalender'],['kontakt','Kontakt / Avatar']]],
 ['Aktion & Vernetzung — Sonder',[['button','Knopf'],['link','Verknüpfungs-Chip'],['cmdk','Command-Palette']]]
];
var LBL={};CATS.forEach(function(c){c[1].forEach(function(k){LBL[k[0]]=k[1]})});
LBL.regtab='Oberregister-Reiter';LBL.filterchip='Bereich-Filter';LBL.regicon='Reiter-Icon';
var SD={button:1,link:1,subpanel:1,oberregister:1,cmdk:1,appkopf:1};
var CONTAINER={subpanel:1,oberregister:1};
var KOPFONLY={appkopf:1,oberregister:1};
var BOXKIND={table:1,chart:1,gauge:1,scatter:1,ring:1,timeline:1,cockpit:1,metric:1,kpi:1,progress:1,heatmap:1,liste:1,board:1,kalender:1};
var HELP={
 appkopf:['Die oberste App-Kopfzeile: Marken-Lockup (App-Name) links, rechts der Anmelde-/Sicherheits-Status.','Genau EINMAL pro App ganz oben — gibt Identität + zeigt die Schutzstufe.','Marke · Funktion · Tagline-Streifen · Stufe · Hochsicher-Symbol.','Nein — die Stufe kommt aus der Dizzi-ID-Anmeldung.'],
 oberregister:['Top-Register, das ganze SEITEN umschaltet (Übersicht/Projekte/Geschäft/Studium). Jeder Reiter = eine eigene Seite.','Wenn die App mehrere große Bereiche hat. Im Tool klickst du die Reiter und schaltest die Seite live um.','Ebenen/Reiter (Komma-getrennt) = die Seiten-Namen.','Nein selbst — aber jede Seite hat eigene Panels.'],
 header:['Eine Abschnitts-Überschrift = der KOPF eines Panels.','Fast jedes Panel braucht eine. Im Tool: setzt den Panel-Titel.','Beschriftung = der Überschriftstext.','Nein.'],
 text:['Erklärender Fließtext / Hinweis / Label.','Für Erläuterungen, Hinweise, statische Texte.','Beschriftung = der Text.','Nein.'],
 subpanel:['Aufklappbarer Unterbereich (Collapse) im Panel.','Für optionale/sekundäre Inhalte zum Ein-/Ausklappen (Details, Netzwerk-Übersicht).','Klapp-Rang 1=Hauptfalt, 2/3=tiefer. „＋ Element einfügen" füllt es.','Nein.'],
 input:['Einzeiliges Eingabefeld.','Wenn der Nutzer EINEN kurzen Wert eintippt (Name, Betrag).','Beschriftung = Label/Platzhalter.','Schreibt in die Daten (meist mit Speichern-Knopf).'],
 textarea:['Mehrzeiliges Textfeld.','Für längere Texte (Notiz, Beschreibung, Nachricht).','Beschriftung = Label.','Schreibt in die Daten.'],
 search:['Suchzeile mit Lupe.','Wenn man eine Liste/Tabelle durchsucht/filtert.','Beschriftung = Platzhalter.','Ja: mit der Liste/Tabelle verknüpfen, die sie filtert.'],
 range:['Schieberegler für einen Zahlenbereich.','Wenn man einen Wert stufenlos einstellt (Schwelle, Zoom).','Min / Max / Schritt.','Schreibt einen Zahlenwert; oft mit einer Anzeige verknüpft.'],
 upload:['Datei-Upload mit Drag&Drop.','Wenn der Nutzer Dateien/Belege hochlädt.','Beschriftung = Hinweistext.','Ja: lädt Dateien in Speicher/Tresor.'],
 select:['Aufklapp-Auswahl (Dropdown) — EINE Option aus vielen.','DEIN Filter-Fall: Select wählen → Tabelle darunter zeigt die passende Statistik (Kategorie, Zeitraum, Kunde).','Optionen (Komma-getrennt).','Ja — mit dem Element verknüpfen, das er steuert (z. B. die Tabelle).'],
 checkbox:['An/Aus-Häkchen (Mehrfachauswahl möglich).','Wenn etwas ein/aus ist oder man mehrere Filter-Optionen ankreuzt.','Beschriftung = Label.','Schreibt ja/nein; oft mit einer Ansicht verknüpft.'],
 radio:['Auswahl aus einer GRUPPE, von der nur EINE gleichzeitig aktiv sein darf — z. B. „Tag / Woche / Monat".','Wenn genau eine von wenigen festen Optionen den Modus/die Ansicht umschaltet.','Beschriftung = Label der Option.','Steuert, was darunter angezeigt wird (mit der Ziel-Anzeige verknüpfen).'],
 toggle:['Schalter (an/aus) als Pille.','Wie Checkbox, aber prominenter (Funktion ein/aus).','Beschriftung = Label.','Schreibt ja/nein.'],
 tabs:['Inline-Umschalter zwischen Ansichten im SELBEN Panel (kleiner als das Oberregister).','Wenn ein Panel mehrere Sichten derselben Daten hat (Liste/Board/Kalender).','Reiter (Komma-getrennt).','Nein; jeder Reiter zeigt andere Inhalte des Panels.'],
 stepper:['Plus/Minus-Zähler für eine kleine Zahl.','Wenn man eine Anzahl/Menge fein hoch/runter stellt.','Beschriftung = Label.','Schreibt eine Zahl.'],
 badge:['Kleiner Status-Marker (Pille) — z. B. „aktiv", „überfällig".','Um einen Zustand kompakt zu zeigen.','Status on/ok/warn/bad färbt die Pille.','Liest meist einen Status aus den Daten.'],
 progress:['Fortschrittsbalken.','Um einen Anteil/Fortschritt zu zeigen (Budget, Ziel).','Beschriftung = Label.','Liest einen Wert aus den Daten.'],
 table:['Datentabelle (Zeilen × Spalten).','Für strukturierte Daten als Liste/Tabelle (Rechnungen, Kunden, Statistik).','Spalten- und Zeilenzahl.','Ja — mit der Datenquelle/dem Filter verknüpfen, der sie speist.'],
 kpi:['Große Kennzahl mit Label.','Für die EINE wichtige Zahl (Umsatz, Nutzer, Score).','Wert + Beschriftung.','Liest einen Wert aus den Daten.'],
 metric:['Metrik-Karte: Wert + Trend + Mini-Sparkline.','Wie KPI, aber mit Trend/Verlauf.','Wert + Trend (+4%).','Liest Wert + Verlaufsdaten.'],
 icon:['Symbol / Icon.','Zur visuellen Markierung (neben Titeln, Knöpfen, Status).','Icon = Zeichen oder Name.','Nein.'],
 chart:['Mini-Diagramm (Linie/Balken/Donut).','Für Verläufe/Verteilungen (Umsatzkurve, Anteile).','Chart-Typ: line/bar/donut/sparkline.','Ja — mit der Datenreihe/dem Filter verknüpfen.'],
 gauge:['Tacho/Gauge für einen Score (0–Max).','Für einen Wert auf einer Skala (Readiness, Auslastung).','Wert + Maximum.','Liest einen Wert aus den Daten.'],
 scatter:['Streudiagramm — Korrelation zweier Größen.','Wenn man Zusammenhänge zeigt (Belastung↔Erholung).','X-Achse + Y-Achse.','Ja — mit den zwei Datenreihen verknüpfen.'],
 ring:['Aktivitäts-Ringe (Apple-Stil).','Für mehrere Ziel-Erreichungen auf einen Blick.','Anzahl der Ringe.','Liest die Ziel-/Ist-Werte.'],
 timeline:['Zeitstrahl / Gantt mit Balken.','Für Termine/Phasen/Fälligkeiten über Zeit (Projekte, Aging).','Zeitspanne.','Ja — mit den Terminen/Aufgaben verknüpfen.'],
 cockpit:['Mehrspaltiges Übersichts-Cockpit (Querverbindungen).','Je Bereich/Domäne eine Kennzahl nebeneinander (Executive-Cockpit).','Spalten (Komma-getrennt).','Ja — je Spalte eine Quell-App/Kennzahl.'],
 button:['Ein Knopf, der eine Aktion auslöst.','Wenn der Nutzer etwas startet (Anlegen, Senden, Öffnen, Filtern).','Stil: primary=Haupt · ghost=dezent · danger=rot · mini=klein · icon=nur Symbol.','Ja — im Feld „Aktion/Verknüpfung" festlegen, WAS er tut / welches Panel er öffnet.'],
 link:['Verknüpfungs-Chip zu einer ANDEREN App.','Um zur Quell-App/Detailseite zu springen (Netzwerk-Deeplink).','Ziel-App.','Ja — die Ziel-App.'],
 cmdk:['Befehls-Palette (Strg/⌘+K), globaler Schnellzugriff.','Für Tastatur-first-Navigation über die ganze App.','Keine.','Nein.'],
 panel:['Legt ein NEUES Panel (Karte mit Kopf + Inhalt) an.','Der Grund-Baustein: jede Funktionsgruppe = ein Panel.','Doppelklick auf den Kopf = Überschrift + Zweck; daraus Vorschläge.','Nein selbst; seine Elemente brauchen ggf. Links.'],
 heatmap:['Farb-Raster über zwei Dimensionen (Wochentag × Stunde).','Um Muster/Dichte zu zeigen (Aktivität, Posting-Zeiten).','Spalten × Zeilen.','Ja — mit den 2D-Werten verknüpfen.'],
 liste:['Eine Liste von Einträgen (Zeilen) mit optionalen Status-Punkten.','Für Aufzählungen (Aufgaben, Rechnungen, Apps, Nachrichten).','Einträge (Komma-getrennt) als Vorschau.','Ja — die echte Liste kommt aus der Datenquelle.'],
 board:['Kanban-Board: Spalten (Status) mit verschiebbaren Karten.','Für Arbeits-Flüsse (To-Do/Läuft/Fertig, Rechnungs-Status).','Spalten-Namen (Komma-getrennt).','Ja — die Karten kommen aus den Daten.'],
 kalender:['Monats-/Wochen-Kalender mit Terminen.','Für Termine/Zeitpläne (Plan-Termine, Posting-Plan, Tagebuch).','Keine Pflicht-Parameter.','Ja — die Termine kommen aus den Daten.'],
 kontakt:['Kontakt-Zeile: rundes Avatar (Initialen) + Name (+ Kanal-Herkunft).','Für Personen/Kunden (Smart Contacts, Kunden). Mit Communication vernetzt zeigt es den letzten Kanal.','Name (Avatar aus Initialen).','Ja — Kontaktdaten aus Communication/CRM.'],
 regtab:['Ein Reiter des Oberregisters — der Knopf, der auf eine ganze Seite schaltet.','Navigation zwischen den großen Bereichen (Übersicht/Geschäft/Studium …).','Beschriftung = Seitenname · Größe = Knopf-/Glow-Größe (Ecke ⤡ ziehen).','Schaltet die Seite um (Einfach-Klick).'],
 filterchip:['Ein Filter-Knopf der Bereichsleiste — grenzt den angezeigten Bereich ein.','Um Inhalte auf einen Bereich (z. B. Praktikum) zu filtern.','Beschriftung = Bereichsname.','Filtert die Seite auf diesen Bereich.'],
 regicon:['Das Symbol (Icon) eines Oberregister-Reiters.','Wenn die Icon-Größe getrennt von Knopf/Glow eingestellt werden soll.','Größe = Icon-Größe (im ✎-Modus die Ecke ⤡ ziehen).','Gehört zum Reiter; schaltet selbst nichts.']
};
var THEMES={metall:['#0b0d13','#07080d','#161b25','#1e2430','#eaeefb','#93a0b8','rgba(150,160,190,.18)'],
 neon:['#070611','#0d0a1c','#1a1430','#241b3e','#eef0ff','#9f93c6','rgba(150,120,210,.20)'],
 carbon:['#050507','#000000','#0c0d11','#15171c','#e8eaf0','#7e828f','rgba(255,255,255,.10)'],
 tag:['#eef1f7','#e3e8f1','#ffffff','#f4f7fc','#1b2333','#5b6473','rgba(20,30,50,.13)']};
var FARBE={cm:['#2fe7ff','#ff3df0','47,231,255','255,61,240'],feuer:['#ff8c00','#ff2400','255,140,0','255,36,0'],toxic:['#39ff14','#ff00ff','57,255,20','255,0,255'],smgd:['#3dffb0','#ffd23d','61,255,176','255,210,61']};
var R=document.getElementById('pbroot');
var S=load()||{app:'',theme:'metall',farbe:'cm',panels:[],active:null,open:null};
// ===== v19 Pixel-Mirror: schwere Klon-/CSS-Daten getrennt von S halten (S wird bei jedem Drag gespeichert) =====
var MIR=loadMir()||{css:null,vars:null,body:null,capW:0,kopfHtml:"",pageHtml:{}};
var mirStage=null,mirShadow=null,mirCssKey='';
function $(i){return document.getElementById(i)}
function uid(){return Math.random().toString(36).slice(2,8)}
function save(){try{localStorage.setItem('dizz_pb2',JSON.stringify(S))}catch(e){}}
function load(){try{return JSON.parse(localStorage.getItem('dizz_pb2'))}catch(e){return null}}
function saveMir(){try{localStorage.setItem('dizz_pb2_mir',JSON.stringify(MIR))}catch(e){}}
function loadMir(){try{return JSON.parse(localStorage.getItem('dizz_pb2_mir'))}catch(e){return null}}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function colW(){return $('pbCanvas').clientWidth/COLS}
function applyTheme(){var t=THEMES[S.theme]||THEMES.metall,f=FARBE[S.farbe]||FARBE.cm;
 R.style.setProperty('--bg',t[0]);R.style.setProperty('--bgd',t[1]);R.style.setProperty('--panel',t[2]);R.style.setProperty('--panel2',t[3]);R.style.setProperty('--fg',t[4]);R.style.setProperty('--mut',t[5]);R.style.setProperty('--line',t[6]);
 R.style.setProperty('--cy',f[0]);R.style.setProperty('--mg',f[1]);R.style.setProperty('--cyr',f[2]);R.style.setProperty('--mgr',f[3])}
function panelById(id){return S.panels.filter(function(p){return p.id===id})[0]}
function findEl(id){var r=null;S.panels.forEach(function(p){(p.els||[]).forEach(function(e){if(e.id===id)r={p:p,e:e};if(CONTAINER[e.kind])(e.els||[]).forEach(function(x){if(x.id===id)r={p:p,e:x}})})});return r}
function defProps(k){return({button:{variant:'primary'},select:{options:'Option A, Option B, Option C'},range:{min:0,max:100,step:1},badge:{state:'on'},icon:{name:'★'},table:{cols:3,rows:3},tabs:{items:'Tab 1, Tab 2'},chart:{ctype:'line'},link:{target:'Memory'},kpi:{value:'1.234'},subpanel:{rank:1},
 appkopf:{brand:'Dizz App',funktion:'Funktion',tagline:'Untertitel · Akzent-Streifen',stufe:'verifiziert',hochsicher:'nein'},
 oberregister:{items:'Übersicht, Tresor, Projekte, Geschäft'},
 gauge:{value:72,max:100},scatter:{xlab:'X-Achse',ylab:'Y-Achse'},ring:{rings:3},timeline:{span:'4 Wochen'},cockpit:{spalten:'Finanzen, Social, Wissen'},metric:{value:'72',trend:'+4%'},upload:{},cmdk:{},
 heatmap:{cols:7,rows:4},liste:{rows:'Eintrag A, Eintrag B, Eintrag C'},board:{spalten:'To-Do, Läuft, Fertig'},kalender:{},kontakt:{name:'Max M.'}})[k]||{}}
function mkEl(k){var e={id:uid(),kind:k,label:LBL[k],desc:'',props:defProps(k)};if(CONTAINER[k])e.els=[];return e}
function addTo(panel,k){var ne=mkEl(k);if(S.mirror){ne.synthetic=true;ne._moved=true;ne.mx=30;ne.my=30;ne.ew=BOXKIND[k]?220:150;ne.eh=BOXKIND[k]?90:34;}(panel.els=panel.els||[]).push(ne);S.open=ne.id;return ne}
function pv(e){var p=e.props||{};var k=e.kind;
 if(k==='header')return '<b style="font-weight:500;font-size:14px">'+esc(e.label)+'</b>';
 if(k==='text')return '<span style="color:var(--mut)">'+esc(e.label)+'</span>';
 if(k==='button'){var bs=p.variant==='primary'?'background:linear-gradient(180deg,rgba(var(--cyr),.28),rgba(var(--cyr),.12));border:1px solid rgba(var(--cyr),.6);color:var(--cy)':p.variant==='danger'?'background:rgba(255,70,70,.16);border:1px solid rgba(255,90,90,.6);color:#ff8f8f':p.variant==='ghost'?'border:1px solid var(--line);color:var(--fg)':p.variant==='mini'?'border:1px solid var(--line);color:var(--mut);padding:1px 8px;font-size:11px':'border:1px solid var(--line);color:var(--fg)';return '<span style="display:inline-flex;align-items:center;padding:3px 12px;border-radius:7px;font-size:12px;'+bs+'">'+(p.variant==='icon'?'★':esc(e.label))+'</span>';}
 if(k==='input'||k==='search'||k==='textarea')return '<span style="display:flex;align-items:center;width:100%;height:'+(k==='textarea'?'40px':'22px')+';border:1px solid var(--line);border-radius:6px;background:var(--panel);padding:0 8px;font-size:11px;color:var(--mut)">'+(k==='search'?'🔍 ':'')+esc(e.label||(k==='textarea'?'Mehrzeiler …':'Eingabe …'))+'</span>';
 if(k==='select')return '<span style="display:flex;align-items:center;min-width:120px;height:22px;border:1px solid var(--line);border-radius:6px;background:var(--panel);padding:0 8px;font-size:11px;color:var(--fg)">'+esc((p.options||'').split(',')[0]||'Auswahl')+'<span style="flex:1"></span><span style="color:var(--mut)">▾</span></span>';
 if(k==='range')return '<span style="display:flex;align-items:center;gap:7px;width:100%"><span style="position:relative;flex:1;height:5px;border-radius:3px;background:rgba(150,160,190,.25)"><span style="position:absolute;left:0;top:0;width:55%;height:100%;border-radius:3px;background:linear-gradient(90deg,var(--cy),var(--mg))"></span><span style="position:absolute;left:55%;top:50%;width:13px;height:13px;border-radius:50%;background:var(--fg);border:2px solid var(--cy);transform:translate(-50%,-50%)"></span></span><span style="font-size:10px;color:var(--mut);white-space:nowrap">'+esc(p.min)+'–'+esc(p.max)+'</span></span>';
 if(k==='checkbox')return '<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:14px;border:1px solid var(--cy);border-radius:3px;display:inline-flex;align-items:center;justify-content:center;color:var(--cy);font-size:11px">✓</span>'+esc(e.label)+'</span>';
 if(k==='radio')return '<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:13px;height:13px;border:1px solid var(--cy);border-radius:50%;display:inline-flex;align-items:center;justify-content:center"><span style="width:6px;height:6px;border-radius:50%;background:var(--cy)"></span></span>'+esc(e.label)+'</span>';
 if(k==='toggle')return '<span style="display:inline-flex;align-items:center;gap:7px"><span style="width:30px;height:16px;border-radius:9px;background:rgba(var(--cyr),.3);position:relative;display:inline-block"><span style="position:absolute;right:2px;top:2px;width:12px;height:12px;border-radius:50%;background:var(--cy)"></span></span>'+esc(e.label)+'</span>';
 if(k==='stepper')return '<span style="display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:7px;overflow:hidden;font-size:12px"><span style="padding:2px 8px;border-right:1px solid var(--line)">−</span><span style="padding:2px 10px">1</span><span style="padding:2px 8px;border-left:1px solid var(--line)">+</span></span>';
 if(k==='tabs')return (p.items||'').split(',').map(function(t){return '<span class="pvbadge" style="background:transparent;border:1px solid var(--line);color:var(--fg)">'+esc(t.trim())+'</span>'}).join(' ');
 if(k==='badge')return '<span class="pvbadge">'+esc(e.label)+'</span> <span style="font-size:10px;color:var(--mut)">'+esc(p.state)+'</span>';
 if(k==='progress'){var pct=Math.max(0,Math.min(100,parseFloat(p.value)||65));return '<span style="display:block;width:100%;height:9px;border-radius:5px;background:rgba(150,160,190,.22);overflow:hidden"><span style="display:block;width:'+pct+'%;height:100%;background:linear-gradient(90deg,var(--cy),var(--mg))"></span></span>';}
 if(k==='table'){var rows=Math.min(parseInt(p.rows)||3,4),cols=Math.min(parseInt(p.cols)||3,5),rr='';for(var tr=0;tr<rows;tr++){var cc='';for(var tc=0;tc<cols;tc++)cc+='<span style="display:inline-block;width:19px;height:9px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:'+(tr===0?'rgba(var(--cyr),.16)':'transparent')+'"></span>';rr+='<span style="display:block;line-height:0">'+cc+'</span>';}return '<span style="display:inline-block;border-top:1px solid var(--line);border-left:1px solid var(--line);border-radius:4px;overflow:hidden;vertical-align:middle">'+rr+'</span>';}
 if(k==='kpi')return '<b style="font-weight:500;font-size:15px">'+esc(p.value)+'</b> <span style="font-size:10px;color:var(--mut)">'+esc(e.label)+'</span>';
 if(k==='chart'){if(p.ctype==='donut')return '<svg width="26" height="26" viewBox="0 0 26 26" style="vertical-align:middle"><circle cx="13" cy="13" r="9" fill="none" stroke="var(--line)" stroke-width="4"/><circle cx="13" cy="13" r="9" fill="none" stroke="var(--cy)" stroke-width="4" stroke-dasharray="34 60" transform="rotate(-90 13 13)"/></svg> <span style="font-size:10px;color:var(--mut)">donut</span>';if(p.ctype==='line'||p.ctype==='sparkline')return '<svg width="58" height="24" viewBox="0 0 58 24" style="vertical-align:middle"><polyline points="2,18 12,10 22,14 32,5 42,12 56,4" fill="none" stroke="var(--cy)" stroke-width="2"/></svg> <span style="font-size:10px;color:var(--mut)">'+esc(p.ctype)+'</span>';return '<span style="display:flex;align-items:flex-end;gap:3px;height:100%;width:100%;min-height:24px">'+[45,75,35,90,60,50,72,40].map(function(h){return '<span style="flex:1;height:'+h+'%;background:linear-gradient(180deg,var(--cy),var(--mg));border-radius:1px"></span>';}).join('')+'</span>';}
 if(k==='icon')return esc(p.name)+' Icon';
 if(k==='link')return '<span class="pvchip">↪ '+esc(p.target)+'</span>';
 if(k==='appkopf')return '<div style="display:flex;align-items:center;gap:10px;width:100%">'
   +'<div style="min-width:0"><div style="white-space:nowrap"><b style="font-weight:500;font-size:15px;letter-spacing:.02em;color:var(--fg)">'+esc(p.brand)+'</b>'+(p.funktion?' <span style="color:var(--mut);font-size:12px">'+esc(p.funktion)+'</span>':'')+'</div>'
   +'<div style="height:3px;width:130px;border-radius:2px;margin:4px 0 3px;background:linear-gradient(90deg,var(--mg),var(--cy))"></div>'
   +(p.tagline?'<div style="font-size:10px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:280px">'+esc(p.tagline)+'</div>':'')+'</div>'
   +'<span style="flex:1"></span>'
   +'<span style="font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:8px;padding:2px 9px;white-space:nowrap">'+esc(p.stufe||'verifiziert')+'</span>'
   +(String(p.hochsicher)==='ja'?'<span title="hochsicher" style="color:var(--mg);font-size:16px">⛨</span>':'')+'</div>';
 if(k==='oberregister')return '<div style="display:flex;gap:6px;flex-wrap:wrap;width:100%">'+(p.items||'').split(',').map(function(t){var nm=t.trim();var act=(nm===S.activePage);return '<span data-page="'+esc(nm)+'" style="cursor:pointer;font-size:12px;padding:3px 11px;border-radius:8px;'+(act?'background:rgba(var(--mgr),.2);color:var(--mg);border:1px solid rgba(var(--mgr),.6)':'color:var(--mut);border:1px solid var(--line)')+'">'+esc(nm)+'</span>'}).join('')+'</div>';
 if(k==='gauge'){var gv=parseFloat(p.value)||0,gm=parseFloat(p.max)||100,fr=Math.max(0,Math.min(1,gv/gm)),an=Math.PI*(1-fr),ex=(23+20*Math.cos(an)).toFixed(1),ey=(24-20*Math.sin(an)).toFixed(1);return '<svg width="48" height="28" viewBox="0 0 46 27" style="vertical-align:middle"><path d="M3 24 A20 20 0 0 1 43 24" fill="none" stroke="var(--line)" stroke-width="4"/><path d="M3 24 A20 20 0 0 1 '+ex+' '+ey+'" fill="none" stroke="var(--cy)" stroke-width="4" stroke-linecap="round"/></svg> <b style="font-weight:500">'+esc(p.value)+'</b>';}
 if(k==='scatter'){var sp=[[6,18],[12,10],[18,14],[10,16],[20,7],[14,19],[22,12]];return '<svg width="30" height="26" viewBox="0 0 30 26" style="vertical-align:middle"><line x1="3" y1="23" x2="28" y2="23" stroke="var(--line)"/><line x1="3" y1="23" x2="3" y2="3" stroke="var(--line)"/>'+sp.map(function(pt){return '<circle cx="'+(pt[0]+2)+'" cy="'+pt[1]+'" r="1.6" fill="var(--cy)"/>';}).join('')+'</svg> <span style="font-size:10px;color:var(--mut)">'+esc(p.xlab)+'×'+esc(p.ylab)+'</span>';}
 if(k==='ring'){var rn=Math.min(parseInt(p.rings)||3,3),rc=['var(--cy)','var(--mg)','#7e8aa0'],rs='';for(var ri=0;ri<rn;ri++){var rr2=11-ri*3;rs+='<circle cx="14" cy="14" r="'+rr2+'" fill="none" stroke="'+rc[ri]+'" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="'+(2*Math.PI*rr2*0.72).toFixed(1)+' '+(2*Math.PI*rr2).toFixed(1)+'" transform="rotate(-90 14 14)"/>';}return '<svg width="28" height="28" viewBox="0 0 28 28" style="vertical-align:middle">'+rs+'</svg>';}
 if(k==='timeline')return '<span style="display:block;width:100%"><span style="display:block;width:96%;height:6px;background:rgba(var(--cyr),.45);border-radius:3px;margin:3px 0"></span><span style="display:block;width:62%;height:6px;background:rgba(var(--mgr),.55);border-radius:3px;margin:3px 0 3px 12%"></span><span style="display:block;width:44%;height:6px;background:rgba(var(--cyr),.45);border-radius:3px;margin:3px 0 0 28%"></span><span style="font-size:10px;color:var(--mut)">'+esc(p.span)+'</span></span>';
 if(k==='cockpit'){var ck=(p.spalten||'').split(',').slice(0,3);return '<span style="display:inline-flex;gap:5px;vertical-align:middle">'+ck.map(function(c){return '<span style="display:inline-block;width:40px;border:1px solid var(--line);border-radius:5px;padding:2px 4px;font-size:9px;color:var(--mut);overflow:hidden;white-space:nowrap;text-overflow:ellipsis"><b style="display:block;font-weight:500;color:var(--cy);font-size:12px;line-height:1">•</b>'+esc(c.trim())+'</span>';}).join('')+'</span>';}
 if(k==='metric')return '<b style="font-weight:500;font-size:15px">'+esc(p.value)+'</b> '+(p.trend?'<span class="pvbadge" style="background:rgba(var(--cyr),.16)">'+esc(p.trend)+'</span> ':'')+'<span style="display:inline-flex;align-items:flex-end;gap:1px;height:14px;vertical-align:middle">'+[6,9,5,11,8,12].map(function(h){return '<span style="width:3px;height:'+h+'px;background:var(--cy);opacity:.75"></span>';}).join('')+'</span>';
 if(k==='upload')return '⤓ Datei-Upload <span class="pvfld" style="width:40%"></span>';
 if(k==='cmdk')return '<span class="pvbadge">⌘K</span> Command-Palette';
 if(k==='heatmap'){var hc=Math.min(parseInt(p.cols)||7,10),hr=Math.min(parseInt(p.rows)||4,8),cells='';for(var hy=0;hy<hr;hy++)for(var hx=0;hx<hc;hx++){var hv=((hx*7+hy*13)%10)/10;cells+='<span style="background:rgba(var(--cyr),'+(0.1+hv*0.62).toFixed(2)+');border-radius:2px"></span>';}return '<span style="display:grid;grid-template-columns:repeat('+hc+',1fr);gap:2px;width:100%;height:100%;min-height:30px">'+cells+'</span>';}
 if(k==='liste'){var li=(p.rows||'').split(',').slice(0,6);return '<span style="display:flex;flex-direction:column;gap:3px;width:100%">'+li.map(function(t){return '<span style="display:flex;align-items:center;gap:6px;font-size:11px;border-bottom:1px solid var(--line);padding-bottom:2px"><span style="width:5px;height:5px;border-radius:50%;background:var(--cy);flex:0 0 auto"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(t.trim())+'</span></span>';}).join('')+'</span>';}
 if(k==='board'){var bc=(p.spalten||'').split(',').slice(0,4);return '<span style="display:flex;gap:5px;width:100%;align-items:flex-start;height:100%">'+bc.map(function(c){return '<span style="flex:1;min-width:0;border:1px solid var(--line);border-radius:5px;padding:3px;display:flex;flex-direction:column;gap:3px"><span style="font-size:9px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(c.trim())+'</span><span style="height:9px;background:rgba(var(--cyr),.16);border-radius:3px"></span><span style="height:9px;background:rgba(var(--mgr),.16);border-radius:3px"></span></span>';}).join('')+'</span>';}
 if(k==='kalender'){var d='';for(var di=0;di<28;di++)d+='<span style="aspect-ratio:1;border:1px solid var(--line);border-radius:2px;font-size:8px;display:flex;align-items:center;justify-content:center;'+(di===10||di===17?'background:rgba(var(--cyr),.25);color:var(--cy)':'color:var(--mut)')+'">'+(di+1)+'</span>';return '<span style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;width:100%">'+d+'</span>';}
 if(k==='kontakt'){var nm=(p.name||'?').trim(),ini=nm.split(/\s+/).map(function(w){return w[0]||'';}).join('').slice(0,2).toUpperCase();return '<span style="display:inline-flex;align-items:center;gap:8px"><span style="width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,rgba(var(--cyr),.35),rgba(var(--mgr),.35));display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:500;color:var(--fg);flex:0 0 auto">'+esc(ini||'•')+'</span><span style="min-width:0"><span style="display:block;font-weight:500;font-size:12px">'+esc(nm)+'</span><span style="font-size:9px;color:var(--mut)">Kontakt</span></span></span>';}
 return esc(e.label)}
function short(e){var d=(e.desc||'').trim();return d?(d.length>46?d.slice(0,46)+'…':d):''}
// §3.5 Element-zu-Element-Bindung: Optionen (andere Panels/Elemente), Auflösung, sichtbarer ↪-Marker.
function zielOptions(curId,sel){var o='<option value=""'+(sel?'':' selected')+'>(keine Bindung)</option>';
 S.panels.forEach(function(p){if(p.zone==='kopf')return;var pv2='panel:'+p.id;o+='<option value="'+pv2+'"'+(sel===pv2?' selected':'')+'>Panel: '+esc(p.title||'Panel')+'</option>';
  (p.els||[]).forEach(function(e){if(e.id===curId||CONTAINER[e.kind])return;var ev='el:'+e.id;o+='<option value="'+ev+'"'+(sel===ev?' selected':'')+'>· '+esc(LBL[e.kind])+' „'+esc(String(e.label||'').slice(0,16))+'"</option>';});});
 return o;}
function zielLabel(z){if(!z)return '';var m=String(z).split(':');if(m[0]==='panel'){var p=panelById(m[1]);return p?('Panel »'+(p.title||'Panel')+'«'):'';}var f=findEl(m[1]);return f?(LBL[f.e.kind]+' »'+(f.e.label||'')+'«'):'';}
function actMark(pp){var z=zielLabel(pp.zielId),a=pp.aktion||'';var t=a+((a&&z)?' → ':'')+z;return t?'<span class="gact" title="'+esc(t)+'">↪</span>':'';}
function editFields(e){var p=e.props||{};var x='';
 x+='<label>Beschriftung / Titel</label><input data-f="label" value="'+esc(e.label)+'">';
 x+='<label>Beschreibung &amp; Funktion — frei einsprechen/tippen (Riesentext ok)</label><textarea data-f="desc" placeholder="z. B. Öffnet den Beleg-Upload; speichert sofort; wird rot wenn überfällig; verknüpft mit Admin-Dokument …">'+esc(e.desc)+'</textarea>';
 if(e.kind==='button')x+='<label>Stil</label><select data-f="p.variant">'+opt(['primary','ghost','danger','mini','icon'],p.variant)+'</select>';
 if(e.kind==='select')x+='<label>Optionen (Komma-getrennt)</label><textarea data-f="p.options" style="min-height:40px">'+esc(p.options)+'</textarea>';
 if(e.kind==='tabs')x+='<label>Tabs (Komma-getrennt)</label><input data-f="p.items" value="'+esc(p.items)+'">';
 if(e.kind==='range')x+='<div class="rw"><div><label>Min</label><input type="number" data-f="p.min" value="'+esc(p.min)+'"></div><div><label>Max</label><input type="number" data-f="p.max" value="'+esc(p.max)+'"></div><div><label>Schritt</label><input type="number" data-f="p.step" value="'+esc(p.step)+'"></div></div>';
 if(e.kind==='badge')x+='<label>Status</label><select data-f="p.state">'+opt(['on','ok','warn','bad'],p.state)+'</select>';
 if(e.kind==='table'){x+='<div class="rw"><div><label>Spalten</label><input type="number" data-f="p.cols" value="'+esc(p.cols)+'"></div><div><label>Zeilen</label><input type="number" data-f="p.rows" value="'+esc(p.rows)+'"></div></div>';x+='<label>Spaltennamen (Komma-getrennt, optional — §3.4)</label><input data-f="p.colnames" value="'+esc(p.colnames||'')+'" placeholder="z. B. Datum, Betrag, Status">';}
 if(e.kind==='progress')x+='<label>Wert in % (0–100)</label><input type="number" data-f="p.value" value="'+esc(p.value||65)+'">';
 if(e.kind==='kpi')x+='<label>Wert</label><input data-f="p.value" value="'+esc(p.value)+'">';
 if(e.kind==='chart')x+='<label>Chart-Typ</label><select data-f="p.ctype">'+opt(['line','bar','donut','sparkline','heatmap','waterfall'],p.ctype)+'</select>';
 if(e.kind==='icon')x+='<label>Icon (Zeichen oder Name)</label><input data-f="p.name" value="'+esc(p.name)+'">';
 if(e.kind==='link')x+='<label>Ziel-App der Verknüpfung</label><select data-f="p.target">'+opt(['Memory','Plans','Communication','Money','Admin','Leading','Management','Creating'],p.target)+'</select>';
 if(e.kind==='subpanel')x+='<div class="rw"><div><label>Klapp-Rang (1 = Hauptfalt, 2/3 = Unterebenen)</label><select data-f="p.rank">'+opt([1,2,3],p.props.rank)+'</select></div><div><label>Standard-Zustand (§3.6)</label><select data-f="p.collapsed">'+opt(['offen','eingeklappt'],(p.collapsed==='eingeklappt'?'eingeklappt':'offen'))+'</select></div></div><div style="font-size:11px;color:var(--mut);margin-top:6px">Element aus der Palette wird in dieses Unterpanel gelegt, solange es offen ist. „eingeklappt" = im Bauplan standardmäßig zugeklappt.</div>';
 if(e.kind==='appkopf'){x+='<div class="rw"><div><label>Marke (betont)</label><input data-f="p.brand" value="'+esc(p.brand)+'"></div><div><label>Funktionsname (dezent)</label><input data-f="p.funktion" value="'+esc(p.funktion)+'"></div></div>';x+='<label>Akzent-Streifen / Tagline</label><input data-f="p.tagline" value="'+esc(p.tagline)+'">';x+='<div class="rw"><div><label>Stufe (rechts)</label><select data-f="p.stufe">'+opt(['angemeldet','verifiziert','hochsicher'],p.stufe)+'</select></div><div><label>Hochsicher-Symbol</label><select data-f="p.hochsicher">'+opt(['nein','ja'],p.hochsicher)+'</select></div></div>';}
 if(e.kind==='oberregister')x+='<label>Ebenen / Register (Komma-getrennt)</label><input data-f="p.items" value="'+esc(p.items)+'"><div style="font-size:11px;color:var(--mut);margin-top:6px">Jede Ebene ist eine umschaltbare Seite. Elemente, die du hier hineinlegst, bilden den Inhalt der aktiven Ebene.</div>';
 if(e.kind==='gauge')x+='<div class="rw"><div><label>Wert</label><input type="number" data-f="p.value" value="'+esc(p.value)+'"></div><div><label>Maximum</label><input type="number" data-f="p.max" value="'+esc(p.max)+'"></div></div>';
 if(e.kind==='scatter')x+='<div class="rw"><div><label>X-Achse</label><input data-f="p.xlab" value="'+esc(p.xlab)+'"></div><div><label>Y-Achse</label><input data-f="p.ylab" value="'+esc(p.ylab)+'"></div></div>';
 if(e.kind==='ring')x+='<label>Anzahl Ringe</label><input type="number" data-f="p.rings" value="'+esc(p.rings)+'">';
 if(e.kind==='timeline')x+='<label>Zeitspanne</label><input data-f="p.span" value="'+esc(p.span)+'">';
 if(e.kind==='cockpit')x+='<label>Spalten (Komma-getrennt)</label><input data-f="p.spalten" value="'+esc(p.spalten)+'">';
 if(e.kind==='metric')x+='<div class="rw"><div><label>Wert</label><input data-f="p.value" value="'+esc(p.value)+'"></div><div><label>Trend</label><input data-f="p.trend" value="'+esc(p.trend)+'"></div></div>';
 if(e.kind==='heatmap')x+='<div class="rw"><div><label>Spalten</label><input type="number" data-f="p.cols" value="'+esc(p.cols)+'"></div><div><label>Zeilen</label><input type="number" data-f="p.rows" value="'+esc(p.rows)+'"></div></div>';
 if(e.kind==='liste')x+='<label>Einträge (Komma-getrennt)</label><input data-f="p.rows" value="'+esc(p.rows)+'">';
 if(e.kind==='board')x+='<label>Spalten (Komma-getrennt)</label><input data-f="p.spalten" value="'+esc(p.spalten)+'">';
 if(e.kind==='kontakt')x+='<label>Name</label><input data-f="p.name" value="'+esc(p.name)+'">';
 if(!CONTAINER[e.kind]&&e.kind!=='appkopf')x+='<label>Aktion / Verknüpfung (optional) — was löst es aus, wohin verlinkt es?</label><input data-f="p.aktion" value="'+esc(p.aktion||'')+'" placeholder="z. B. öffnet Panel »Details« · springt zu Memory · vergrößert die Karte">';
 if(!CONTAINER[e.kind]&&e.kind!=='appkopf')x+='<label>Steuert / öffnet → (Bindung an ein anderes Panel/Element — wird als ↪ sichtbar)</label><select data-f="p.zielId">'+zielOptions(e.id,p.zielId)+'</select>';
 if(!CONTAINER[e.kind]&&e.kind!=='appkopf')x+='<div class="rw"><div><label>Kurzbeschreibung zeigen?</label><select data-f="p.showdesc">'+opt(['nein','ja'],(p.showdesc||'nein'))+'</select></div><div><label>Position</label><select data-f="p.descpos">'+opt(['daneben','unten'],(p.descpos||'daneben'))+'</select></div></div>';
 return x}
function opt(a,v){return a.map(function(o){return '<option '+(String(o)===String(v)?'selected':'')+'>'+esc(o)+'</option>'}).join('')}
function elRow(e,pid){
 if(CONTAINER[e.kind]){
  var ac=activeContainer();var actc=(ac&&ac.id===e.id)?' activecont':'';
  var coll=(e.kind==='subpanel'&&(e.props||{}).collapsed==='eingeklappt');
  // §3.3: Container-Blätter liegen auf einem EIGENEN Raster (frei verschieb-/größenbar, gx/gy/gw/gh
  // relativ zum Container); verschachtelte Container bleiben als Reihe darunter.
  var ckids=(e.els||[]);
  var cleaves=ckids.filter(function(x){return !CONTAINER[x.kind]});
  var cconts=ckids.filter(function(x){return CONTAINER[x.kind]});
  var cmaxb=0;cleaves.forEach(function(x){if(x.gx==null){x.gx=0;x.gy=cmaxb;x.gw=BOXKIND[x.kind]?6:4;x.gh=BOXKIND[x.kind]?4:2;}cmaxb=Math.max(cmaxb,(x.gy||0)+(x.gh||1));});
  var inner=(cleaves.length?'<div class="pgrid" data-grid="'+e.id+'" style="height:'+(Math.max(2,cmaxb)*GROWH)+'px">'+cleaves.map(elGrid).join('')+'</div>':'')+cconts.map(function(x){return elRow(x,pid)}).join('');
  var chev=(e.kind==='subpanel')?'<span class="cv" data-subcollapse="'+e.id+'" style="cursor:pointer;color:var(--mg);width:14px;text-align:center" title="Standard-Zustand (eingeklappt/offen) umschalten">'+(coll?'▸':'▾')+'</span>':'';
  var chead='<div class="conthead">'+chev+'<span data-edit="'+e.id+'" style="font-weight:500;cursor:pointer">'+esc(LBL[e.kind])+'</span> <span class="pvw" data-edit="'+e.id+'" style="cursor:pointer">'+pv(e)+'</span><span class="contadd" data-addin="'+e.id+'">＋ Element einfügen</span><span class="xe" data-delel="'+e.id+'">✕</span></div>';
  var cbox=coll?'':'<div style="margin:6px 0 0 8px;border-left:2px dashed '+(e.kind==='oberregister'?'rgba(var(--mgr),.5)':'var(--line)')+';padding-left:7px;display:block">'+(inner||'<button class="addhint" data-addin="'+e.id+'">＋ Hier ein Element einfügen …</button>')+'</div>';
  return '<div class="pbel cont'+actc+'" data-el="'+e.id+'">'+chead+cbox+'</div>';
 }
 var sh=short(e);var pp=e.props||{};
 var dsc=(pp.showdesc==='ja'&&sh)?'<span class="dsc">'+esc(sh)+'</span>':'';
 return '<div class="pbel" data-el="'+e.id+'" data-edit="'+e.id+'" title="Doppelklick = bearbeiten"><span class="pvw">'+pv(e)+'</span>'+dsc+actMark(pp)+'<span class="xe" data-delel="'+e.id+'">✕</span></div>';
}
function elGrid(e){var pp=e.props||{};var sh=short(e);var below=pp.descpos==='unten';
 var dsc=(pp.showdesc==='ja'&&sh)?'<span class="gdsc'+(below?' below':'')+'">'+esc(sh)+'</span>':'';
 var st='left:'+(e.gx/GCOLS*100).toFixed(3)+'%;top:'+(e.gy*GROWH)+'px;width:'+(e.gw/GCOLS*100).toFixed(3)+'%;height:'+(e.gh*GROWH)+'px';
 return '<div class="gel'+(S.sel===e.id?' sel':'')+'" data-el="'+e.id+'" data-edit="'+e.id+'" data-emove="'+e.id+'" title="Ziehen = verschieben · Ecke = Größe · Doppelklick = bearbeiten" style="'+st+'"><span class="gpv">'+pv(e)+'</span>'+dsc+actMark(pp)+'<span class="xe" data-delel="'+e.id+'">✕</span><span class="eresize" data-eresize="'+e.id+'"></span></div>';
}
// ===== Maßstabsgetreuer Modus (1:1-Übernahme): echte px-Rechtecke, skaliert auf die Canvas-Breite =====
function isScaled(){return S.refW>0;}
function SC(){var cw=$('pbCanvas').clientWidth;if(!cw){var pr=$('pbCanvas').parentElement;cw=(pr&&pr.clientWidth)||0;}if(!cw)cw=R.clientWidth||S.refW||900;return S.refW?(cw/S.refW):1;}
function elScaledHtml(e,sc){var pp=e.props||{};var mr=(S.mirror&&!e.synthetic)?' mreal':'';
 var st='position:absolute;left:'+((e.ex||0)*sc).toFixed(1)+'px;top:'+((e.ey||0)*sc).toFixed(1)+'px;width:'+(Math.max(8,(e.ew||40)*sc)).toFixed(1)+'px;height:'+(Math.max(8,(e.eh||18)*sc)).toFixed(1)+'px';
 if(CONTAINER[e.kind]){var inner=(e.els||[]).map(function(x){return elScaledHtml(x,sc)}).join('');
  return '<div class="gel cont-scaled'+mr+(S.sel===e.id?' sel':'')+'" data-el="'+e.id+'" data-edit="'+e.id+'" data-emove="'+e.id+'" title="Container · Ziehen=verschieben · Ecke=Größe · Doppelklick=bearbeiten" style="'+st+'"><span class="gpv" style="position:absolute;inset:0;display:block">'+inner+'</span><span class="xe" data-delel="'+e.id+'">✕</span><span class="eresize" data-eresize="'+e.id+'"></span></div>';}
 var hdr=e.kind==='header'?' hdr-scaled':'';
 return '<div class="gel'+hdr+mr+(S.sel===e.id?' sel':'')+'" data-el="'+e.id+'" data-edit="'+e.id+'" data-emove="'+e.id+'" title="Ziehen=verschieben · Ecke=Größe · Doppelklick=bearbeiten" style="'+st+'"><span class="gpv">'+pv(e)+'</span>'+actMark(pp)+'<span class="xe" data-delel="'+e.id+'">✕</span><span class="eresize" data-eresize="'+e.id+'"></span></div>';
}
function panelScaledHtml(p){var sc=SC();var act=S.active===p.id?' act':'';
 var elsHtml=(p.els||[]).map(function(e){return elScaledHtml(e,sc)}).join('');
 var st='left:'+((p.rx||0)*sc).toFixed(1)+'px;top:'+((p.ry||0)*sc).toFixed(1)+'px;width:'+(Math.max(20,(p.rw||100)*sc)).toFixed(1)+'px;height:'+(Math.max(16,(p.rh||40)*sc)).toFixed(1)+'px';
 return '<div class="pbpanel scaled'+act+'" data-panel="'+p.id+'" data-head="'+p.id+'" style="'+st+'">'+
  '<span class="pscaledtag" data-panel-edit="'+p.id+'" title="Doppelklick = Panel-Kopf / Zweck">'+esc(p.title||'Panel')+'</span>'+
  '<span class="xx" data-delpanel="'+p.id+'">✕</span>'+elsHtml+
  '<span class="presize" data-resize="'+p.id+'"></span></div>';
}
function kopfFlowHtml(p){var els=(p.els||[]).map(function(e){return elRow(e,p.id)}).join('');
 return '<div class="pbpanel kopfzone'+(S.active===p.id?' act':'')+'" data-panel="'+p.id+'" style="position:relative;left:0;top:0;width:100%;min-height:30px">'+
  '<div class="pbody khdr">'+(els||'<span style="font-size:11px;color:var(--mut)">App-Kopf / Oberregister</span>')+'</div>'+
  '<span class="presize" data-resize="'+p.id+'"></span></div>';
}
function panelHtml(p){var act=S.active===p.id?' act':'';
 var els=(p.els||[]).map(function(e){return elRow(e,p.id)}).join('');
 if(p.zone==='kopf'){
  return '<div class="pbpanel kopfzone'+act+'" data-panel="'+p.id+'" style="left:0;top:'+(p.y*ROWH)+'px;width:100%;min-height:'+(p.h*ROWH)+'px">'+
   '<div class="pbody khdr">'+(els||'<span style="font-size:11px;color:var(--mut)">App-Kopf / Oberregister aus der Palette wählen — erscheint hier sofort als finale Kopfzeile</span>')+'</div>'+
   '<span class="presize" data-resize="'+p.id+'"></span></div>';
 }
 var leaves=(p.els||[]).filter(function(e){return !CONTAINER[e.kind]});
 var conts=(p.els||[]).filter(function(e){return CONTAINER[e.kind]});
 var maxb=0;leaves.forEach(function(e){if(e.gx==null){e.gx=0;e.gy=maxb;e.gw=BOXKIND[e.kind]?6:4;e.gh=BOXKIND[e.kind]?4:2;}maxb=Math.max(maxb,(e.gy||0)+(e.gh||1));});
 var grows=Math.max(3,maxb);var need=Math.ceil((grows*GROWH+42)/ROWH);if((p.h||4)<need)p.h=need;
 var pgrid='<div class="pgrid" data-grid="'+p.id+'" style="height:'+(grows*GROWH)+'px">'+leaves.map(elGrid).join('')+'</div>';
 var contHtml=conts.map(function(e){return elRow(e,p.id)}).join('');
 var bodyInner=pgrid+contHtml+'<button class="addhint" data-addin="'+p.id+'">＋ Element einfügen …</button>';
 return '<div class="pbpanel'+act+'" data-panel="'+p.id+'" style="left:'+(p.x*100/COLS)+'%;top:'+(p.y*ROWH)+'px;width:'+(p.w*100/COLS)+'%;height:'+(p.h*ROWH)+'px">'+
  '<div class="phead" data-head="'+p.id+'"><span class="cv" data-collapse="'+p.id+'" title="Panel aufklappbar machen (Collapse-Ebene)">'+(p.collapsed?'▸':'▾')+'</span><span class="pt" data-panel-edit="'+p.id+'" title="Doppelklick = Kopfzeile + Zweck dieses Panels">'+esc(p.title||'Panel')+'</span><span class="wd">'+p.w+'/'+COLS+'</span><span class="pe-add" data-addin="'+p.id+'" title="Element in dieses Panel einfügen">＋</span><span class="xx" data-delpanel="'+p.id+'">✕</span></div>'+
  (p.collapsed?'':'<div class="pbody">'+bodyInner+'</div>')+
  '<span class="presize" data-resize="'+p.id+'"></span></div>';
}
function canvasH(){var m=4;S.panels.forEach(function(p){m=Math.max(m,p.y+p.h)});return (m*ROWH+24)+'px'}
function activeContainer(){if(S.open){var f=findEl(S.open);if(f&&CONTAINER[f.e.kind])return f.e}var p=panelById(S.active);return p}
function renderPal(){$('pbPal').innerHTML=CATS.map(function(c){return '<div class="pbcat"><span>'+esc(c[0])+'</span>'+c[1].map(function(k){return '<button class="pbchip'+(SD[k[0]]?' sd':'')+'" data-add="'+k[0]+'">'+esc(k[1])+'</button>'}).join('')+'</div>'}).join('')}
function render(){S.panels=S.panels.filter(function(p){return p.zone!=='kopf'||(p.els&&p.els.length)});
 var pgs=pageList();if(pgs.length&&pgs.indexOf(S.activePage)<0)S.activePage=pgs[0];
 S.panels.forEach(function(p){if(p.zone!=='kopf'&&p.page==null)p.page=pgs[0];});
 applyTheme();$('pbApp').value=S.app||'';$('pbTheme').value=S.theme;$('pbFarbe').value=S.farbe;
 var c=activeContainer();$('pbHint').textContent=(pgs.length>1?'📑 Seite „'+S.activePage+'" (Reiter im Seitenkopf klicken = umschalten).  ':'')+(c?('Neu → '+(CONTAINER[c.kind]?LBL[c.kind]+' „'+(c.label||'')+'"':'Panel „'+(c.title||'')+'"')+'. Element ziehen=verschieben · Ecke=Größe · Doppelklick=bearbeiten.'):'„＋ Neues Panel", dann anklicken.');
 var vis=S.panels.filter(function(p){return p.zone==='kopf'||pgs.length<=1||p.page===S.activePage;});
 var cv=$('pbCanvas');
 if(S.mirror&&MIR&&MIR.css){renderMirror();return;}
 clearMir();
 if(isScaled()){cv.classList.add('maszstab');var sc=SC();
  var kp=vis.filter(function(p){return p.zone==='kopf'}),pgp=vis.filter(function(p){return p.zone!=='kopf'});
  var maxb=0;pgp.forEach(function(p){maxb=Math.max(maxb,(p.ry||0)+(p.rh||0));});
  var kopfHtml=kp.length?'<div class="kopfflow">'+kp.map(kopfFlowHtml).join('')+'</div>':'';
  cv.innerHTML=kopfHtml+'<div class="pagewrap" style="height:'+(maxb*sc+12).toFixed(0)+'px">'+pgp.map(panelScaledHtml).join('')+'</div>';
  cv.style.height='auto';save();return;}
 cv.classList.remove('maszstab');
 cv.innerHTML=vis.map(panelHtml).join('');var m=4;vis.forEach(function(p){m=Math.max(m,p.y+p.h)});cv.style.height=(m*ROWH+24)+'px';save()}
// ===== Pixel-Mirror — die KOMPLETTE Seite als echtes DOM (echte App-CSS), 1:1 zur Browserbreite, in echtem Fluss =====
// Anzeige = Kopf-Region (Kopfzeile + Bereichs-Filterleiste + Oberregister, alle volle Breite) + die aktive Seite
// (zentrierter, schmalerer Inhalt mit echten Außen-Abständen). Alles im Shadow-Root mit der echten App-CSS,
// per transform auf die Werkzeug-Breite skaliert (capW = Browser-Breite bei der Übernahme ⇒ SC≈1, echtes 1:1).
function clearMir(){if(mirStage&&mirStage.parentNode)mirStage.parentNode.removeChild(mirStage);mirStage=null;mirShadow=null;mirCssKey='';var cv=$('pbCanvas');var ov=cv.querySelector('.movlayer');if(ov)ov.remove();cv.classList.remove('mir');R.classList.remove('mirror','editmode');$('pbHint').className='pbhint';var be=$('pbEditBtn');if(be)be.style.display='none';}
function buildMirStage(){var cv=$('pbCanvas');
 if(!mirStage||!cv.contains(mirStage)){mirStage=document.createElement('div');mirStage.className='mirstage';cv.insertBefore(mirStage,cv.firstChild);mirShadow=mirStage.attachShadow({mode:'open'});mirCssKey='';mirShadow.addEventListener('click',onMirClick,true);mirShadow.addEventListener('dblclick',onMirDbl,true);}
 var css=MIR.css||{links:[],styles:[]};var key=(css.links||[]).join('|')+'#'+(css.styles||[]).length;
 if(key!==mirCssKey){mirCssKey=key;
  var v=MIR.vars||{},vstr='';for(var k in v){vstr+=k+':'+v[k]+';';}
  var b=MIR.body||{};
  var head='<style>*{box-sizing:border-box}#dzhost{'+vstr+'display:block;font-family:'+(b.fontFamily||'system-ui,sans-serif')+';color:'+(b.color||'#eaeefb')+';font-size:'+(b.fontSize||'14px')+';line-height:'+(b.lineHeight||'1.45')+'}img,svg{max-width:none}.bgfx,.bgbrush,#bg-stage{display:none!important}[hidden]{display:none!important}#dzkopf,#dzmain,#dzkopf *,#dzmain *{pointer-events:auto}.pb-drill{margin:8px 0 10px 4px;border-left:2px solid rgba(var(--mg-rgb,255,61,240),.45);padding-left:9px}.zeile[data-dz-act],.li[data-dz-act]{cursor:pointer}</style>';
  head+=(css.styles||[]).map(function(s){return '<style>'+s+'</style>';}).join('');
  head+=(css.links||[]).map(function(h){return '<link rel="stylesheet" href="'+h+'">';}).join('');
  mirShadow.innerHTML=head+'<div id="dzhost" style="background:'+(b.background||'transparent')+'"><div id="dzwrap"><div id="dzkopf"></div><div id="dzmain"></div></div></div>';
 }}
function reserMir(){try{var k=mirShadow.getElementById('dzkopf'),mn=mirShadow.getElementById('dzmain');if(k)MIR.kopfHtml=k.innerHTML;if(mn&&S.activePage!=null)MIR.pageHtml[S.activePage]=mn.innerHTML;saveMir();}catch(e){}}
function renderMirror(){var cv=$('pbCanvas');cv.classList.add('maszstab','mir');R.classList.add('mirror');
 buildMirStage();
 var capW=MIR.capW||S.refW||1280;
 var cw=cv.clientWidth||(cv.parentElement&&cv.parentElement.clientWidth)||R.clientWidth||capW;
 var sc=capW?(cw/capW):1;
 var dz=mirShadow.getElementById('dzwrap'),k=mirShadow.getElementById('dzkopf'),mn=mirShadow.getElementById('dzmain');
 var pgs=pageList();if(pgs.length&&pgs.indexOf(S.activePage)<0)S.activePage=pgs[0];
 k.innerHTML=MIR.kopfHtml||'';
 mn.innerHTML=(MIR.pageHtml&&MIR.pageHtml[S.activePage])||'';
 [].slice.call(k.querySelectorAll('.mtab,.dz-register a,.dz-register button,[role=tab]')).forEach(function(t){t.classList.toggle('on',(t.textContent||'').trim()===S.activePage);});
 dz.style.cssText='width:'+capW+'px;transform-origin:0 0;transform:scale('+sc+')';
 var h=dz.scrollHeight||dz.offsetHeight||600;
 mirStage.style.height=(h*sc+2).toFixed(0)+'px';cv.style.height=(h*sc+6).toFixed(0)+'px';
 var be=$('pbEditBtn');if(be){be.style.display='inline-flex';be.classList.toggle('editon',!!S.edit);}
 R.classList.toggle('editmode',!!S.edit);
 $('pbHint').className='pbhint';
 $('pbHint').innerHTML=S.edit
  ?'<span class="ed">✎ Bearbeiten</span> — greifen=verschieben · Ecke ⤡=Größe · Doppelklick=Hintergrund · ✕=löschen · Unterpanel anklicken=auf/zu. Palette oben=einfügen.<span class="mlegend"><i><b style="border-color:var(--mg)"></b>Hauptpanel</i><i><b style="border-color:#ffb86b"></b>Unterpanel</i><i><b style="border-color:var(--cy)"></b>Element</i><i><b style="border-color:#42e896"></b>tiefer</i></span>'
  :'Pixel-Mirror — echte App-Oberfläche 1:1. Reiter oben = Seite wechseln · Aufklapp-Streifen funktionieren · Doppelklick = Hintergrund & Bearbeiten · „✎ Bearbeiten" = Verschieben/Größe/Einfügen.';
 save();buildMirOverlay();}
// View-Modus: Aufklapp-Streifen reagieren auf EINFACH-Klick (toggle), DOPPEL-Klick öffnet die Hintergrund-Bearbeitung
var pendSum=null;
function onMirClick(ev){
 // Seitenwechsel über die echten Oberregister-Reiter — in beiden Modi
 var t=ev.target.closest&&ev.target.closest('.mtab,.dz-register a,.dz-register button,[role=tab]');
 if(t){var nm=(t.textContent||'').trim().replace(/\s+/g,' ');var pgs=pageList();var hit=pgs.filter(function(p){return p&&(p===nm||(nm&&nm.indexOf(p)>=0));})[0];if(hit){ev.preventDefault();ev.stopPropagation();if(hit!==S.activePage){S.activePage=hit;render();}return;}}
 if(S.edit){ev.preventDefault();return;}
 // Drill-down: Klick auf eine „öffnende" Zeile zeigt/verbirgt die erfasste Detailansicht (echter Pfad, offline)
 var dz=ev.target.closest&&ev.target.closest('[data-dz-act],.zeile');
 if(dz){var row=dz.closest('.zeile')||dz;var dr=row.nextElementSibling;if(dr&&dr.classList&&dr.classList.contains('pb-drill')){ev.preventDefault();ev.stopPropagation();dr.hidden=!dr.hidden;return;}}
 // View-Modus: Aufklapp-Streifen — Einfach-Klick togglet, Doppel-Klick öffnet die Bearbeitung
 var sm=ev.target.closest&&ev.target.closest('summary');
 if(sm&&sm.parentElement&&sm.parentElement.tagName==='DETAILS'){ev.preventDefault();ev.stopPropagation();var det=sm.parentElement;
  if(pendSum){clearTimeout(pendSum.t);pendSum=null;return;}
  pendSum={t:setTimeout(function(){pendSum=null;det.open=!det.open;reserMir();},250)};return;}}
function onMirDbl(ev){if(S.edit)return;var n=ev.target.closest&&ev.target.closest('[data-pb-id]');if(!n)return;var id=n.getAttribute('data-pb-id');ev.preventDefault();ev.stopPropagation();var p=panelById(id);if(p){S.active=id;openPanelModal(id);return;}var f=findEl(id);if(f){S.active=f.p.id;openModal(id);}}
// ===== Bearbeiten-Ebene über dem Mirror: gestrichelte Boxen (aus den echten Klon-Rechtecken) =====
function mirElById(id){return mirShadow&&mirShadow.querySelector('[data-pb-id="'+id+'"]');}
function ovDepth(n){var d=0,a=n.parentElement;while(a){if(a.id==='dzmain'||a.id==='dzkopf')break;if(a.getAttribute&&a.getAttribute('data-pb-id'))d++;a=a.parentElement;}return d;}
function buildMirOverlay(){var cv=$('pbCanvas');var ov=cv.querySelector('.movlayer');
 if(!S.edit||!mirShadow){if(ov&&ov.parentNode)ov.parentNode.removeChild(ov);return;}
 if(!ov){ov=document.createElement('div');ov.className='movlayer';cv.appendChild(ov);}
 var crect=cv.getBoundingClientRect();var boxes=[];
 // Ebenen-Farbschema: jedes Element bekommt einen gestrichelten Rahmen in der Farbe SEINER Ebene
 // (Hauptpanel · Unterpanel · Element-Tiefe 1/2/3) — so sieht man sofort, was auf welcher Ebene liegt.
 [].slice.call(mirShadow.querySelectorAll('#dzkopf [data-pb-id],#dzmain [data-pb-id]')).forEach(function(n){var id=n.getAttribute('data-pb-id');
  var isP=!!panelById(id);var f=isP?null:findEl(id);
  if(!isP&&(!f||f.e.kind==='oberregister'||f.e.kind==='tabs'))return; // die volle-Breite-Leisten selbst NICHT boxen (ihre Reiter/Chips sind eigene Boxen)
  var r=n.getBoundingClientRect();if(r.width<6||r.height<5)return;
  var isSub=!!(f&&CONTAINER[f.e.kind]);var depth=ovDepth(n);
  var lv=isP?'lv-panel':(isSub?'lv-sub':('lv-e'+Math.min(Math.max(depth,1),3)));
  boxes.push({id:id,isP:isP,sub:isSub,depth:depth,lv:lv,l:Math.round(r.left-crect.left),t:Math.round(r.top-crect.top),w:Math.round(r.width),h:Math.round(r.height)});});
 S.panels.forEach(function(p){if(p.zone!=='kopf'&&p.page&&p.page!==S.activePage)return;(p.els||[]).forEach(function(e){if(e.synthetic)boxes.push({id:e.id,syn:true,lv:'lv-e1',l:(e.mx||24),t:(e.my||24),w:(e.ew||150),h:(e.eh||36)});});});
 // flach→tief stapeln, damit tiefere (kleinere) Boxen oben liegen
 boxes.sort(function(a,b){return (a.depth||0)-(b.depth||0);});
 ov.innerHTML=boxes.map(function(b){var sel=(S.sel===b.id)?' sel':'';var f=b.syn&&findEl(b.id);
  return '<div class="mov '+b.lv+(b.isP?' movp':'')+(b.sub?' movs':'')+(b.syn?' syn':'')+sel+'" data-mov="'+b.id+'" style="left:'+b.l+'px;top:'+b.t+'px;width:'+b.w+'px;height:'+b.h+'px">'+(f?('<span class="gpv" style="pointer-events:none;width:100%;overflow:hidden">'+pv(f.e)+'</span>'):'')+'<span class="mx" data-movdel="'+b.id+'">✕</span><span class="mh" data-movres="'+b.id+'"></span></div>';
 }).join('');}
var movd=null;
$('pbCanvas').addEventListener('pointerdown',function(ev){if(!S.edit)return;var box=ev.target.closest('.mov');if(!box||ev.target.closest('[data-movdel]'))return;
 var id=box.dataset.mov;var f=findEl(id);S.sel=id;
 [].slice.call(box.parentNode.querySelectorAll('.mov')).forEach(function(n){n.classList.toggle('sel',n===box);});
 movd={id:id,box:box,res:!!ev.target.closest('[data-movres]'),sx:ev.clientX,sy:ev.clientY,ol:parseFloat(box.style.left)||0,ot:parseFloat(box.style.top)||0,ow:parseFloat(box.style.width)||40,oh:parseFloat(box.style.height)||20,e:f?f.e:null,node:mirElById(id),moved:false,ntx:(f&&f.e.tx)||0,nty:(f&&f.e.ty)||0};
 try{box.setPointerCapture(ev.pointerId)}catch(e){}ev.preventDefault();ev.stopPropagation();},true);
$('pbCanvas').addEventListener('pointermove',function(ev){if(!movd)return;var dx=ev.clientX-movd.sx,dy=ev.clientY-movd.sy;if(!movd.moved){if(Math.abs(dx)<3&&Math.abs(dy)<3)return;movd.moved=true;}
 if(movd.res){var w=Math.max(10,movd.ow+dx),h=Math.max(8,movd.oh+dy);movd.box.style.width=w+'px';movd.box.style.height=h+'px';if(movd.e){movd.e.ew=Math.round(w);movd.e.eh=Math.round(h);}if(movd.node){movd.node.style.width=Math.round(w)+'px';movd.node.style.height=Math.round(h)+'px';}}
 else{movd.box.style.left=(movd.ol+dx)+'px';movd.box.style.top=(movd.ot+dy)+'px';if(movd.e&&movd.e.synthetic){movd.e.mx=Math.round(movd.ol+dx);movd.e.my=Math.round(movd.ot+dy);}else if(movd.node){movd.node.style.transform='translate('+Math.round(movd.ntx+dx)+'px,'+Math.round(movd.nty+dy)+'px)';if(movd.e){movd.e.tx=Math.round(movd.ntx+dx);movd.e.ty=Math.round(movd.nty+dy);}}}},true);
var movJustMoved=false;
function endMov(){if(!movd)return;var m=movd;movd=null;if(!m.moved)return;movJustMoved=true;setTimeout(function(){movJustMoved=false;},90);
 // Drag ZWISCHEN Panels: liegt die Mitte der losgelassenen Box über einer ANDEREN Panel-Karte? → umhängen
 var moved=false;
 if(S.mirror&&m.e&&!m.e.synthetic&&m.box&&!m.res){var f=findEl(m.id);
  if(f&&!panelById(m.id)&&'regtab regicon filterchip appkopf'.indexOf(m.e.kind)<0){
   var br=m.box.getBoundingClientRect(),cx=br.left+br.width/2,cy=br.top+br.height/2,tgt=null;
   [].slice.call(document.querySelectorAll('.movlayer .mov.movp')).forEach(function(pb){if(pb.dataset.mov===f.p.id)return;var r=pb.getBoundingClientRect();if(cx>=r.left&&cx<=r.right&&cy>=r.top&&cy<=r.bottom)tgt=pb.dataset.mov;});
   if(tgt){moveElToPanel(m.id,tgt);moved=true;}
  }}
 if(S.mirror&&!moved)reserMir();save();if(moved)render();}
$('pbCanvas').addEventListener('pointerup',endMov,true);$('pbCanvas').addEventListener('pointercancel',endMov,true);
$('pbCanvas').addEventListener('click',function(ev){if(!S.edit)return;var d=ev.target.closest('[data-movdel]');if(d){var id=d.dataset.movdel;ev.stopPropagation();if(panelById(id)){S.panels=S.panels.filter(function(p){return p.id!==id;});var pn=mirElById(id);if(pn&&pn.parentNode)pn.parentNode.removeChild(pn);reserMir();}else{delEl(id);}S.sel=null;render();return;}
 if(movJustMoved)return;var b=ev.target.closest('.mov');if(!b)return;var f=findEl(b.dataset.mov);
 if(f&&f.e.kind==='regtab'){var tgt=f.e.props&&f.e.props.target;var pgs=pageList();if(tgt&&pgs.indexOf(tgt)>=0&&tgt!==S.activePage){S.activePage=tgt;render();}return;}
 // Drill-down-Zeile im Edit-Modus anklicken = erfasste Detailansicht auf/zu ⇒ ihre Elemente werden box-/bearbeitbar
 if(f){var rn=mirElById(f.e.id);if(rn){var rrow=rn.closest('.zeile')||rn;var dn=rrow.nextElementSibling;if(dn&&dn.classList&&dn.classList.contains('pb-drill')){dn.hidden=!dn.hidden;reserMir();setTimeout(buildMirOverlay,0);return;}}}
 // Unterpanel anklicken = echtes <details> auf/zu + Rahmen neu berechnen (gestrichelte Linien klappen mit auf)
 if(f&&CONTAINER[f.e.kind]){var n=mirElById(f.e.id);if(n&&n.tagName==='DETAILS'){n.open=!n.open;reserMir();setTimeout(buildMirOverlay,0);}return;}
 },true);
$('pbCanvas').addEventListener('dblclick',function(ev){if(!S.edit)return;var b=ev.target.closest('.mov');if(!b)return;ev.stopPropagation();var id=b.dataset.mov;var p=panelById(id);if(p){S.active=id;openPanelModal(id);}else{var f=findEl(id);if(f){S.active=f.p.id;openModal(id);}}},true);
function setField(id,f,v){var f2=findEl(id);if(!f2)return;var e=f2.e;if(f.slice(0,2)==='p.'){e.props=e.props||{};e.props[f.slice(2)]=v}else if(/^(ex|ey|ew|eh)$/.test(f)){e[f]=parseInt(v)||0;e._moved=true;}else e[f]=v}

renderPal();render();

$('pbPal').addEventListener('click',function(ev){var b=ev.target.closest('[data-add]');if(!b)return;var k=b.dataset.add;var con;
 if(S.mirror){if(k==='header')return;if(k==='panel'){addPanel();S.edit=true;render();return;}
  var tp=panelById(S.active);if(!tp||tp.zone==='kopf'||(tp.page&&tp.page!==S.activePage))tp=S.panels.filter(function(p){return p.zone!=='kopf'&&(!p.page||p.page===S.activePage);})[0]||addPanel();
  addTo(tp,k);S.edit=true;render();return;}
 if(k==='panel'){var np=addPanel();render();return;}
 if(k==='header'){var hp=S.open?((findEl(S.open)||{}).p):panelById(S.active);if(!hp||hp.zone==='kopf')hp=normalPanel();S.active=hp.id;openPanelModal(hp.id);return;}
 if(KOPFONLY[k]){con=kopfZone();S.active=con.id;S.open=null;$('pbHint').textContent='„'+LBL[k]+'" an den Seitenkopf gelegt (gehört nicht ins Panel).';}
 else{con=activeContainer();var tp=S.open?((findEl(S.open)||{}).p):panelById(S.active);if(!con||(tp&&tp.zone==='kopf')){con=normalPanel();S.active=con.id;S.open=null;}}
 addTo(con,k);render();});
function pageList(){var kz=S.panels.filter(function(p){return p.zone==='kopf'})[0];if(kz){var or=(kz.els||[]).filter(function(e){return e.kind==='oberregister'})[0];if(or&&or.props&&or.props.items){var a=or.props.items.split(',').map(function(s){return s.trim();}).filter(function(s){return s;});if(a.length)return a;}}return [''];}
function addPanel(){var pg=S.activePage||(pageList()[0]||'');var y=0;S.panels.forEach(function(p){if(p.zone==='kopf'||(p.page||'')===pg)y=Math.max(y,p.y+p.h)});var np={id:uid(),title:'Neues Panel',page:pg,x:0,y:y,w:6,h:4,collapsed:false,rank:1,els:[]};
 if(isScaled()){var rb=0;S.panels.forEach(function(p){if(p.page===pg&&p.ry!=null)rb=Math.max(rb,p.ry+(p.rh||0));});np.rx=40;np.ry=rb+15;np.rw=Math.max(200,(S.refW||1200)-80);np.rh=160;}
 S.panels.push(np);S.active=np.id;S.open=null;return np}
function kopfZone(){var z=S.panels.filter(function(p){return p.zone==='kopf'})[0];if(z)return z;z={id:uid(),title:'Seitenkopf',zone:'kopf',x:0,y:0,w:12,h:2,collapsed:false,rank:1,els:[]};S.panels.forEach(function(p){p.y+=2});S.panels.unshift(z);return z}
function normalPanel(){var p=S.panels.filter(function(p){return p.zone!=='kopf'})[0];return p||addPanel()}

$('pbHint').addEventListener('click',function(ev){var mp=ev.target.closest('[data-mpage]');if(mp){S.activePage=mp.dataset.mpage;S.sel=null;render();}});
$('pbApp').addEventListener('input',function(){S.app=$('pbApp').value;save()});
$('pbTheme').addEventListener('change',function(){S.theme=$('pbTheme').value;render()});
$('pbFarbe').addEventListener('change',function(){S.farbe=$('pbFarbe').value;render()});
R.querySelector('.pbtop').addEventListener('click',function(ev){var b=ev.target.closest('[data-act]');if(!b)return;var a=b.dataset.act;
 if(a==='addPanel'){addPanel();render()}
 else if(a==='editmode'){S.edit=!S.edit;S.sel=null;render();}
 else if(a==='loadapp'){loadAppUI()}
 else if(a==='io'){openIO()}
 else if(a==='tpl'){tpl();render()}
 else if(a==='reset'){if(confirm('Alles zurücksetzen?')){S={app:'',theme:S.theme,farbe:S.farbe,panels:[],active:null,open:null,mirror:false};MIR={css:null,vars:null,body:null,capW:0,kopfHtml:"",pageHtml:{}};saveMir();clearMir();render();}}
 else if(a==='export'){doExport()}});

$('pbCanvas').addEventListener('click',function(ev){
 if(justMoved)return;
 var pg=ev.target.closest('[data-page]');if(pg){S.activePage=pg.dataset.page;S.sel=null;render();return}
 var dp=ev.target.closest('[data-delpanel]');if(dp){S.panels=S.panels.filter(function(p){return p.id!==dp.dataset.delpanel});if(S.mirror){delete MIR.html[dp.dataset.delpanel];saveMir();}if(S.active===dp.dataset.delpanel){S.active=(S.panels[0]||{}).id||null;S.open=null;}render();return}
 var de=ev.target.closest('[data-delel]');if(de){delEl(de.dataset.delel);render();return}
 var cl=ev.target.closest('[data-collapse]');if(cl){var p=panelById(cl.dataset.collapse);p.collapsed=!p.collapsed;render();return}
 var sc=ev.target.closest('[data-subcollapse]');if(sc){var fs=findEl(sc.dataset.subcollapse);if(fs){fs.e.props=fs.e.props||{};fs.e.props.collapsed=(fs.e.props.collapsed==='eingeklappt'?'offen':'eingeklappt');render();}return}
 var ai=ev.target.closest('[data-addin]');if(ai){openAdd(ai.dataset.addin);return}
 var elx=ev.target.closest('[data-el]');
 if(elx){var f2=findEl(elx.dataset.el);if(f2){S.active=f2.p.id;S.open=CONTAINER[f2.e.kind]?elx.dataset.el:null;S.sel=elx.dataset.el;}refreshActive();return}
 var pn=ev.target.closest('[data-panel]');if(pn){S.active=pn.dataset.panel;S.open=null;S.sel=null;refreshActive();}});
$('pbCanvas').addEventListener('dblclick',function(ev){var pp=ev.target.closest('[data-panel-edit]');if(pp){S.active=pp.dataset.panelEdit;openPanelModal(pp.dataset.panelEdit);return;}var pe=ev.target.closest('[data-edit]');if(!pe)return;var f=findEl(pe.dataset.edit);if(f){S.active=f.p.id;openModal(pe.dataset.edit);}});
function refreshActive(){R.querySelectorAll('.pbpanel').forEach(function(n){n.classList.toggle('act',n.dataset.panel===S.active)});var ac=activeContainer();R.querySelectorAll('.pbel.cont').forEach(function(n){n.classList.toggle('activecont',!!ac&&ac.id===n.dataset.el)});R.querySelectorAll('.gel').forEach(function(n){n.classList.toggle('sel',n.dataset.el===S.sel)});updateHint();save();}
function updateHint(){var c=activeContainer();$('pbHint').textContent=c?('Neues Element → '+(CONTAINER[c.kind]?LBL[c.kind]+' „'+(c.label||'')+'"':'Panel „'+(c.title||'')+'"')+'.  Element ziehen = verschieben (Raster) · Ecke = Größe · Doppelklick = bearbeiten.'):'Erst „＋ Neues Panel", dann anklicken. Panel am Kopf ziehen, an der Ecke ⤡ größen-rastern.';}
// Pixel-Mirror: „Hintergrund-Ebene" je Element (Was ist das · Funktion · eigene Seite · öffnet Panel)
function panelOpts(curPid){return S.panels.filter(function(p){return p.zone!=='kopf'&&p.id!==curPid&&(!S.mirror||!p.page||p.page===S.activePage);}).map(function(p){return '<option value="'+p.id+'">'+esc(p.title||'Panel')+(p.page?' · '+esc(p.page):'')+'</option>';}).join('');}
function mirrorInfo(e,p){var pp=e.props||{};var was;
 if(e.kind==='regtab')was='<b>Oberregister-Reiter</b> „'+esc(e.label)+'" — der Knopf, der auf die Seite „'+esc(e.label)+'" schaltet. Größe ändern = Knopf-/Glow-Größe (im ✎-Modus die Ecke ⤡ ziehen).';
 else if(e.kind==='regicon')was='<b>Reiter-Icon</b> — das Symbol des Oberregister-Reiters „'+esc(String(e.label||'').replace(/ · Icon$/,''))+'". Größe hier ist GETRENNT vom Knopf/Glow editierbar (Ecke ⤡).';
 else if(e.kind==='filterchip')was='<b>Bereich-Filter</b> „'+esc(e.label)+'" — Filter-Knopf; grenzt den angezeigten Bereich auf „'+esc(e.label)+'" ein.';
 else if(e.kind==='oberregister')was='<b>Oberregister</b> (Seiten-Navigation) — die Reiter '+(pp.items?'„'+esc(pp.items)+'" ':'')+'schalten ganze Seiten um. Jeder Reiter ist EIN eigenes Element (einzeln anklickbar).';
 else if(e.kind==='tabs')was='<b>Bereichs-Filterleiste</b> — die Chips '+(pp.items?'„'+esc(pp.items)+'" ':'')+'filtern den angezeigten Bereich (jeder Chip ist EIN eigenes Filter-Element).';
 else if(e.kind==='appkopf')was='<b>App-Kopfzeile</b> — Marken-Lockup links, Anmelde-/Sicherheits-Status rechts'+(pp.tagline?', Akzent-Streifen „'+esc(pp.tagline)+'"':'')+'.';
 else was='<b>'+esc(LBL[e.kind]||e.kind)+'</b>'+((HELP[e.kind]&&HELP[e.kind][0])?' — '+esc(HELP[e.kind][0]):'');
 var fn=pp.aktion||((e.desc||'').slice(0,100))||((HELP[e.kind]&&HELP[e.kind][1])||'—');
 var ownPage=(e.kind==='oberregister')?'ja — jeder Reiter ist eine eigene Seite':'nein';
 var opens=pp.zielId?zielLabel(pp.zielId):((pp.aktion&&/öffne|panel/i.test(pp.aktion))?pp.aktion:'—');
 var glow=mirGlow(e);
 return '<div style="background:rgba(var(--cyr),.06);border:1px solid rgba(var(--cyr),.25);border-radius:8px;padding:7px 9px;margin-bottom:7px;font-size:11px;line-height:1.6">'
  +'<span style="color:var(--cy);font-weight:500">Was ist das:</span> '+was
  +'<br><span style="color:var(--cy);font-weight:500">Funktion:</span> '+esc(fn)
  +'<br><span style="color:var(--cy);font-weight:500">Eigene Seite:</span> '+esc(ownPage)
  +'<br><span style="color:var(--cy);font-weight:500">Öffnet Panel:</span> '+esc(opens)
  +(glow?'<br><span style="color:var(--mg);font-weight:500">Leucht-Effekt (Glow):</span> '+esc(glow)+' <span style="color:var(--mut)">— aus dem UI-Kit, fest (nicht im Tool editierbar)</span>':'')+'</div>';}
function mirGlow(e){if(e.kind==='regtab')return 'ja — der aktive Reiter glüht (Akzentfarbe)';if(e.kind==='filterchip')return 'ja — der aktive Filter glüht';
 try{var n=mirElById(e.id);if(n){var cs=getComputedStyle(n);if((cs.boxShadow&&cs.boxShadow!=='none')||(cs.filter&&/drop-shadow/.test(cs.filter)))return 'ja';}}catch(x){}
 if(e.kind==='button'||e.kind==='link')return 'ja — Hover/Aktiv-Glow';return '';}
function mirrorEditExtra(e,p){if(CONTAINER[e.kind])return '';
 var x='<div style="border-top:1px dashed var(--line);margin-top:10px;padding-top:8px">';
 x+='<label>Größe (px — 1:1 zur echten Seite)</label><div class="rw"><div><input type="number" data-f="ew" value="'+(e.ew||0)+'" title="Breite"></div><div><input type="number" data-f="eh" value="'+(e.eh||0)+'" title="Höhe"></div></div>';
 var po=(e.kind==='regtab'||e.kind==='regicon'||e.kind==='filterchip'||e.kind==='appkopf')?'':panelOpts(p&&p.id);
 if(po)x+='<label>In anderes Panel verschieben (gleiche Seite)</label><select data-mv><option value="">— hier lassen —</option>'+po+'</select>';
 x+='<div style="margin-top:10px;text-align:right"><button class="pbbtn mg" data-delcur>Element löschen</button></div></div>';return x;}
// Element zwischen Panels verschieben (whole-page-flow): Datenmodell umhängen + echten Klon-Knoten in die Ziel-.card umhängen + MIR neu serialisieren.
function moveElToPanel(id,tpid){var f=findEl(id);if(!f||!tpid)return;var tp=panelById(tpid);if(!tp||tp.id===f.p.id)return;var e=f.e;
 S.panels.forEach(function(p){p.els=(p.els||[]).filter(function(x){return x.id!==id;});(p.els||[]).forEach(function(c){if(CONTAINER[c.kind])c.els=(c.els||[]).filter(function(x){return x.id!==id;});});});
 tp.els=tp.els||[];tp.els.push(e);
 if(S.mirror&&mirShadow){var cn=mirElById(id),tc=mirElById(tpid);if(cn&&tc){var host=tc.querySelector('.card-koerper')||tc;cn.style.transform='';e.tx=0;e.ty=0;host.appendChild(cn);reserMir();}}
 S.active=tpid;S.sel=id;}
function openModal(id){var f=findEl(id);if(!f)return;var e=f.e;var m=$('pbModal');m.dataset.el=id;m.dataset.panel='';
 $('pbmTitle').textContent=LBL[e.kind];$('pbmPrev').innerHTML=pv(e);
 var hl=HELP[e.kind]||['','','',''];$('pbmHelp').innerHTML=(S.mirror?mirrorInfo(e,f.p):'')+'<b style="color:var(--cy);font-weight:500">Was:</b> '+esc(hl[0]||'')+(hl[1]?'<br><b style="color:var(--cy);font-weight:500">Wann:</b> '+esc(hl[1]):'')+'<br><b style="color:var(--cy);font-weight:500">Parameter:</b> '+esc(hl[2]||'')+(hl[3]?'<br><b style="color:var(--mg);font-weight:500">Verknüpfung/Daten:</b> '+esc(hl[3]):'');
 $('pbmBody').innerHTML=editFields(e)+(S.mirror?mirrorEditExtra(e,f.p):'');$('pbBackdrop').style.display='block';m.style.display='block';m.scrollTop=0;}
function closeModal(){$('pbModal').style.display='none';$('pbModal').dataset.panel='';$('pbBackdrop').style.display='none';render();}
function modalApply(ev){var mv=ev.target.closest('[data-mv]');if(mv){if(mv.value){moveElToPanel($('pbModal').dataset.el,mv.value);closeModal();}return;}
 var pe=ev.target.closest('[data-pf]');if(pe){var p=panelById($('pbModal').dataset.panel);if(p){if(pe.dataset.pf==='collapsed')p.collapsed=(pe.value==='eingeklappt');else p[pe.dataset.pf]=pe.value;if(pe.dataset.pf==='note')renderSugg(p);if(pe.dataset.pf==='title')$('pbmPrev').innerHTML='<b style="font-weight:500">'+esc(p.title||'Panel')+'</b>';save();}return;}
 var el=ev.target.closest('[data-f]');if(!el)return;var id=$('pbModal').dataset.el;setField(id,el.dataset.f,el.value);var f=findEl(id);if(f)$('pbmPrev').innerHTML=pv(f.e);save();
 // Pixel-Mirror: Größe live am echten Klon anwenden (in-flow), dann persistent sichern
 if(S.mirror&&mirShadow&&/^(ew|eh)$/.test(el.dataset.f)){var n=mirShadow.querySelector('[data-pb-id="'+id+'"]');if(n){if(el.dataset.f==='ew')n.style.width=(parseInt(el.value)||0)+'px';else n.style.height=(parseInt(el.value)||0)+'px';}reserMir();}}
$('pbModal').addEventListener('input',modalApply);
$('pbModal').addEventListener('change',modalApply);
$('pbModal').addEventListener('click',function(ev){if(ev.target.closest('[data-mclose]')){closeModal();return;}
 if(ev.target.closest('[data-delcur]')){var did=$('pbModal').dataset.el;if(did)delEl(did);closeModal();return;}
 var dpc=ev.target.closest('[data-delpanelcur]');if(dpc){var ppid=dpc.dataset.delpanelcur;S.panels=S.panels.filter(function(p){return p.id!==ppid;});if(S.mirror&&mirShadow){var pn=mirShadow.querySelector('[data-pb-id="'+ppid+'"]');if(pn&&pn.parentNode)pn.parentNode.removeChild(pn);reserMir();}closeModal();return;}
 if(ev.target.closest('[data-addopen]')){var ap=ev.target.closest('[data-addopen]').dataset.addopen;closeModal();openAdd(ap);return;}
 if(ev.target.closest('[data-suggmock]')){var pm=panelById($('pbModal').dataset.panel);if(pm){var nt=(pm.note||'').toLowerCase();var st={};SUGG.forEach(function(s){if(s[0].test(nt))s[1].forEach(function(k){st[k]=1;});});var ks2=Object.keys(st);if(!ks2.length)ks2=['header','table','badge'];ks2.forEach(function(k){addTo(pm,k);});save();closeModal();}return;}
 var sg=ev.target.closest('[data-suggadd]');if(sg){var p=panelById($('pbModal').dataset.panel);if(p){addTo(p,sg.dataset.suggadd);save();$('pbmPrev').innerHTML='<b style="font-weight:500">'+esc(p.title||'Panel')+'</b> <span style="color:var(--mut);font-size:11px">+ '+esc(LBL[sg.dataset.suggadd])+'</span>';}}});
$('pbBackdrop').addEventListener('click',function(){if($('pbAdd').style.display==='block')closeAdd();else closeModal();});
document.addEventListener('keydown',function(ev){if(ev.key!=='Escape')return;if($('pbAdd').style.display==='block')closeAdd();else if($('pbModal').style.display==='block')closeModal();});

function openPanelModal(pid){var p=panelById(pid);if(!p)return;var m=$('pbModal');m.dataset.el='';m.dataset.panel=pid;
 $('pbmTitle').textContent='Panel — '+(p.zone==='kopf'?'Seitenkopf':'Karte');
 $('pbmPrev').innerHTML='<b style="font-weight:500">'+esc(p.title||'Panel')+'</b>';
 if(S.mirror){
  $('pbmHelp').innerHTML='<b style="color:var(--cy);font-weight:500">Was ist das:</b> Panel (Karte) der echten App-Oberfläche'+(p.page?' · Seite „'+esc(p.page)+'"':'')+'.<br><b style="color:var(--cy);font-weight:500">Inhalt:</b> '+(((p.els||[]).length)||0)+' erfasste Elemente — Doppelklick auf ein Element zeigt dessen Hintergrund.';
  $('pbmBody').innerHTML='<label>Überschrift (für den Bauplan)</label><input data-pf="title" value="'+esc(p.title||'')+'">'
   +'<label>Notiz / Funktion dieses Panels</label><textarea data-pf="note" placeholder="frei beschreiben …">'+esc(p.note||'')+'</textarea>'
   +(p.zone!=='kopf'?'<div style="margin-top:10px;text-align:right"><button class="pbbtn mg" data-delpanelcur="'+pid+'">Panel löschen</button></div>':'');
  $('pbBackdrop').style.display='block';m.style.display='block';m.scrollTop=0;return;}
 $('pbmHelp').innerHTML='<b style="color:var(--fg);font-weight:500">Panel-Kopf:</b> Überschrift + ein Satz, was dieses Panel können soll. Aus der Beschreibung schlägt das Tool passende Elemente vor.';
 var _pgs=pageList();
 var _pageSel=(p.zone!=='kopf'&&_pgs.length>1)?'<div><label>Seite (§3.2 — Panel umhängen)</label><select data-pf="page">'+_pgs.map(function(pg){return '<option'+(((p.page||'')===pg)?' selected':'')+'>'+esc(pg)+'</option>';}).join('')+'</select></div>':'';
 var _collSel=(p.zone!=='kopf')?'<div><label>Standard-Zustand (§3.6)</label><select data-pf="collapsed">'+opt(['offen','eingeklappt'],(p.collapsed?'eingeklappt':'offen'))+'</select></div>':'';
 var _row=(_pageSel||_collSel)?'<div class="rw">'+_pageSel+_collSel+'</div>':'';
 $('pbmBody').innerHTML='<label>Überschrift</label><input data-pf="title" value="'+esc(p.title||'')+'">'
  +_row
  +'<div style="margin:8px 0 2px;text-align:right"><button class="pbbtn mg" data-addopen="'+pid+'">＋ Element einfügen</button></div>'
  +'<label>Zweck / Beschreibung — was soll dieses Panel können?</label><textarea data-pf="note" placeholder="z. B. Zeigt den monatlichen Umsatz mit Trend; Liste offener Rechnungen; Status je Kunde …">'+esc(p.note||'')+'</textarea>'
  +'<div id="pbSugg"></div>';
 renderSugg(p);$('pbBackdrop').style.display='block';m.style.display='block';m.scrollTop=0;}
var SUGG=[[/umsatz|trend|verlauf|kennzahl|euro|mrr|monat|wachstum/i,['kpi','metric','chart']],[/liste|tabelle|posten|rechnung|aufgabe|eintrag|eintr/i,['table']],[/status|ampel|zustand|offen|erledigt|fortschritt/i,['badge','progress']],[/frist|termin|zeit|gantt|deadline|kalender/i,['timeline']],[/score|readiness|fitness|index|gauge|tacho/i,['gauge']],[/korrelation|streu|vergleich|zusammenhang/i,['scatter']],[/ring|aktivit|bewegung|training/i,['ring']],[/cockpit|übersicht|domän|quer|netzwerk/i,['cockpit']],[/datei|upload|beleg|dokument|pdf|hochlad/i,['upload']],[/such|filter|finden/i,['search']],[/verkn|link|sprung|andere app|öffne/i,['link']],[/foto|bild|icon|symbol/i,['icon']],[/eingabe|formular|feld|tippen/i,['input','textarea']]];
function renderSugg(p){var box=$('pbSugg');if(!box)return;var note=(p.note||'').toLowerCase();var set={};SUGG.forEach(function(s){if(s[0].test(note))s[1].forEach(function(k){set[k]=1;});});var ks=Object.keys(set);if(!ks.length){box.innerHTML='<div style="font-size:11px;color:var(--mut);margin-top:11px">💡 Beschreibe die Funktion oben — dann schlägt das Tool hier passende Elemente vor (Klick fügt ein).</div>';return;}box.innerHTML='<div style="font-size:11px;color:var(--fg);margin:13px 0 6px">Passt dazu — Klick fügt einzeln ins Panel ein:</div><div style="display:flex;flex-wrap:wrap;gap:6px">'+ks.map(function(k){return '<button class="addopt mini" data-suggadd="'+k+'"><span class="aoprev">'+pv(mkEl(k))+'</span><span class="aon">'+esc(LBL[k])+'</span></button>';}).join('')+'</div><button class="pbbtn mg" data-suggmock style="margin-top:11px">✨ Komplettes Vorschlags-Layout ins Panel erzeugen</button>';}

var addTarget=null;
function openAdd(id){var f=findEl(id);var con,panel;if(f){con=f.e;panel=f.p;}else{con=panelById(id);panel=con;}if(!con)return;var inKopf=panel&&panel.zone==='kopf';addTarget=con;var name=con.title||con.label||LBL[con.kind]||'Panel';
 $('pbAddTitle').textContent='Was soll in „'+name+'"?';
 var note=((panel&&panel.note)||'').toLowerCase(),sset={};SUGG.forEach(function(s){if(s[0].test(note))s[1].forEach(function(k){sset[k]=1;});});
 $('pbAddBody').innerHTML=CATS.map(function(c){var items=c[1].filter(function(k){var kk=k[0];if(kk==='panel')return false;return inKopf?KOPFONLY[kk]:!KOPFONLY[kk];});if(!items.length)return '';return '<div class="aocat">'+esc(c[0])+'</div>'+items.map(function(k){var kk=k[0];var hl=HELP[kk]||['',''];var g=sset[kk]?' glow':'';return '<button class="addopt'+g+'" data-addinto="'+kk+'"><span class="aoprev">'+pv(mkEl(kk))+'</span><span class="aotx"><span class="aon">'+esc(LBL[kk])+(sset[kk]?' <span class="sugbadge">★ passt zum Zweck</span>':'')+'</span><span class="aod">'+esc(hl[0])+'</span></span></button>';}).join('');}).join('');
 $('pbBackdrop').style.display='block';$('pbAdd').style.display='block';$('pbAdd').scrollTop=0;}
function closeAdd(){$('pbAdd').style.display='none';$('pbBackdrop').style.display='none';addTarget=null;render();}
$('pbAdd').addEventListener('click',function(ev){if(ev.target.closest('[data-mclose]')){closeAdd();return;}var b=ev.target.closest('[data-addinto]');if(!b||!addTarget)return;
 if(b.dataset.addinto==='header'){var t=addTarget;closeAdd();if(panelById(t.id)===t)openPanelModal(t.id);else openModal(t.id);return;}
 var tid=addTarget.id;addTo(addTarget,b.dataset.addinto);render();var rf=findEl(tid);addTarget=rf?rf.e:(panelById(tid)||addTarget);});
$('pbPal').addEventListener('mouseover',function(ev){var b=ev.target.closest('[data-add]');if(!b)return;var k=b.dataset.add;var hl=HELP[k]||['',''];var tip=$('pbTip');
 tip.innerHTML='<div class="tname">'+esc(LBL[k])+'</div><div class="tpanelmock"><div class="tpm-head">▾ Beispiel-Panel — so integriert sich „'+esc(LBL[k])+'"</div><div class="tpm-body">'+pv(mkEl(k))+'</div></div><div class="th-row"><b>Was:</b> '+esc(hl[0]||'')+'</div>'+(hl[1]?'<div class="th-row"><b>Wann / wofür:</b> '+esc(hl[1])+'</div>':'')+'<div class="th-row"><b>Parameter:</b> '+esc(hl[2]||hl[1]||'')+'</div>'+(hl[3]?'<div class="th-row tlink"><b>Verknüpfung / Daten:</b> '+esc(hl[3])+'</div>':'');
 tip.style.display='block';var r=b.getBoundingClientRect(),rr=R.getBoundingClientRect();var x=r.left-rr.left,y=r.bottom-rr.top+6;var mx=R.clientWidth-tip.offsetWidth-8;if(x>mx)x=mx;if(x<4)x=4;tip.style.left=x+'px';tip.style.top=y+'px';});
$('pbPal').addEventListener('mouseout',function(ev){var to=ev.relatedTarget;if(to&&to.closest&&to.closest('[data-add]'))return;$('pbTip').style.display='none';});
function delEl(id){S.panels.forEach(function(p){p.els=(p.els||[]).filter(function(e){return e.id!==id});p.els.forEach(function(e){if(CONTAINER[e.kind])e.els=(e.els||[]).filter(function(x){return x.id!==id})})});if(S.open===id)S.open=null;
 if(S.mirror&&mirShadow){var n=mirShadow.querySelector('[data-pb-id="'+id+'"]');if(n&&n.parentNode)n.parentNode.removeChild(n);reserMir();}}

$('pbCanvas').addEventListener('input',function(ev){var el=ev.target.closest('[data-f]');if(!el)return;var box=ev.target.closest('[data-el]');if(!box)return;var v=el.value;setField(box.dataset.el,el.dataset.f,v);save();
 if(el.dataset.f==='label'){/*live label in head only on close*/}});
$('pbCanvas').addEventListener('change',function(ev){var el=ev.target.closest('[data-f]');if(!el)return;var box=ev.target.closest('[data-el]');if(box&&el.dataset.f.slice(0,2)==='p.'){setField(box.dataset.el,el.dataset.f,el.value);render()}});
$('pbCanvas').addEventListener('blur',function(ev){var t=ev.target.closest('[data-title]');if(t){var p=panelById(t.dataset.title);if(p){p.title=t.textContent.trim()||'Panel';save()}}},true);

// Pixel-Mirror: Drag/Resize spiegelt live in den echten Klon (Anzeige-Ebene)
function mirSyncPanel(p){if(!mirShadow)return;var mw=mirShadow.querySelector('[data-mw="'+p.id+'"]');if(mw){mw.style.left=(p.rx||0)+'px';mw.style.top=(p.ry||0)+'px';mw.style.width=(p.rw||100)+'px';}}
function mirSyncEl(e){if(!mirShadow)return;e._moved=true;var cn=mirShadow.querySelector('[data-pb-id="'+e.id+'"]');if(cn){var mw=cn.closest('[data-mw]');if(mw&&mw.firstElementChild)mw.firstElementChild.style.position='relative';cn.style.position='absolute';cn.style.left=(e.ex||0)+'px';cn.style.top=(e.ey||0)+'px';cn.style.width=(e.ew||40)+'px';cn.style.height=(e.eh||18)+'px';cn.style.margin='0';cn.style.zIndex='1';}}
var drag=null;
$('pbCanvas').addEventListener('pointerdown',function(ev){
 var rh=ev.target.closest('[data-resize]');var hd=ev.target.closest('[data-head]');
 if(!rh&&!hd)return;
 if(hd&&(ev.target.closest('[data-title]')||ev.target.closest('[data-collapse]')||ev.target.closest('[data-delpanel]')||ev.target.closest('[data-panel-edit]')||ev.target.closest('.gel')))return;
 var id=(rh||hd).dataset.resize||(rh||hd).dataset.head;var p=panelById(id);if(!p)return;
 if(S.mirror&&p.zone==='kopf')return;
 S.active=id;
 if(isScaled()&&p.rw!=null&&p.zone!=='kopf'){drag={p:p,mode:rh?'resize':'move',scaled:true,sc:SC(),sx:ev.clientX,sy:ev.clientY,orx:p.rx,ory:p.ry,orw:p.rw,orh:p.rh,node:ev.target.closest('.pbpanel')};}
 else{drag={p:p,mode:rh?'resize':'move',sx:ev.clientX,sy:ev.clientY,ox:p.x,oy:p.y,ow:p.w,oh:p.h,node:ev.target.closest('.pbpanel')};}
 try{ev.target.setPointerCapture(ev.pointerId)}catch(e){}ev.preventDefault()});
$('pbCanvas').addEventListener('pointermove',function(ev){if(!drag)return;var p=drag.p;
 if(drag.scaled){var sc=drag.sc||1;var ddx=(ev.clientX-drag.sx)/sc,ddy=(ev.clientY-drag.sy)/sc;
  if(drag.mode==='move'){p.rx=Math.max(0,Math.round(drag.orx+ddx));p.ry=Math.max(0,Math.round(drag.ory+ddy));}
  else{p.rw=Math.max(40,Math.round(drag.orw+ddx));p.rh=Math.max(24,Math.round(drag.orh+ddy));}
  var sn=drag.node;if(sn){sn.style.left=(p.rx*sc).toFixed(1)+'px';sn.style.top=(p.ry*sc).toFixed(1)+'px';sn.style.width=(p.rw*sc).toFixed(1)+'px';sn.style.height=(p.rh*sc).toFixed(1)+'px';}if(S.mirror)mirSyncPanel(p);return;}
 var cw=colW();var dx=Math.round((ev.clientX-drag.sx)/cw);var dy=Math.round((ev.clientY-drag.sy)/ROWH);
 if(drag.mode==='move'){p.x=clamp(drag.ox+dx,0,COLS-p.w);p.y=Math.max(0,drag.oy+dy)}
 else{p.w=clamp(drag.ow+dx,2,COLS-p.x);p.h=Math.max(2,drag.oh+dy)}
 var n=drag.node;if(n){n.style.left=(p.x*100/COLS)+'%';n.style.top=(p.y*ROWH)+'px';n.style.width=(p.w*100/COLS)+'%';n.style.height=(p.h*ROWH)+'px';var wd=n.querySelector('.wd');if(wd)wd.textContent=p.w+'/'+COLS}
 $('pbCanvas').style.height=canvasH()});
function endDrag(){if(drag){drag=null;render()}}
$('pbCanvas').addEventListener('pointerup',endDrag);$('pbCanvas').addEventListener('pointercancel',endDrag);

var justMoved=false,gd=null;
$('pbCanvas').addEventListener('pointerdown',function(ev){
 if(ev.target.closest('[data-delel]'))return;
 var rh=ev.target.closest('[data-eresize]'),mh=ev.target.closest('[data-emove]');if(!rh&&!mh)return;
 var node=ev.target.closest('.gel');if(!node)return;
 var f=findEl(node.dataset.el);if(!f)return;
 if(isScaled()&&node.closest('.pbpanel.scaled')){gd={mode:rh?'resize':'move',scaled:true,sc:SC(),e:f.e,node:node,sx:ev.clientX,sy:ev.clientY,oex:f.e.ex||0,oey:f.e.ey||0,oew:f.e.ew||40,oeh:f.e.eh||18,moved:false};ev.stopPropagation();return;}
 var grid=node.closest('.pgrid');if(!grid)return;
 gd={mode:rh?'resize':'move',e:f.e,node:node,grid:grid,colpx:(grid.clientWidth/GCOLS)||40,sx:ev.clientX,sy:ev.clientY,ogx:f.e.gx,ogy:f.e.gy,ogw:f.e.gw,ogh:f.e.gh,moved:false};
 ev.stopPropagation();
},true);
$('pbCanvas').addEventListener('pointermove',function(ev){if(!gd)return;
 if(!gd.moved){if(Math.abs(ev.clientX-gd.sx)<4&&Math.abs(ev.clientY-gd.sy)<4)return;gd.moved=true;if(gd.grid)gd.grid.classList.add('gridon');try{gd.node.setPointerCapture(ev.pointerId)}catch(e){}}
 var e=gd.e;
 if(gd.scaled){var sc=gd.sc||1;var ddx=(ev.clientX-gd.sx)/sc,ddy=(ev.clientY-gd.sy)/sc;
  if(gd.mode==='move'){e.ex=Math.max(0,Math.round(gd.oex+ddx));e.ey=Math.max(0,Math.round(gd.oey+ddy));}
  else{e.ew=Math.max(12,Math.round(gd.oew+ddx));e.eh=Math.max(10,Math.round(gd.oeh+ddy));}
  gd.node.style.left=(e.ex*sc).toFixed(1)+'px';gd.node.style.top=(e.ey*sc).toFixed(1)+'px';gd.node.style.width=(e.ew*sc).toFixed(1)+'px';gd.node.style.height=(e.eh*sc).toFixed(1)+'px';if(S.mirror)mirSyncEl(e);return;}
 var dxc=Math.round((ev.clientX-gd.sx)/gd.colpx),dyr=Math.round((ev.clientY-gd.sy)/GROWH);
 if(gd.mode==='move'){e.gx=Math.max(0,Math.min(GCOLS-(e.gw||1),gd.ogx+dxc));e.gy=Math.max(0,gd.ogy+dyr);}
 else{e.gw=Math.max(1,Math.min(GCOLS-(e.gx||0),gd.ogw+dxc));e.gh=Math.max(1,gd.ogh+dyr);}
 gd.node.style.left=(e.gx/GCOLS*100).toFixed(3)+'%';gd.node.style.top=(e.gy*GROWH)+'px';gd.node.style.width=(e.gw/GCOLS*100).toFixed(3)+'%';gd.node.style.height=(e.gh*GROWH)+'px';});
function endGD(){if(!gd)return;var mv=gd.moved;if(gd.grid)gd.grid.classList.remove('gridon');gd=null;if(mv){justMoved=true;setTimeout(function(){justMoved=false;},70);save();render();}}
$('pbCanvas').addEventListener('pointerup',endGD);$('pbCanvas').addEventListener('pointercancel',endGD);

var edrag=null;
$('pbCanvas').addEventListener('dragstart',function(ev){var g=ev.target.closest('[data-grip]');if(!g){ev.preventDefault();return}edrag=g.dataset.grip;ev.dataTransfer.effectAllowed='move';try{ev.dataTransfer.setData('text','x')}catch(e){}});
$('pbCanvas').addEventListener('dragover',function(ev){if(edrag)ev.preventDefault()});
$('pbCanvas').addEventListener('drop',function(ev){if(!edrag)return;ev.preventDefault();var tgt=ev.target.closest('[data-el]');if(!tgt||tgt.dataset.el===edrag){edrag=null;return}reorder(edrag,tgt.dataset.el);edrag=null;render()});
function reorder(src,dst){var arr,si,di;S.panels.forEach(function(p){scan(p.els);(p.els||[]).forEach(function(e){if(CONTAINER[e.kind])scan(e.els)})});
 function scan(list){if(!list)return;var a=list.indexOf(list.filter(function(e){return e.id===src})[0]);var b=list.indexOf(list.filter(function(e){return e.id===dst})[0]);if(a>-1&&b>-1){arr=list;si=a;di=b}}
 if(arr){var it=arr.splice(si,1)[0];arr.splice(di,0,it)}}

window.addEventListener('resize',function(){if(isScaled())render();else $('pbCanvas').style.height=canvasH()});

var APPMAP={'8210':'Money','8211':'Plans','8212':'Memory','8213':'Management','8214':'Creating','8216':'News','8217':'Healthy','8218':'Communication','8219':'Leading','8222':'Admin','8410':'Plans','8412':'Memory','8413':'Management','8416':'News','8417':'Healthy','8418':'Communication','8419':'Leading','8420':'Money','8422':'Admin','8424':'Creating',
 '8137':'Trading','8200':'Core','8139':'Trading','8141':'Trading','8201':'Core','8400':'Core'};
function detectApp(){return APPMAP[location.port]||''}
function info(m){var e=$('pbIOinfo');if(e)e.textContent=m;}
function openIO(){var io=$('pbIO');io.style.display=(io.style.display==='none'?'block':'none');if(io.style.display==='block'){var ap=detectApp();info(ap?('Erkannte App: '+ap+'. „App-UI laden" liest die aktuelle Oberfläche direkt ein (gleiche Herkunft).'):'Standalone geöffnet — „App-UI laden" funktioniert nur, wenn das Tool von der App-Adresse läuft (…:PORT/ui-kit/ui-builder-tool.html). Sonst: Extraktor-Snippet auf der App ausführen und das JSON hier einfügen.');}}
function rawExtract(doc,opts){opts=opts||{};
 var win=doc.defaultView||window,GROWH=26;
 function txt(el){return el?(el.textContent||'').trim().replace(/\s+/g,' '):''}
 function lab(el){return (txt(el)||(el.getAttribute&&(el.getAttribute('placeholder')||el.getAttribute('aria-label')||el.getAttribute('title')))||'')}
 function hidden(el){if(el.hasAttribute&&el.hasAttribute('hidden'))return true;try{var s=win.getComputedStyle(el);if(s&&(s.display==='none'||s.visibility==='hidden'))return true;}catch(e){}return false;}
 function rct(el){try{return el.getBoundingClientRect();}catch(e){return{left:0,top:0,width:0,height:0};}}
 function clampi(v,a,b){return Math.max(a,Math.min(b,v));}
 // ===== v19 Pixel-Mirror — echte Knoten taggen + sauber serialisieren (für die Anzeige-Ebene) =====
 var MIRON=!!opts.mirror;
 function mid(){return 'm'+Math.random().toString(36).slice(2,9);}
 function cleanClone(node){var c=node.cloneNode(true);
  [].slice.call(c.querySelectorAll('script,noscript,link,style')).forEach(function(n){if(n.parentNode)n.parentNode.removeChild(n);});
  var all=c.querySelectorAll('*');for(var i=0;i<all.length;i++){var at=all[i].attributes;for(var j=at.length-1;j>=0;j--){var nm=at[j].name;if(nm.slice(0,2)==='on'||nm==='contenteditable')all[i].removeAttribute(nm);}}
  return c.outerHTML;}
 function tagAll(items){if(!MIRON)return;items.forEach(function(o){o._id=mid();try{o.e.setAttribute('data-pb-id',o._id);}catch(e){}});}
 function variant(el){var c=' '+(el.className||'')+' ';if(/ (prim|primary|cta) /.test(c))return'primary';if(/ (danger|del|destruct) /.test(c))return'danger';if(/ (mini|sm|small) /.test(c))return'mini';if(!txt(el)&&el.querySelector('svg,use,img'))return'icon';return'ghost';}
 var ACTMAP={oeffneKm:'öffnet Einstellungen & Konto',setBereich:'wechselt den Bereich',setModul:'wechselt die Seite/Modul',dizziFrage:'fragt die Mini-KI',rechnungAnlegen:'legt eine Rechnung an',kundeAnlegen:'legt einen Kunden an',neuerBereichForm:'legt einen Bereich an',bereichNeuStart:'legt einen Bereich an'};
 function aktion(el){var a=el.getAttribute&&el.getAttribute('data-dz-act');if(a)return ACTMAP[a]||('Aktion: '+a);var h=el.getAttribute&&el.getAttribute('href');if(h&&h!=='#'&&h.indexOf('javascript')<0)return 'öffnet '+h;return '';}
 var ATOMIC='table,.dz-table,.dz-cockpit,.cock-grid,.cockpit,.dz-chart,.chart,.dz-gauge,.dz-score-card,.dz-rings,.dz-ring-wrap,.dz-heat,.dz-heat-grid,.dz-bars,.dz-donut,.dz-scatter,.dz-timeline,canvas,svg.chart';
 function mk(el){
  if(el.matches('.dz-upload,[data-dz-upload]')||el.matches('input[type=file]'))return 'upload';
  if(el.matches('.cmdk,#cmdk,.command-palette,.dz-cmdk'))return 'cmdk';
  if(el.matches('.dz-heat,.dz-heat-grid,.dz-heatmap,.heatmap,[data-heatmap]'))return 'heatmap';
  if(el.matches('.dz-cockpit,.cock-grid,.cockpit'))return 'cockpit';
  if(el.matches('.dz-gauge,.dz-score-card,[data-gauge]'))return 'gauge';
  if(el.matches('.dz-scatter,[data-scatter]'))return 'scatter';
  if(el.matches('.dz-rings,.dz-ring-wrap,.dz-ring,.rings,[data-ring],[data-rings]'))return 'ring';
  if(el.matches('.dz-timeline,.gantt,[data-timeline]'))return 'timeline';
  if(el.matches('.dz-metric,.dz-kpi-t,.metric-card,.metrik'))return 'metric';
  if(el.matches('.dz-board,.dz-kanban,.kanban'))return 'board';
  if(el.matches('.dz-kalender,.kalender,.calendar,.dz-calendar,[data-calendar]'))return 'kalender';
  if(el.matches('.kontakt,.dz-kontakt,.smartkontakt,.contact,.dz-avatar'))return 'kontakt';
  if(el.matches('.dz-liste,.dz-list,.liste,ul.liste,ol.liste'))return 'liste';
  if(el.matches('.dz-icon,[data-icon]'))return 'icon';
  if(el.matches('.dz-oberregister,.oberregister,.dz-register,.kategorien,.cat-nav,.tabbar,.modulbar'))return 'oberregister';
  if(el.matches('header,.dz-kopf,.apphead,.app-head,.topbar,.brandbar,.dz-appbar'))return 'appkopf';
  if(el.matches('.dz-chip,.chip,.tagchip,.berchip'))return 'link';
  if(el.matches('input[type=search],.dz-search'))return 'search';
  if(el.matches('.dz-tabs,.dz-tab,[role=tablist],.viewswitch,.view-switch,.seg,.segmented'))return 'tabs';
  if(el.matches('.dz-toggle,.toggle'))return 'toggle';
  if(el.matches('.dz-stepper'))return 'stepper';
  if(el.matches('select,.dz-select'))return 'select';
  if(el.matches('textarea'))return 'textarea';
  if(el.matches('input[type=range],.dz-range'))return 'range';
  if(el.matches('input[type=checkbox]'))return 'checkbox';
  if(el.matches('input[type=radio]'))return 'radio';
  if(el.matches('table,.dz-table'))return 'table';
  if(el.matches('.dz-chart,.chart,canvas,svg.chart,[data-chart],.dz-donut,.dz-bars'))return 'chart';
  if(el.matches('.pill,.dz-badge,.badge,.b-status,.zchip,.subbadge'))return 'badge';
  if(el.matches('.dz-progress,progress,meter'))return 'progress';
  if(el.matches('.kpi,[class*=kpi]')||(el.matches('.card')&&el.querySelector('.big,.kt-v,.dz-metric-val')))return 'kpi';
  if(el.matches('button,.btn,.dz-btn,a.btn,[role=button]')||(el.matches('[data-dz-act]')&&!el.matches('select,.dz-select,input,textarea,.dz-field')))return 'button';
  if(el.matches('input'))return 'input';
  return null;}
 function eprops(el,k){var p={},q;
  if(k==='button'){p.variant=variant(el);var a=aktion(el);if(a)p.aktion=a;}
  else if(k==='select'){p.options=[].slice.call(el.querySelectorAll('option')).map(function(o){return txt(o);}).filter(Boolean).slice(0,10).join(', ');}
  else if(k==='table'){var tr=el.querySelectorAll('tr');p.rows=Math.max(1,tr.length);var r0=tr[0];p.cols=r0?Math.max(1,r0.querySelectorAll('th,td').length):2;}
  else if(k==='tabs'||k==='oberregister'){p.items=[].slice.call(el.querySelectorAll('a,button,.tab,.mtab,.berchip,[role=tab],li')).map(function(t){return txt(t);}).filter(function(s){return s&&s.length<26;}).slice(0,8).join(', ');}
  else if(k==='badge'){var c=' '+(el.className||'')+' ';p.state=/ok|bezahlt|aktiv|gut|on /.test(c)?'ok':/warn|faellig|ruhend|offen/.test(c)?'warn':/bad|danger|storniert|err/.test(c)?'bad':'on';}
  else if(k==='range'){p.min=el.getAttribute('min')||0;p.max=el.getAttribute('max')||100;p.step=el.getAttribute('step')||1;}
  else if(k==='metric'){q=el.querySelector('.dz-metric-val,.kt-v,.cm-n,.value');if(q)p.value=txt(q).slice(0,12);q=el.querySelector('.dz-arrow,.trend,.dz-metric-ref');p.trend=q?txt(q).slice(0,8):'';}
  else if(k==='cockpit'){p.spalten=[].slice.call(el.querySelectorAll('.dz-cockpit-kachel .kk-kopf,.cock-mod .cm-tt,.kk-label,.kk-kopf')).map(function(t){return txt(t);}).filter(Boolean).slice(0,5).join(', ');}
  else if(k==='kpi'){q=el.querySelector('.big,.kt-v,.dz-metric-val,b,strong');if(q)p.value=txt(q).slice(0,12);}
  else if(k==='liste'){p.rows=[].slice.call(el.querySelectorAll('.zeile .z-titel,li,.dz-list-item')).map(function(t){return txt(t);}).filter(Boolean).slice(0,6).join(', ');}
  else if(k==='link'){p.target=txt(el).replace(/[↗↪→]/g,'').trim().slice(0,24);}
  else if(k==='heatmap'){p.cols=7;p.rows=4;}
  return p;}
 function elLabel(el,k){var q;
  if(k==='metric'){q=el.querySelector('.dz-metric-label,.kt-kopf,.cm-tt');if(q)return txt(q).slice(0,32);}
  if(k==='kpi'){q=el.querySelector('.lbl,.dz-metric-label,.kt-kopf');if(q)return txt(q).slice(0,32);}
  if(k==='cockpit')return 'Cockpit';
  return String(lab(el)||k).slice(0,40);}
 var ELSEL='.dz-chip,.chip,.tagchip,.berchip,.dz-tabs,[role=tablist],.viewswitch,.view-switch,.dz-toggle,.toggle,.dz-stepper,button,.btn,.dz-btn,a.btn,[role=button],[data-dz-act],input,textarea,select,.dz-select,.dz-search,.dz-range,table,.dz-table,.pill,.dz-badge,.badge,.b-status,.zchip,.subbadge,.dz-progress,progress,meter,.kpi,canvas,svg.chart,[data-chart],.dz-chart,.chart,.dz-donut,.dz-bars,.dz-upload,[data-dz-upload],input[type=file],.cmdk,.command-palette,.dz-gauge,.dz-score-card,.dz-scatter,.dz-rings,.dz-ring-wrap,.dz-timeline,.dz-cockpit,.cock-grid,.cockpit,.dz-metric,.dz-kpi-t,.dz-heat,.dz-heat-grid,.dz-heatmap,.heatmap,.dz-board,.kanban,.dz-kalender,.kalender,.calendar,.kontakt,.smartkontakt,.dz-liste,.dz-list,.liste,.dz-icon,[data-icon],.dz-oberregister,.oberregister,.card';
 var SKIP='.kmwin,.kmwrap,.km,.floatset,.floatdizzi,.floatacct,.dizzibubble,.modal,dialog,[role=dialog],.bgfx,.bgbrush,#bg-stage';
 function inSkip(el){return !!(el.closest&&el.closest(SKIP))}
 function panelish(el){return el.matches('.card,.pane,[data-panel],.panel,section.card')}
 var scope=doc.querySelector('main .wrap,main,.wrap,.app')||doc.body;
 var sr=rct(scope),sw=sr.width||1180,sl=sr.left;
 function nearestPanel(el){var p=el.parentElement;while(p&&p!==scope){if(panelish(p))return p;p=p.parentElement;}return null;}
 function geom(list,br){var bw=br.width||sw,bl=br.left;list.sort(function(a,b){return (a.r.top-b.r.top)||(a.r.left-b.r.left);});var gy=0,rowBot=null,rowH=0,started=false;list.forEach(function(o){var r=o.r;var hh=clampi(Math.round(r.height/GROWH),1,8);if(!started||r.top>rowBot-6){if(started)gy+=rowH;rowBot=r.top+r.height;rowH=hh;started=true;}else{rowBot=Math.max(rowBot,r.top+r.height);rowH=Math.max(rowH,hh);}o.gx=clampi(Math.round((r.left-bl)/bw*12),0,11);o.gw=clampi(Math.round(r.width/bw*12),1,12);if(o.gx+o.gw>12)o.gw=12-o.gx;o.gy=gy;o.gh=hh;});}
 function collect(box,skipSet){var seen={},list=[];[].slice.call(box.querySelectorAll(ELSEL)).forEach(function(e){
   if(skipSet&&skipSet.has(e))return;if(hidden(e)||inSkip(e))return;
   if(!e.matches(ATOMIC)&&e.closest(ATOMIC))return;
   if(e.closest('.dz-kpibar,.dz-metric-list,.minikpis')&&!e.matches('.dz-kpi-t,.dz-metric'))return;
   var k=mk(e);if(!k)return;var r=rct(e);if(r.width<10||r.height<7)return;if(k==='chart'&&r.width<40)return;
   var lbl=elLabel(e,k);var key=k+'|'+lbl+'|'+Math.round(r.top/9);if(seen[key])return;seen[key]=1;
   list.push({e:e,r:r,kind:k,label:lbl,props:eprops(e,k)});});return list;}
 var cand=[].slice.call(scope.querySelectorAll('.card,.pane,[data-panel],.panel,section.card'));
 if(!cand.length)cand=[].slice.call(doc.querySelectorAll('.card,.pane,section'));
 var tops=cand.filter(function(c){return !hidden(c)&&!inSkip(c)&&!nearestPanel(c)});
 var out=[];
 function wasClosed(d){return d.hasAttribute('data-pb-wasclosed')||(d.tagName.toLowerCase()==='details'&&!(d.hasAttribute('open')));}
 tops.forEach(function(card){
  // Panel-Kopf/Body: Muster „Panel umschließt ein <details>" (z. B. Trading Bot section.panel>details>summary)
  // berücksichtigen — Titel steht dann in der summary (ohne Knöpfe), der Body IST das details.
  var wrap=null;for(var cc=card.firstElementChild;cc;cc=cc.nextElementSibling){if(cc.tagName&&cc.tagName.toLowerCase()==='details'){wrap=cc;break;}}
  var title='';
  if(wrap){var sm=wrap.querySelector('summary');if(sm){var smc=sm.cloneNode(true);[].slice.call(smc.querySelectorAll('button,.btn,svg,input,.rangebtn')).forEach(function(n){if(n.parentNode)n.parentNode.removeChild(n);});title=txt(smc);}}
  if(!title){var h=card.querySelector('.card-kopf h2,.card-kopf h3,.head .name,.lockup .name,.card-head h2')||[].slice.call(card.querySelectorAll('h2,h3,legend,.psummary,.panelhead')).filter(function(x){return !x.closest('details,.ber-grp,.pane,.panel')&&nearestPanel(x)===card;})[0];title=h?txt(h):'';}
  title=((title)||'').slice(0,46)||'Panel';
  var body=wrap||card.querySelector('.card-koerper')||card,bRect=rct(body);
  var subs=[].slice.call(body.querySelectorAll('details.ber-grp,details,.pane,.panel')).filter(function(s){return s!==wrap&&nearestPanel(s)===card&&!hidden(s)&&!inSkip(s)});
  var inSub=new Set();if(wrap){var wsm=wrap.querySelector('summary');if(wsm){inSub.add(wsm);[].slice.call(wsm.querySelectorAll('*')).forEach(function(e){inSub.add(e)});}}subs.forEach(function(s){inSub.add(s);[].slice.call(s.querySelectorAll('*')).forEach(function(e){inSub.add(e)})});
  var cr=rct(card);
  var raw=collect(body,inSub);geom(raw,bRect);
  // ECHTE Rechtecke (px) mitnehmen: Element relativ zum Panel (ox/oy), für den maßstabsgetreuen Render.
  function rel(o,ox,oy){return {kind:o.kind,label:o.label,props:o.props,_id:o._id,gx:o.gx,gy:o.gy,gw:o.gw,gh:o.gh,ex:Math.round(o.r.left-ox),ey:Math.round(o.r.top-oy),ew:Math.round(o.r.width),eh:Math.round(o.r.height)};}
  tagAll(raw);
  var pel=raw.map(function(o){return rel(o,cr.left,cr.top);});
  subs.forEach(function(s){var sh=s.querySelector('summary .sg-name,summary,h2,h3,.title,.pt');var sRect=rct(s);var sc2=collect(s,null);geom(sc2,sRect);tagAll(sc2);var sid=MIRON?mid():null;if(sid){try{s.setAttribute('data-pb-id',sid);}catch(e){}}pel.push({kind:'subpanel',_id:sid,label:((sh?txt(sh):'')||'Unterpanel').slice(0,40),collapsed:wasClosed(s),ex:Math.round(sRect.left-cr.left),ey:Math.round(sRect.top-cr.top),ew:Math.round(sRect.width),eh:Math.round(sRect.height),els:sc2.map(function(o){return rel(o,sRect.left,sRect.top);})});});
  // Echte Kopfzeile der Karte als header-Element mitnehmen (rendert dann 1:1 an ihrer Stelle).
  var hdrNode=card.querySelector('.card-kopf')||(wrap&&wrap.querySelector('summary'))||((h&&h.parentElement&&h.parentElement!==card)?h.parentElement:null);
  if(hdrNode){var hr=rct(hdrNode);if(hr.height>6&&hr.width>10){var hid=MIRON?mid():null;if(hid){try{hdrNode.setAttribute('data-pb-id',hid);}catch(e){}}pel.unshift({kind:'header',_id:hid,label:title,props:{},ex:Math.round(hr.left-cr.left),ey:Math.round(hr.top-cr.top),ew:Math.round(hr.width),eh:Math.round(hr.height),gx:0,gy:0,gw:12,gh:1});}}
  if(title!=='Panel'||pel.length){var P={title:title,x:clampi(Math.round((cr.left-sl)/sw*12),0,11),w:clampi(Math.round((cr.width||sw)/sw*12),2,12),collapsed:(wrap?wasClosed(wrap):false),rx:Math.round(cr.left),ry:Math.round(cr.top-(MIRON&&opts.pageTop!=null?opts.pageTop:sr.top)),rw:Math.round(cr.width),rh:Math.round(cr.height),refW:Math.round(win.innerWidth||sw),els:pel.slice(0,28)};if(MIRON){var pid=mid();try{card.setAttribute('data-pb-id',pid);}catch(e){}P._id=pid;}out.push(P);}
 });
 if(!opts.noKopf){
  var kopfEls=[];
  var head=doc.querySelector('header,.dz-kopf,.apphead,.topbar,.brandbar,.dz-appbar');
  if(head&&!inSkip(head)&&!hidden(head)){var be=head.querySelector('.brand,.lockup .brand,.ttl,h1,strong,b');var fe=head.querySelector('.fn,.funktion,.sub');var brand=((be?txt(be):'')||txt(head)).slice(0,40)||'App-Kopf';kopfEls.push({kind:'appkopf',label:brand,props:{brand:brand,funktion:(fe?txt(fe).slice(0,30):''),tagline:txt(head).slice(0,60),stufe:'verifiziert',hochsicher:(head.querySelector('.hochsicher,[data-hochsicher]')?'ja':'nein')}});}
  var reg=doc.querySelector('.modulbar,.dz-oberregister,.oberregister,.dz-register,.kategorien,.cat-nav,.tabbar');
  if(reg&&!inSkip(reg)&&!hidden(reg)){var tabs=[].slice.call(reg.querySelectorAll('a,button,.tab,.mtab,[role=tab],li')).map(function(t){return txt(t)}).filter(function(s){return s&&s.length<26;}).slice(0,8);if(tabs.length)kopfEls.push({kind:'oberregister',label:'Oberregister',props:{items:tabs.join(', ')}});}
  var ctx=doc.querySelector('.kontextbar,.dz-kontextbar');
  if(ctx&&!inSkip(ctx)&&!hidden(ctx)){var ci=[].slice.call(ctx.querySelectorAll('.berchip,.chip,.tab,a,button')).map(function(t){return txt(t);}).filter(function(s){return s&&s.length<26&&s.charAt(0)!=='+';}).slice(0,8);if(ci.length)kopfEls.push({kind:'tabs',label:'Bereiche',props:{items:ci.join(', ')}});}
  if(kopfEls.length){var KP={title:'Seitenkopf',zone:'kopf',els:kopfEls};
   if(MIRON){var tagK=function(el,node){if(!el||!node)return;el._id=mid();try{node.setAttribute('data-pb-id',el._id);}catch(e){}};
    kopfEls.forEach(function(el){if(el.kind==='appkopf')tagK(el,head);else if(el.kind==='oberregister')tagK(el,reg);else if(el.kind==='tabs')tagK(el,ctx);});KP._id=mid();
    // Jeder Oberregister-Reiter + jeder Bereich-Filter-Chip wird ein EIGENES Element (einzeln auslesbar/größen-editierbar)
    if(reg){var rtabs=[].slice.call(reg.querySelectorAll('.mtab,.tab,[role=tab]'));if(!rtabs.length)rtabs=[].slice.call(reg.querySelectorAll('a,button'));rtabs.forEach(function(t){var s=txt(t);if(!s||s.length>26)return;var el={kind:'regtab',label:s,props:{target:s}};el._id=mid();try{t.setAttribute('data-pb-id',el._id);}catch(e){}kopfEls.push(el);
     // Icon des Reiters als eigenes Sub-Element (Icon-Größe getrennt vom Knopf/Glow editierbar)
     var ic=t.querySelector('.mt-ic,svg,img,.ic');if(ic){var ie={kind:'regicon',label:s+' · Icon',props:{}};ie._id=mid();try{ic.setAttribute('data-pb-id',ie._id);}catch(e){}kopfEls.push(ie);}});}
    if(ctx){[].slice.call(ctx.querySelectorAll('.berchip,.chip,.tab,a,button')).forEach(function(t){var s=txt(t);if(!s||s.length>26||s.charAt(0)==='+')return;var el={kind:'filterchip',label:s,props:{}};el._id=mid();try{t.setAttribute('data-pb-id',el._id);}catch(e){}kopfEls.push(el);});}}
   out.unshift(KP);}
 }
 return out;}
function walkAndExtract(win,doc,onInfo){
 function txt(el){return el?(el.textContent||'').trim().replace(/\s+/g,' '):''}
 function mscope(){return doc.querySelector('main,.wrap')||doc.body;}
 function hasPanels(){return !!mscope().querySelector('.card,.pane,[data-panel],.panel');}
 function waitStable(max){return new Promise(function(res){var last='',same=0,t0=Date.now();(function tick(){var sc=mscope();var cur=sc.innerHTML.length+'|'+sc.querySelectorAll('.card').length;if(cur===last)same++;else{same=0;last=cur;}if((same>=2&&hasPanels())||Date.now()-t0>max)res();else setTimeout(tick,140);})();});}
 return (async function(){
  var keep={};try{keep.m=win.localStorage.getItem('admin_modul');keep.b=win.localStorage.getItem('admin_bereich');}catch(e){}
  var ms=function(t){return new Promise(function(r){setTimeout(r,t);});};
  var navSel='.modulbar,.dz-oberregister,.dz-register';
  function liveTabs(){var nv=doc.querySelector(navSel);return nv?[].slice.call(nv.querySelectorAll('a,button,.mtab,.tab,[role=tab]')).filter(function(t){var s=txt(t);return s&&s.length<26;}):[];}
  // Seiten-Beschreibungen einmal sichern (das Oberregister wird bei jedem Wechsel neu gebaut ⇒ Live-Tab pro Schritt neu suchen)
  var descs=liveTabs().map(function(t){return {name:txt(t),arg:t.getAttribute('data-dz-arg')};});
  for(var pre=0;pre<14&&!hasPanels();pre++){await ms(200);}
  // Bereich-Filter auf „Alle Bereiche" (kein Filter) ⇒ ALLE Inhalte über alle Bereiche erfassen (sonst kommt z. B. Studium leer)
  (function(){var ctx=doc.querySelector('.kontextbar,.dz-kontextbar');if(!ctx)return;var chips=[].slice.call(ctx.querySelectorAll('.berchip,.chip,a,button'));var all=chips.filter(function(c){return !c.classList.contains('add')&&/alle/i.test(txt(c));})[0]||chips.filter(function(c){var a=c.getAttribute('data-dz-arg');return (a==null||a==='')&&!c.classList.contains('add');})[0];if(all)try{all.click();}catch(e){}})();
  await waitStable(2200);
  // Standardmäßig zugeklappte <details> aufklappen, sonst hat ihr Inhalt rect=0 und wird nicht
  // erfasst (z. B. Trading Bot: jedes Panel ist ein geschlossenes <details>). Original-Zustand markiert.
  function openDetails(){[].slice.call(doc.querySelectorAll('details:not([open])')).forEach(function(d){try{d.setAttribute('data-pb-wasclosed','1');d.open=true;}catch(e){}});}
  // Drill-down: jede „öffnende" Listenzeile anklicken, die geladene Detailansicht erfassen und HINTER der Zeile
  // (versteckt, data-pb-drill) inline einsetzen ⇒ im Mirror klappt sie auf Klick auf → echter Pfad, offline.
  function waitDetail(host,before,max){return new Promise(function(res){var t0=Date.now(),last='',same=0;(function tick(){if(!host){res();return;}var c=host.innerHTML;var loading=/lädt|wird geladen|class="leer"/i.test(c);if(c.trim()&&c!==before&&!loading){if(c===last)same++;else{same=0;last=c;}if(same>=1||Date.now()-t0>max){res();return;}}else if(Date.now()-t0>max){res();return;}setTimeout(tick,120);})();});}
  function isHidden(el){try{if(el.hasAttribute&&el.hasAttribute('hidden'))return true;var s=win.getComputedStyle(el);return !!(s&&(s.display==='none'||s.visibility==='hidden'));}catch(e){return false;}}
  async function expandDrilldowns(){
   var OPEN=/waehle|oeffne|open|select|zeige|view|detail/i,DESTRUCT=/loesch|weg|del|entfern|anleg|speicher|^neu|abbrech|upload|senden|veroeff|publish|bearbeit/i;
   var trigs=[].slice.call(mscope().querySelectorAll('.zeile[data-dz-act][data-dz-arg],.li[data-dz-act][data-dz-arg]')).filter(function(t){var a=t.getAttribute('data-dz-act')||'';return OPEN.test(a)&&!DESTRUCT.test(a)&&!isHidden(t);});
   var seen={},list=[];trigs.forEach(function(t){var k=(t.getAttribute('data-dz-act'))+'|'+(t.getAttribute('data-dz-arg'));if(!seen[k]){seen[k]=1;list.push(t);}});list=list.slice(0,12);
   for(var i=0;i<list.length;i++){var t=list[i];if(!doc.contains(t))continue;
    var host=doc.querySelector('#st-detail,#proj-detail,[id$="-detail"],[id*="detail"]');var before=host?host.innerHTML:'';
    try{t.click();}catch(e){continue;}await waitDetail(host,before,2800);
    host=host||doc.querySelector('[id*="detail"]');
    if(host&&host.innerHTML.trim()&&host.innerHTML!==before){var dd=doc.createElement('div');dd.className='pb-drill';dd.setAttribute('data-pb-drill','1');dd.innerHTML=host.innerHTML;var row=t.closest('.zeile')||t;if(row.parentNode)row.parentNode.insertBefore(dd,row.nextSibling);host.innerHTML=before;}
   }
  }
  openDetails();await ms(200);
  // Pixel-Mirror: gemeinsamer Seiten-Ursprung (Oberkante Kopf) + globale App-CSS/Tokens einmal sichern
  var pageTop=(function(){try{var hh=doc.querySelector('header,.dz-kopf,.apphead,.topbar,.brandbar,.dz-appbar')||mscope();return hh.getBoundingClientRect().top;}catch(e){return 0;}})();
  // Pixel-Mirror-Klone der KOMPLETTEN Seite (echtes Fluss-Layout, native Aufklapp-Mechanik bleibt erhalten)
  var mir={capW:Math.round(win.innerWidth||1280),kopfHtml:'',pageHtml:{}};
  function cloneKopf(){var sels=['header','.dz-kopf','.apphead','.topbar','.brandbar','.dz-appbar','.kontextbar','.dz-kontextbar','.modulbar','.dz-oberregister','.oberregister','.dz-register','.kategorien','.cat-nav','.tabbar'];var seen=[],html='';sels.forEach(function(sel){var n=doc.querySelector(sel);if(n&&seen.indexOf(n)<0&&!n.closest('main')){seen.push(n);html+=mirClean(n);}});return html;}
  function cloneMain(){var m=doc.querySelector('main')||doc.querySelector('.wrap,.app')||doc.body;return mirClean(m);}
  var MOPT={mirror:true,pageTop:pageTop};
  var kopf=rawExtract(doc,MOPT).filter(function(p){return p.zone==='kopf';})[0];
  mir.kopfHtml=cloneKopf();
  var panels=[];
  if(descs.length){for(var i=0;i<descs.length;i++){var d=descs[i];if(onInfo)onInfo('Seite „'+d.name+'" wird gelesen ('+(i+1)+'/'+descs.length+')…');
    var tab=liveTabs().filter(function(t){return d.arg!=null?t.getAttribute('data-dz-arg')===d.arg:txt(t)===d.name;})[0];
    if(tab){tab.click();await ms(130);await waitStable(2600);}
    openDetails();await ms(160);
    await expandDrilldowns();await ms(60);                                   // Detail-Inhalte SICHTBAR einsetzen …
    rawExtract(doc,{noKopf:true,mirror:true,pageTop:pageTop}).forEach(function(p){p.page=d.name;panels.push(p);}); // … damit sie miterfasst+getaggt werden
    [].slice.call(doc.querySelectorAll('.pb-drill')).forEach(function(dd){dd.setAttribute('hidden','');});         // im Klon standardmäßig zu
    mir.pageHtml[d.name]=cloneMain();}}
  else{await expandDrilldowns();rawExtract(doc,{noKopf:true,mirror:true,pageTop:pageTop}).forEach(function(p){panels.push(p);});[].slice.call(doc.querySelectorAll('.pb-drill')).forEach(function(dd){dd.setAttribute('hidden','');});mir.pageHtml['']=cloneMain();}
  try{if(keep.m!=null)win.localStorage.setItem('admin_modul',keep.m);if(keep.b!=null)win.localStorage.setItem('admin_bereich',keep.b);}catch(e){}
  var res=[];if(kopf)res.push(kopf);res=res.concat(panels);
  var g=captureGlobals(win,doc);g.capW=mir.capW;g.kopfHtml=mir.kopfHtml;g.pageHtml=mir.pageHtml;res._mir=g;
  return res;
 })();}
// Pixel-Mirror: einen echten Knoten sauber klonen (Skripte/Handler raus, Links inert, ursprünglich zugeklappte <details> wieder zu)
function mirClean(node){var c=node.cloneNode(true);
 [].slice.call(c.querySelectorAll('script,noscript,link,style')).forEach(function(n){if(n.parentNode)n.parentNode.removeChild(n);});
 var all=c.querySelectorAll('*');for(var i=0;i<all.length;i++){var el=all[i];var at=el.attributes;for(var j=at.length-1;j>=0;j--){var nm=at[j].name;if(nm.slice(0,2)==='on'||nm==='contenteditable')el.removeAttribute(nm);}if(el.tagName==='A'&&el.hasAttribute('href'))el.removeAttribute('href');}
 [].slice.call(c.querySelectorAll('details[data-pb-wasclosed]')).forEach(function(d){d.removeAttribute('open');});
 if(c.tagName==='DETAILS'&&c.hasAttribute('data-pb-wasclosed'))c.removeAttribute('open');
 return c.outerHTML;}
// ===== Pixel-Mirror: echte App-Stylesheets (Link + inline <style>) + ALLE Token-Werte sichern =====
function captureGlobals(win,doc){var g={links:[],styles:[],vars:{},body:{}};
 try{[].slice.call(doc.querySelectorAll('link[rel~="stylesheet"]')).forEach(function(l){if(l.href)g.links.push(l.href);});}catch(e){}
 try{[].slice.call(doc.querySelectorAll('style')).forEach(function(s){if(!s.closest('.pbroot'))g.styles.push(s.textContent||'');});}catch(e){}
 try{var de=doc.documentElement,names={};
  // Token-NAMEN aus allen erreichbaren Regeln + inline-Styles sammeln, dann je Name den berechneten Wert lesen
  g.styles.forEach(function(t){var m=t.match(/--[\w-]+(?=\s*:)/g);if(m)m.forEach(function(n){names[n]=1;});});
  try{[].slice.call(doc.styleSheets).forEach(function(ss){try{var rs=ss.cssRules||[];for(var i=0;i<rs.length;i++){var ct=rs[i].cssText||'';var mm=ct.match(/--[\w-]+(?=\s*:)/g);if(mm)mm.forEach(function(n){names[n]=1;});}}catch(e2){}});}catch(e3){}
  var cs=win.getComputedStyle(de);for(var n in names){var val=cs.getPropertyValue(n);if(val!=null&&val!=='')g.vars[n]=val.trim();}
  var bcs=win.getComputedStyle(doc.body);
  g.body.background=bcs.getPropertyValue('background-color');g.body.color=bcs.getPropertyValue('color');
  g.body.fontFamily=bcs.getPropertyValue('font-family');g.body.fontSize=bcs.getPropertyValue('font-size');g.body.lineHeight=bcs.getPropertyValue('line-height');
 }catch(e){}
 return g;}
function mkElFrom(k,lbl,kids,props,src){var e=mkEl(k);if(lbl)e.label=lbl;if(props)for(var pk in props){if(props[pk]!=null)e.props[pk]=props[pk];}if(src){if(src._id)e.id=src._id;if(src.gx!=null){e.gx=src.gx;e.gy=src.gy;e.gw=src.gw;e.gh=src.gh;}if(src.ex!=null){e.ex=src.ex;e.ey=src.ey;e.ew=src.ew;e.eh=src.eh;}if(src.desc)e.desc=src.desc;if(src.collapsed&&k==='subpanel'){e.props=e.props||{};e.props.collapsed='eingeklappt';}}if(CONTAINER[k]&&kids&&kids.length)e.els=kids.map(function(c){return mkElFrom(c.kind,c.label,c.els,c.props,c)});return e}
function normalize(raw){var out=[],ny=0,sky={};
 var kz=(raw||[]).filter(function(p){return p.zone==='kopf'}),rest=(raw||[]).filter(function(p){return p.zone!=='kopf'});
 if(kz.length){var kels=[];kz.forEach(function(p){(p.els||[]).forEach(function(e){kels.push(mkElFrom(e.kind,e.label,e.els,e.props,e))})});var kh=Math.max(2,kels.length+1);var KZ=kz[0]||{};var ko={id:KZ._id||uid(),title:'Seitenkopf',zone:'kopf',x:0,y:0,w:12,h:kh,collapsed:false,rank:1,els:kels};if(KZ.rw!=null){ko.rx=KZ.rx;ko.ry=KZ.ry;ko.rw=KZ.rw;ko.rh=KZ.rh;}out.push(ko);ny=kh;}
 function placeY(pg,x,w,h){var s=sky[pg]||(sky[pg]=[]);var i,top=ny;for(i=x;i<x+w;i++){if(s[i]!=null&&s[i]>top)top=s[i];}for(i=x;i<x+w;i++)s[i]=top+h;return top;}
 rest.forEach(function(p){var els=(p.els||[]).map(function(e){return mkElFrom(e.kind,e.label,e.els,e.props,e)});
  var hasGeom=els.some(function(e){return e.gx!=null});var maxb=0;els.forEach(function(e){if(e.gx!=null)maxb=Math.max(maxb,(e.gy||0)+(e.gh||1))});
  var h=hasGeom?Math.max(3,Math.ceil((maxb*GROWH+44)/ROWH)):Math.max(3,Math.min(12,2+els.length));
  var x=(p.x!=null)?clamp(p.x,0,11):0,w=(p.w!=null)?clamp(p.w,2,12):6;if(x+w>12)x=12-w;
  var pg=p.page||'',y=placeY(pg,x,w,h);
  var np={id:p._id||uid(),title:p.title||'Panel',page:pg,x:x,y:y,w:w,h:h,collapsed:!!p.collapsed,rank:1,els:els};
  if(p.rw!=null){np.rx=p.rx;np.ry=p.ry;np.rw=p.rw;np.rh=p.rh;}
  out.push(np)});
 return out;}
// Pixel-Mirror: schwere Klon-/CSS-Daten aus dem rohen Extrakt nach MIR übernehmen (nur in-process via App-UI laden).
function adoptMirror(raw){var m=raw&&raw._mir;var ok=m&&(m.kopfHtml||(m.pageHtml&&Object.keys(m.pageHtml).length));
 if(!ok){S.mirror=false;MIR={css:null,vars:null,body:null,capW:0,kopfHtml:'',pageHtml:{}};mirCssKey='';saveMir();return;}
 S.mirror=true;MIR={css:{links:(m.links||[]),styles:(m.styles||[])},vars:(m.vars||{}),body:(m.body||{}),capW:(m.capW||0),kopfHtml:(m.kopfHtml||''),pageHtml:(m.pageHtml||{})};mirCssKey='';saveMir();}
function loadFromRaw(raw,src){if(!raw||!raw.length){info('Keine Panels erkannt — App schon fertig geladen? Sonst Extraktor-Snippet nutzen.');return}adoptMirror(raw);S.panels=normalize(raw);S.refW=(raw.filter(function(p){return p.refW;})[0]||{}).refW||0;S.active=(S.panels[0]||{}).id||null;S.open=null;S.sel=null;var pgs=pageList();S.activePage=pgs[0];if(src&&!S.app)S.app=src;render();var np=S.panels.filter(function(p){return p.zone!=='kopf'}).length;info('✓ Übernommen: '+np+' Panels'+(pgs.length>1?' über '+pgs.length+' Seiten':'')+(src?' aus '+src:'')+(S.mirror?' — echte Optik (Pixel-Mirror). Doppelklick = Hintergrund/Bearbeiten.':'. Doppelklick auf ein Element zeigt den Ist-Zustand.'));}
function loadAppUI(){var io=$('pbIO');if(io.style.display==='none')openIO();
 if(!detectApp()){info('Standalone geöffnet — „App-UI laden" braucht die App-Adresse (…:PORT/ui-kit/ui-builder-tool.html). Hier stattdessen: „Extraktor-Snippet kopieren", auf der App-Seite ausführen, JSON einfügen + „JSON laden".');return;}
 info('Lese App-UI — gehe alle Seiten durch…');
 // Bei der echten Browser-Breite erfassen ⇒ Layout exakt wie auf dem Bildschirm (volle-Breite-Leisten, zentrierter schmaler Inhalt).
 var capW=Math.max(700,Math.round($('pbCanvas').clientWidth||(R.clientWidth-26)||window.innerWidth||1280));
 var f=document.createElement('iframe');f.setAttribute('aria-hidden','true');f.style.cssText='position:absolute;left:-10000px;top:0;width:'+capW+'px;height:2600px;border:0';f.src='/';document.body.appendChild(f);
 var done=false;
 function fail(m){if(done)return;done=true;try{f.remove()}catch(e){}info(m);}
 f.onload=function(){var win,doc;try{win=f.contentWindow;doc=f.contentDocument;}catch(e){fail('Andere Herkunft: das Tool muss von der App-Adresse geöffnet sein (…:PORT/ui-kit/ui-builder-tool.html). Alternativ Extraktor-Snippet.');return;}
  var t0=Date.now();(function ready(){var n;try{n=doc.querySelectorAll('.modulbar .mtab,.dz-oberregister a,main .card,.wrap .card,.card,.bnav').length;}catch(e){fail('Andere Herkunft: das Tool muss von der App-Adresse geöffnet sein (…:PORT/ui-kit/ui-builder-tool.html).');return;}
   if(n>=1||Date.now()-t0>6000){walkAndExtract(win,doc,info).then(function(raw){if(done)return;done=true;try{f.remove()}catch(e){}loadFromRaw(raw,detectApp());}).catch(function(e){fail('Import-Fehler: '+((e&&e.message)||e));});}
   else setTimeout(ready,200);})();};
 setTimeout(function(){fail('Zeitüberschreitung beim Lesen der App-UI. Versuch das Extraktor-Snippet.');},240000);}
function doImport(){var t=$('pbImp').value.trim();if(!t){info('Erst JSON einfügen.');return}var j;try{j=JSON.parse(t)}catch(e){info('Ungültiges JSON.');return}if(j&&j.panels){S.panels=j.panels;S.mirror=false;MIR={css:null,vars:null,body:null,capW:0,kopfHtml:"",pageHtml:{}};saveMir();S.active=(j.panels[0]||{}).id||null;S.open=null;render();info('✓ Layout geladen.');}else if(Array.isArray(j)){loadFromRaw(j,'');}else info('Unbekanntes Format.');}
function copyExtractor(){var snip='(function(){var f='+rawExtract.toString()+';var d=f(document);try{navigator.clipboard.writeText(JSON.stringify(d))}catch(e){}alert("dz Panel-Extraktor: "+d.length+" Panels erkannt + in die Zwischenablage kopiert. Jetzt im UI Builder Tool unter Import/Export einfügen und \\u201eJSON laden\\u201c.");return d;})();';try{navigator.clipboard.writeText(snip)}catch(e){}info('Snippet kopiert → auf der App-Seite Browser-Konsole (F12) öffnen, einfügen, Enter; dann das Ergebnis hier einfügen + „JSON laden".');}
$('pbIO').addEventListener('click',function(ev){var b=ev.target.closest('[data-act]');if(!b)return;var a=b.dataset.act;if(a==='copyx')copyExtractor();else if(a==='doimp')doImport();else if(a==='expjson'){$('pbImp').value=JSON.stringify({panels:S.panels},null,1);info('Aktuelles Layout als JSON ausgegeben (Strg+A, Strg+C zum Sichern).');}});
if(!S.app)S.app=detectApp();
// Desktop-Schnellzugriff (Dizz-Network-Fenster): ?lade=1 ⇒ Oberfläche automatisch übernehmen.
try{if(/[?&]lade=1(?:&|$)/.test(location.search)&&detectApp()){setTimeout(function(){try{history.replaceState(null,'',location.pathname);}catch(e){}loadAppUI();},500);}}catch(e){}
function tpl(){S.refW=0;S.mirror=false;MIR={css:null,vars:null,body:null,capW:0,kopfHtml:"",pageHtml:{}};S.app=S.app||'Beispiel · Übersicht';var a=addPanel();a.title='KPI-Kopfleiste';a.x=0;a.y=0;a.w=12;a.h=3;a.els=[mkEl('kpi'),mkEl('kpi'),mkEl('kpi'),mkEl('kpi')];
 var b=addPanel();b.title='Verlauf';b.x=0;b.y=3;b.w=8;b.h=6;b.els=[mkEl('tabs'),mkEl('chart')];
 var c=addPanel();c.title='Liste & Filter';c.x=8;c.y=3;c.w=4;c.h=6;c.els=[mkEl('search'),mkEl('table'),mkEl('link')];
 S.active=a.id;S.open=null}

function elSpec(e,ind){var p=e.props||{};var ex='';
 if(e.kind==='button')ex=' ['+p.variant+']';else if(e.kind==='select')ex=' {Optionen: '+p.options+'}';else if(e.kind==='range')ex=' {'+p.min+'–'+p.max+', Schritt '+p.step+'}';else if(e.kind==='badge')ex=' {'+p.state+'}';else if(e.kind==='tabs')ex=' {'+p.items+'}';else if(e.kind==='table')ex=' {'+p.cols+'×'+p.rows+(p.colnames?', Spalten: '+p.colnames:'')+'}';else if(e.kind==='chart')ex=' {'+p.ctype+'}';else if(e.kind==='link')ex=' {→ '+p.target+'}';else if(e.kind==='kpi')ex=' {Wert '+p.value+'}';else if(e.kind==='icon')ex=' {'+p.name+'}';
 else if(e.kind==='appkopf')ex=' {Marke '+p.brand+' · Funktion '+p.funktion+' · Streifen "'+p.tagline+'" · Stufe '+p.stufe+(String(p.hochsicher)==='ja'?' · hochsicher-Symbol':'')+'}';else if(e.kind==='gauge')ex=' {'+p.value+'/'+p.max+'}';else if(e.kind==='scatter')ex=' {'+p.xlab+' × '+p.ylab+'}';else if(e.kind==='ring')ex=' {'+p.rings+' Ringe}';else if(e.kind==='timeline')ex=' {'+p.span+'}';else if(e.kind==='cockpit')ex=' {Spalten: '+p.spalten+'}';else if(e.kind==='metric')ex=' {Wert '+p.value+' · Trend '+p.trend+'}';
 var bind=(p.zielId?' [→ Bindung: '+zielLabel(p.zielId)+']':'');
 var line=ind+'- ['+LBL[e.kind]+'] "'+(e.label||'')+'"'+ex+(p.aktion?' [Aktion/Link: '+p.aktion+']':'')+bind+' — '+(e.desc||'(keine Beschreibung)');
 if(CONTAINER[e.kind]){var ci=e.kind==='oberregister'?('Ebenen: '+(p.items||'')):('Klapp-Rang '+(p.rank||1)+(p.collapsed==='eingeklappt'?', standardmäßig eingeklappt':''));line=ind+'- ['+LBL[e.kind]+'] "'+(e.label||'')+'" ('+ci+')'+(e.desc?' — '+e.desc:'');(e.els||[]).forEach(function(x){line+='\n'+elSpec(x,ind+'    ')})}
 return line}
function buildSpec(){var L=['Panel-Bauplan für: '+(S.app||'(unbenannt)'),'Design: '+S.theme+' / '+S.farbe,''];
 S.panels.slice().sort(function(a,b){return a.y-b.y||a.x-b.x}).forEach(function(p,i){L.push((p.zone==='kopf'?'Seitenkopf':'Panel '+(i+1))+': "'+(p.title||'')+'" — Raster x'+p.x+' y'+p.y+' · Breite '+p.w+'/'+COLS+' · Höhe '+p.h+(p.collapsed?' · einklappbar':'')+(p.note?'\n  Zweck/Funktion: '+p.note:''));(p.els||[]).forEach(function(e){L.push(elSpec(e,'  '))});L.push('')});return L.join('\n')}
function doExport(){if(!S.panels.length){alert('Noch keine Panels.');return}var spec=buildSpec();
 var msg='Hier ist mein Panel-Bauplan aus dem UI Builder Tool. Bitte im echten Frontend umsetzen — geteiltes /ui-kit, echte dz-* Komponenten, dunkles Token-Theme, Spin/Collapse-Norm, kanonische Kopf-Norm + Oberregister/Ebenen (docs/39). Beschreibung je Element = gewünschte Funktion:\n\n'+spec+'\nJSON:\n'+JSON.stringify(S.panels);
 try{if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(msg)}catch(e){}
 if(typeof sendPrompt==='function'){sendPrompt(msg)}
 else{var o=$('pbOut');o.style.display='block';o.value=msg;o.focus();o.select();}}
})();
