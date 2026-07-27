// Dizz Network — kleines natives Statusfenster fürs GESAMTE Netzwerk (nicht mehr nur Trading).
// Erscheint im Windows-Taskmanager unter PROZESSE → APPS als „Dizz Network" mit Neon-Icon.
//
// ★ 02.07.2026 aus apps\trading\programm\scripts nach ops\monitor\ VERLEGT (es ist ein netzweiter
//   Launcher, kein Trading-Teil). Eigene Autostart-Verknüpfung im Windows-Startup-Ordner.
//
// ★ 22.07.2026 v2.9: Die Trading-Kachel differenziert jetzt ehrlich Online/Offline. Der Backend-Poll
//   (:8137, liest lokale Trade-DBs) läuft im Flugmodus weiter — doch eine winzige öffentliche Bitget-
//   Erreichbarkeitsprobe (ohne Auth, ohne Kontakt zum Geld-System) zeigt, ob wirklich gehandelt wird
//   (grün „Bitget verbunden — Bots handeln aktiv") oder nur die Historie sichtbar ist (magenta „OFFLINE").
//
// Warum eine eigene EXE (statt python/tkinter): der Taskmanager benennt App-Einträge nach der
// FileDescription der EXE-Versionsressource und zeigt deren eingebettetes Icon — eine umbenannte
// pythonw-Kopie hieße dort „Python". Diese EXE trägt beides selbst (AssemblyTitle + /win32icon
// beim Build, siehe build_monitor.ps1). Kein .NET-Zusatz nötig (Framework 4.x ist Teil von Windows).
//
// Verhalten: pollt alle 5 s PARALLEL den Dizzi-Core (:8200, „Netzwerk live") + Dizz Trading
// (:8137 → 51/51 + Winrate + Profit + offene Trades) + die übrigen Apps (/api/health). Oben
// Netzwerk-Status, Mitte Trading prominent (3 Stats: Winrate + Profit + Offen), unten kompakte
// Gruppen, welche Dienste gerade laufen (grün) bzw. ruhen (grau). DIREKT-VERLINKUNGEN (klickbar,
// Hand-Cursor): Titel „DIZZ NETWORK" → Core-Dashboard (the world of dizzi), „Dizz Trading" → :8137,
// jeder Dienst-Chip → seine App-Seite. UNTEN: ZWEI voll-breite Knöpfe — „PROJEKTPLAN" öffnet den
// interaktiven Projektstand (_netzwerk/PROJEKT_STAND.html), darunter „GESAMTSYSTEM-KARTE" die
// Konstellations-Karte (_netzwerk/SYSTEM_KARTE.html) — beide lokal im Browser, ohne Server.
// X schließt NUR die Anzeige — Backends & Bots laufen unabhängig weiter. Singleton via Mutex.
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Net;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("Dizz Network")]
[assembly: System.Reflection.AssemblyProduct("Dizz Network")]
[assembly: System.Reflection.AssemblyDescription("Status: Dizzi-Netzwerk (Kommandozentrale + Apps)")]
[assembly: System.Reflection.AssemblyFileVersion("2.9.0.0")]
[assembly: System.Reflection.AssemblyVersion("2.9.0.0")]

namespace DizzNetwork
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            bool created;
            using (new Mutex(true, "DizzNetworkMonitor", out created))
            {
                if (!created) return;   // läuft schon — kein Doppel-Fenster
                Application.EnableVisualStyles();
                // v2.9: .NET Framework 4.x wählt sonst evtl. TLS<1.2 ⇒ die HTTPS-Bitget-Probe schlägt fehl.
                ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
                Application.Run(new MonitorForm());
            }
        }
    }

    // Eine Netzwerk-App: Anzeigename + Port + ob sie erreichbar ist (zuletzt gepollt).
    // Rect = beim Zeichnen gesetzte Klick-Fläche (Direkt-Link auf die App-Seite).
    class App
    {
        public string Name; public int Port; public bool Live; public Rectangle Rect;
        public Rectangle BuildRect;   // Klick-Fläche des Bautool-Chips (→ …/ui-kit/ui-builder-tool.html)
        public App(string n, int p) { Name = n; Port = p; }
    }

    class MonitorForm : Form
    {
        static readonly Color BG   = ColorTranslator.FromHtml("#0b0917");
        static readonly Color CARD = ColorTranslator.FromHtml("#141029");
        static readonly Color CY   = ColorTranslator.FromHtml("#2fe7ff");
        static readonly Color MG   = ColorTranslator.FromHtml("#ff3df0");
        static readonly Color GRN  = ColorTranslator.FromHtml("#3dffb0");
        static readonly Color MUT  = ColorTranslator.FromHtml("#9286bd");
        static readonly Color OFF  = ColorTranslator.FromHtml("#4a4170");

        // POLLING (Erreichbarkeit) bleibt auf 127.0.0.1 (IPv4-Bind der Server, zuverlässig).
        const string CORE = "http://127.0.0.1:8200";   // Poll: Dizzi-Kommandozentrale
        const string TRADE = "http://127.0.0.1:8137";  // Poll: Dizz Trading (Stats)
        // BROWSER-LINKS auf localhost: dort leben IdP-Session + Passkey (appkit
        // DEFAULT_NAV_ISSUER=localhost) ⇒ Anmeldung/Passkey konsistent (Nutzer-Wunsch 18.06.).
        const string LINK_HOST  = "http://localhost:";
        const string LINK_CORE  = "http://localhost:8200";
        const string LINK_TRADE = "http://localhost:8137";

        // Das Netzwerk: Trading wird separat mit Stats behandelt; diese Apps nur „läuft/ruht".
        readonly App[] _apps = new[]
        {
            // Ports = kanonische Netzwerk-Ports (Chat-Management §0). 19.06. korrigiert:
            // Music ABGEWICKELT (in Creating eingeschmolzen) ⇒ raus · Plans + Leading
            // ABGEWICKELT (in die vereinte App „Dizz Admin" :8222 verschmolzen, docs/28)
            // ⇒ raus · Memory 8212 · Admin 8222 = die vereinte Verwaltung (klickbarer
            // Localhost-Link localhost:8222) · „Social" → „Management" (8213).
            new App("News", 8216), new App("Comm", 8218), new App("Money", 8210),
            new App("Admin", 8222), new App("Memory", 8212), new App("Management", 8213),
            new App("Create", 8214), new App("Health", 8217),
        };

        // Bautool-Reihe = die 8 Dienste PLUS Trading (eigener Stack :8137) und Core/Network (:8200),
        // damit auch die beiden mit dem UI Builder Tool bearbeitet werden können (Nutzer-Wunsch v2.6).
        readonly App _trBuild = new App("Trading", 8137);
        readonly App _coBuild = new App("Core", 8200);
        App[] _buildApps;

        // Vom Polling gesetzt, vom Paint gelesen (nur UI-Thread via BeginInvoke).
        bool _coreLive, _tradeLive, _tradeAllUp;
        bool _bitgetLive;   // v2.9: öffentliche Bitget-Erreichbarkeit (kein Auth, KEIN Kontakt zum Geld-System)
        int _running, _bots, _tradeOpen;
        double _winrate, _profitPct;

        // Klick-Flächen (beim Zeichnen gesetzt): Titel → Core-Dashboard, Trading → :8137,
        // _projektRect = „PROJEKTPLAN"-Knopf, _karteRect = „GESAMTSYSTEM-KARTE"-Knopf (beide ganz unten).
        Rectangle _titleRect, _tradeRect, _projektRect, _karteRect;

        // — Dizzi-Sprachzeile (eigener schneller 1-s-Takt) —
        bool _wakeLive;            // Daemon lauscht?
        int _wakeTreffer = -1;     // treffer_gesamt (—1 = noch nie gepollt)
        DateTime _aufnahmeBis = DateTime.MinValue;  // bis dahin „zeichnet auf"-Zustand

        public MonitorForm()
        {
            Text = "Dizz Network";
            BackColor = BG;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            // Höhe für: Titel + Sprachzeile + Trading + Dienste-Chips + Bautool-Chips (10 Stück)
            // + die ZWEI voll-breiten Knöpfe unten (v2.8: PROJEKTPLAN über GESAMTSYSTEM-KARTE;
            //   je 30 px + 8 px Abstand → +38 px gegenüber v2.7).
            ClientSize = new Size(396, 390);   // v2.9: +18 px für die Online/Offline-Statuszeile der Trading-Kachel
            // Bautool-Reihe = 8 Dienste + Trading + Core.
            _buildApps = new App[_apps.Length + 2];
            _apps.CopyTo(_buildApps, 0);
            _buildApps[_apps.Length] = _trBuild;
            _buildApps[_apps.Length + 1] = _coBuild;
            StartPosition = FormStartPosition.Manual;
            DoubleBuffered = true;
            var wa = Screen.PrimaryScreen.WorkingArea;          // dezent unten rechts
            Location = new Point(wa.Right - Width - 18, wa.Bottom - Height - 18);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            // (v2.5: „Netzwerk-Dashboard öffnen"-Button entfernt — der Titel „DIZZ NETWORK"
            //  ist bereits der Direkt-Link aufs Core-Dashboard.)

            var timer = new System.Windows.Forms.Timer { Interval = 5000 };
            timer.Tick += (s, e) => Poll();
            timer.Start();
            Poll();

            // Eigener schneller Takt nur für den Wake-Status (leichter Endpoint),
            // damit „Hey Dizzi erkannt → zeichnet auf" zeitnah erscheint.
            var wakeTimer = new System.Windows.Forms.Timer { Interval = 1000 };
            wakeTimer.Tick += (s, e) => PollWake();
            wakeTimer.Start();
            PollWake();
        }

        void PollWake()
        {
            ThreadPool.QueueUserWorkItem(_ =>
            {
                string j = Get(CORE + "/api/ai/wake/status", 1200);
                bool live = j != null && BoolOf(j, "laeuft");
                int treffer = j != null ? IntOf(j, "treffer_gesamt") : -1;
                try
                {
                    BeginInvoke((Action)(() =>
                    {
                        // Neuer Treffer (treffer_gesamt gestiegen) ⇒ 5 s „zeichnet auf".
                        if (treffer >= 0 && _wakeTreffer >= 0 && treffer > _wakeTreffer)
                            _aufnahmeBis = DateTime.Now.AddSeconds(5);
                        _wakeLive = live; _wakeTreffer = treffer;
                        Invalidate();
                    }));
                }
                catch { }
            });
        }

        void Poll()
        {
            ThreadPool.QueueUserWorkItem(_ =>
            {
                bool core = Reachable(CORE + "/api/health", 1500);
                string tj = Get(TRADE + "/api/summary", 2500);
                foreach (var a in _apps)
                    a.Live = Reachable("http://127.0.0.1:" + a.Port + "/api/health", 900);
                // v2.9: winzige öffentliche Bitget-Probe (ohne Auth). Im Flugmodus scheitert schon DNS ⇒ false.
                bool bitget = Reachable("https://api.bitget.com/api/v2/public/time", 1500);

                bool tLive = tj != null;
                int running = tLive ? IntOf(tj, "running") : 0;
                int bots = tLive ? IntOf(tj, "bots") : 0;
                int wins = tLive ? IntOf(tj, "wins") : 0;
                int done = tLive ? IntOf(tj, "trades_done") : 0;
                int open = tLive ? IntOf(tj, "trades_open") : 0;
                double winrate = done > 0 ? 100.0 * wins / done : 0.0;
                double profit = tLive ? DoubleOf(tj, "profit_pct") : 0.0;

                try
                {
                    BeginInvoke((Action)(() =>
                    {
                        _coreLive = core; _tradeLive = tLive; _bitgetLive = bitget;
                        _trBuild.Live = tLive; _coBuild.Live = core;   // Bautool-Chip-Punkte
                        _running = running; _bots = bots; _tradeAllUp = bots > 0 && running == bots;
                        _winrate = winrate; _profitPct = profit; _tradeOpen = open;
                        Invalidate();
                    }));
                }
                catch { }
            });
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            int W = ClientSize.Width;

            using (var fTitle = new Font("Segoe UI", 13f, FontStyle.Bold))
            using (var fPill  = new Font("Segoe UI", 8f, FontStyle.Bold))
            using (var fApp   = new Font("Segoe UI", 11f, FontStyle.Bold))
            using (var fStat  = new Font("Segoe UI", 11.5f, FontStyle.Bold))
            using (var fLab   = new Font("Segoe UI", 8f, FontStyle.Bold))
            using (var fGrp   = new Font("Segoe UI", 9f))
            {
                Pen line = new Pen(Color.FromArgb(60, 150, 120, 210));

                // — Titel + Netzwerk-Live-Pille — (Titel klickbar → the world of dizzi)
                Text2(g, "DIZZ", fTitle, CY, 16, 10);
                float dx = 16 + g.MeasureString("DIZZ", fTitle).Width - 4;
                Text2(g, "NETWORK", fTitle, MG, dx, 10);
                _titleRect = new Rectangle(14, 6, (int)(dx + g.MeasureString("NETWORK", fTitle).Width) - 14 + 8, 30);
                DrawPill(g, W - 96, 13, 80, 20, _coreLive ? GRN : OFF,
                         _coreLive ? "● LIVE" : "○ AUS", fPill);

                // — Dizzi-Sprachzeile DIREKT UNTER DEM TITEL (Nutzer-Wunsch v2.5) —
                bool aufnahme = DateTime.Now < _aufnahmeBis;
                Text2(g, "Dizzi:", fLab, MG, 16, 41);
                float dox = 16 + g.MeasureString("Dizzi:", fLab).Width + 6;
                if (aufnahme)
                {
                    Dot(g, dox, 42, MG);
                    Text2(g, "» Hey Dizzi « — zeichnet auf …", fGrp, MG, dox + 14, 38);
                }
                else if (_wakeLive)
                {
                    Dot(g, dox, 42, GRN);
                    Text2(g, "lauscht auf » Hey Dizzi «", fGrp, Color.White, dox + 14, 38);
                }
                else
                {
                    Dot(g, dox, 42, OFF);
                    Text2(g, "Spracherkennung aus", fGrp, MUT, dox + 14, 38);
                }

                g.DrawLine(line, 16, 62, W - 16, 62);

                // — Dizz Trading (klickbar → :8137; 3 Stats: Winrate · Profit · Offen) —
                _tradeRect = new Rectangle(14, 66, W - 28, 84);   // v2.9: +18 px (Statuszeile liegt im Klickfeld)
                Text2(g, "Dizz Trading", fApp, CY, 16, 68);
                string botTxt = _tradeLive ? (_running + "/" + _bots + " Bots") : "offline";
                Color botCol = !_tradeLive ? MG : (_tradeAllUp ? GRN : MG);
                Dot(g, W - 150, 74, botCol);
                Text2(g, botTxt, fLab, botCol, W - 138, 70);

                if (_tradeLive)
                {
                    Text2(g, "Winrate", fLab, MUT, 18, 96);
                    Text2(g, _winrate.ToString("0.0") + "%", fStat, CY, 18, 110);
                    Text2(g, "Profit", fLab, MUT, 150, 96);
                    Color pc = _profitPct >= 0 ? GRN : MG;
                    Text2(g, (_profitPct >= 0 ? "+" : "") + _profitPct.ToString("0.0") + "%", fStat, pc, 150, 110);
                    Text2(g, "Offen", fLab, MUT, 272, 96);
                    Text2(g, _tradeOpen.ToString(), fStat, Color.White, 272, 110);
                    // v2.9: Online/Offline-Ehrlichkeit — grün = Bitget verbunden & aktiv, magenta = nur Historie.
                    if (_bitgetLive)
                    {
                        Dot(g, 18, 138, GRN);
                        Text2(g, "Bitget verbunden — Bots handeln aktiv", fGrp, GRN, 32, 134);
                    }
                    else
                    {
                        Dot(g, 18, 138, MG);
                        Text2(g, "OFFLINE — kein Bitget · kein Handel · Historie sichtbar", fGrp, MUT, 32, 134);
                    }
                }
                else
                {
                    Text2(g, "Backend nicht erreichbar", fGrp, MUT, 18, 102);
                }

                g.DrawLine(line, 16, 156, W - 16, 156);

                // — Dienste: kompakte Gruppen (grün = läuft, grau = ruht), Chip → App-Seite —
                Text2(g, "DIENSTE IM NETZWERK", fLab, MUT, 16, 162);
                int yEnd = DrawChips(g, fGrp, 180, _apps, false);

                // — UI Builder Tool-Schnellzugriff: je App ein Chip → öffnet das Bautool DER App
                //   (…/ui-kit/ui-builder-tool.html?lade=1 lädt die echte Oberfläche automatisch). —
                int divY = yEnd + 7;
                g.DrawLine(line, 16, divY, W - 16, divY);
                Text2(g, "UI BUILDER TOOL · OBERFLÄCHE LADEN (auch Trading + Core)", fLab, MUT, 16, divY + 7);
                int buildEnd = DrawChips(g, fGrp, divY + 25, _buildApps, true);

                // — ZWEI voll-breite Knöpfe ganz unten (v2.8): PROJEKTPLAN (oben) über
                //   GESAMTSYSTEM-KARTE (unten). Öffnen die self-contained HTML lokal im Browser,
                //   ohne Server (_netzwerk/PROJEKT_STAND.html bzw. SYSTEM_KARTE.html). —
                int kx = 16, kw = W - 32, kh = 30;
                int py = buildEnd + 14;
                DrawWideButton(g, new Rectangle(kx, py, kw, kh), "PROJEKTPLAN  ↗", fApp);
                _projektRect = new Rectangle(kx, py, kw, kh);

                int ky = py + kh + 8;
                DrawWideButton(g, new Rectangle(kx, ky, kw, kh), "GESAMTSYSTEM-KARTE  ↗", fApp);
                _karteRect = new Rectangle(kx, ky, kw, kh);

                line.Dispose();
            }
        }

        // Zeichnet die App-Chips ab Höhe y0 mit Umbruch. builder=false ⇒ Dienst-Chips
        // (→ App-Seite, a.Rect); builder=true ⇒ Bautool-Chips (→ …/ui-kit/ui-builder-tool.html,
        // a.BuildRect). Rückgabe = Unterkante der letzten Reihe.
        int DrawChips(Graphics g, Font f, int y0, App[] list, bool builder)
        {
            int W = ClientSize.Width;
            int x = 18, y = y0;
            foreach (var a in list)
            {
                float wlbl = g.MeasureString(a.Name, f).Width;
                int chip = (int)wlbl + 22;
                if (x + chip > W - 14) { x = 18; y += 22; }
                Color dotc = a.Live ? (builder ? CY : GRN) : OFF;
                Color txtc = a.Live ? (builder ? CY : Color.White) : MUT;
                Dot(g, x, y + 4, dotc);
                Text2(g, a.Name, f, txtc, x + 12, y);
                var r = new Rectangle(x - 2, y - 1, chip, 19);
                if (builder) a.BuildRect = r; else a.Rect = r;
                x += chip;
            }
            return y + 19;
        }

        // Voll-breiter Neon-Gradient-Knopf (Mattglanz-Metall-Stil), zentrierter Text.
        static void DrawWideButton(Graphics g, Rectangle r, string label, Font f)
        {
            using (var path = Round(r, 9))
            using (var lg = new LinearGradientBrush(r,
                    Color.FromArgb(46, MG.R, MG.G, MG.B), Color.FromArgb(46, CY.R, CY.G, CY.B), 0f))
            using (var pen = new Pen(CY))
            {
                g.FillPath(lg, path);
                g.DrawPath(pen, path);
            }
            var sz = g.MeasureString(label, f);
            Text2(g, label, f, CY, r.X + (r.Width - sz.Width) / 2f, r.Y + (r.Height - sz.Height) / 2f);
        }

        // — Direkt-Verlinkungen: Titel → Core, Trading → :8137, Dienst-Chip → App-Seite,
        //   Bautool-Chip → …/ui-kit/ui-builder-tool.html?lade=1, PROJEKTPLAN → PROJEKT_STAND.html,
        //   GESAMTSYSTEM-KARTE → SYSTEM_KARTE.html. —
        string UrlAt(Point p)
        {
            if (_titleRect.Contains(p)) return LINK_CORE;
            if (_tradeRect.Contains(p)) return LINK_TRADE;
            if (_projektRect.Contains(p)) return NetzPath("PROJEKT_STAND.html");
            if (_karteRect.Contains(p)) return NetzPath("SYSTEM_KARTE.html");
            foreach (var a in _apps)
                if (a.Rect.Contains(p)) return LINK_HOST + a.Port;
            foreach (var a in _buildApps)
                if (a.BuildRect.Contains(p)) return LINK_HOST + a.Port + "/ui-kit/ui-builder-tool.html?lade=1";
            return null;
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            var url = UrlAt(e.Location);
            if (url != null) { try { Process.Start(url); } catch { } }
            base.OnMouseClick(e);
        }

        // Pfad zu einer _netzwerk-Seite (self-contained HTML — lokal, ohne Server, im
        // Standard-Browser geöffnet). Kanonischer Ort zuerst, sonst relativ zur EXE.
        static string NetzPath(string file)
        {
            string canon = @"C:\Dizzik\code\dizz-network\_netzwerk\" + file;
            if (System.IO.File.Exists(canon)) return canon;
            try
            {
                string dir = System.IO.Path.GetDirectoryName(Application.ExecutablePath);
                // ops\monitor → ops → dizz-network → _netzwerk\<file>
                string repo = System.IO.Path.GetFullPath(System.IO.Path.Combine(dir, "..", ".."));
                string rel = System.IO.Path.Combine(repo, "_netzwerk", file);
                if (System.IO.File.Exists(rel)) return rel;
            }
            catch { }
            return canon;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            Cursor = UrlAt(e.Location) != null ? Cursors.Hand : Cursors.Default;
            base.OnMouseMove(e);
        }

        static void Text2(Graphics g, string s, Font f, Color c, float x, float y)
        {
            using (var b = new SolidBrush(c)) g.DrawString(s, f, b, x, y);
        }

        static void Dot(Graphics g, float x, float y, Color c)
        {
            using (var b = new SolidBrush(c)) g.FillEllipse(b, x, y, 8, 8);
            using (var p = new Pen(Color.FromArgb(90, c.R, c.G, c.B), 3))
                g.DrawEllipse(p, x - 1.5f, y - 1.5f, 11, 11);   // sanfter Glow-Ring
        }

        static void DrawPill(Graphics g, int x, int y, int w, int h, Color c, string txt, Font f)
        {
            using (var path = Round(new Rectangle(x, y, w, h), h / 2))
            using (var bg = new SolidBrush(Color.FromArgb(36, c.R, c.G, c.B)))
            using (var pen = new Pen(c))
            using (var br = new SolidBrush(c))
            {
                g.FillPath(bg, path);
                g.DrawPath(pen, path);
                var sz = g.MeasureString(txt, f);
                g.DrawString(txt, f, br, x + (w - sz.Width) / 2, y + (h - sz.Height) / 2);
            }
        }

        static GraphicsPath Round(Rectangle r, int rad)
        {
            var p = new GraphicsPath(); int d = rad * 2;
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        static bool Reachable(string url, int timeoutMs)
        {
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.Timeout = timeoutMs;
                using (var resp = (HttpWebResponse)req.GetResponse())
                    return (int)resp.StatusCode == 200;
            }
            catch { return false; }
        }

        static string Get(string url, int timeoutMs)
        {
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.Timeout = timeoutMs;
                using (var resp = req.GetResponse())
                using (var sr = new System.IO.StreamReader(resp.GetResponseStream()))
                    return sr.ReadToEnd();
            }
            catch { return null; }
        }

        static int IntOf(string json, string key)
        {
            var m = Regex.Match(json, "\"" + key + "\"\\s*:\\s*(\\d+)");
            return m.Success ? int.Parse(m.Groups[1].Value) : 0;
        }

        static double DoubleOf(string json, string key)
        {
            var m = Regex.Match(json, "\"" + key + "\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)");
            return m.Success
                ? double.Parse(m.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture)
                : 0.0;
        }

        static bool BoolOf(string json, string key)
        {
            return Regex.IsMatch(json, "\"" + key + "\"\\s*:\\s*true");
        }
    }
}
