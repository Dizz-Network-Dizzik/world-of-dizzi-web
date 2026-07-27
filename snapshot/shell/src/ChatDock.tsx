import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  deleteMemory, fetchAiHistory, fetchAiStatus, fetchMemory, fetchNotices,
  markNoticesRead, speak, streamChat, transcribe,
  type AiStatus, type ChatMessage, type MemoryFact, type Notice,
} from "./api";
import { Icon } from "./icons";

/* Dizzi-Konsole: DAS Interaktionsfenster, oben mittig über den Panels.
   - „DIZZI"-Schriftzug darüber (Name der KI: Dizzi, Nutzer-Festlegung 11.06.)
   - Texteingabe + Senden, Streaming-Antworten
   - Sensibel-Schloss 🔒 (Anfrage bleibt garantiert lokal)
   - Mikrofon: sichtbarer, vorbereiteter Anschluss — die echte Aufnahme/
     Transkription kommt mit der Sprachschicht (Phase 4, faster-whisper
     lokal); bis dahin erklärt der Klick das ehrlich.
   - Gedächtnis-Ansicht über das Hirn-Icon umschaltbar */

export function DizziConsole() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [showMemory, setShowMemory] = useState(false);
  const [noticeList, setNoticeList] = useState<Notice[]>([]);
  const [showNotices, setShowNotices] = useState(false);
  const [input, setInput] = useState("");
  const [sensitive, setSensitive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [speakOn, setSpeakOn] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const speakRef = useRef(false);
  speakRef.current = speakOn;

  useEffect(() => {
    fetchAiStatus().then(setStatus).catch(() => {});
    fetchAiHistory().then(setMsgs).catch(() => {});
    fetchMemory().then(setFacts).catch(() => {});
    const loadNotices = () => fetchNotices().then(setNoticeList).catch(() => {});
    loadNotices();
    const iv = setInterval(loadNotices, 60000);
    return () => clearInterval(iv);
  }, []);

  const unread = noticeList.filter((n) => !n.read_at).length;

  const toggleNotices = () => {
    const next = !showNotices;
    setShowNotices(next);
    if (next) {
      setShowMemory(false);
      if (unread > 0) {
        void markNoticesRead().then(() =>
          fetchNotices().then(setNoticeList).catch(() => {}));
      }
    }
  };

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [msgs]);

  const send = async (textOverride?: string) => {
    const text = (textOverride ?? input).trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setNote(null);
    setShowMemory(false);
    setMsgs((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    let answerAcc = ""; // für die Sprachausgabe nach dem done-Event
    try {
      await streamChat(text, sensitive, (e) => {
        if ("t" in e) {
          answerAcc += e.t;
          setMsgs((m) => {
            const out = [...m];
            out[out.length - 1] = {
              ...out[out.length - 1],
              content: out[out.length - 1].content + e.t,
            };
            return out;
          });
        } else if ("tool" in e) {
          setNote(`🛠 ${t("using_tool")}: ${e.tool}`);
        } else if ("memory_saved" in e) {
          setNote(`${t("memory_saved")}: ${e.memory_saved}`);
          fetchMemory().then(setFacts).catch(() => {});
        } else if ("done" in e) {
          setMsgs((m) => {
            const out = [...m];
            out[out.length - 1] = { ...out[out.length - 1], provider: e.provider };
            return out;
          });
          if (speakRef.current && answerAcc) {
            speak(answerAcc)
              .then((blob) => { void new Audio(URL.createObjectURL(blob)).play(); })
              .catch(() => {});
          }
        } else if ("error" in e) {
          setMsgs((m) => {
            const out = [...m];
            out[out.length - 1] = { ...out[out.length - 1], content: `⚠ ${e.error}` };
            return out;
          });
        }
      });
    } catch {
      setMsgs((m) => {
        const out = [...m];
        out[out.length - 1] = { ...out[out.length - 1], content: `⚠ ${t("core_error")}` };
        return out;
      });
    } finally {
      setBusy(false);
    }
  };

  const removeFact = async (id: string) => {
    await deleteMemory(id);
    setFacts((f) => f.filter((x) => x.id !== id));
  };

  // Push-to-talk: Klick startet die Aufnahme, zweiter Klick stoppt →
  // lokale Whisper-Transkription → automatisch senden.
  const toggleMic = async () => {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setRecording(false);
        setNote(t("mic_transcribing"));
        try {
          const text = await transcribe(new Blob(chunks, { type: rec.mimeType }));
          setNote(null);
          if (text) void send(text);
          else setNote(t("mic_nothing"));
        } catch {
          setNote(t("mic_failed"));
        }
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setNote(t("mic_recording"));
    } catch {
      setNote(t("mic_denied"));
    }
  };

  const hasConversation = msgs.length > 0;

  return (
    <section className="consolewrap">
      <div className="dizzititle">
        <span className="dz">DIZZI</span>
        {/* UX-5a · AI-Act Art. 50(1): KI-Offenlegung an der Chat-Fläche (docs/70; Optik = .dz-agentchip). */}
        <span
          className="dz-agentchip"
          title="Du sprichst mit einer KI (läuft lokal auf deinem Rechner)."
          aria-label="Du sprichst mit einer KI (läuft lokal auf deinem Rechner)."
        >
          <span className="ac-dot aus" aria-hidden="true" />KI
        </span>
        {status && (
          <span className={`dockstatus ${status.ollama_ok ? "on" : "off"}`}>
            {status.ollama_ok ? status.active_model : t("ai_offline")}
          </span>
        )}
        <button
          className={`membtn ${showMemory ? "on" : ""}`}
          onClick={() => { setShowMemory((s) => !s); setShowNotices(false); }}
          title={t("tab_memory")}
        >
          <Icon name="brain" />
        </button>
        <button
          className={`membtn ${showNotices ? "on" : ""}`}
          onClick={toggleNotices}
          title={t("tab_notices")}
        >
          <Icon name="bell" />
          {unread > 0 && <span className="badge">{unread}</span>}
        </button>
      </div>
      <div className="console">
        {showNotices ? (
          <div className="consolelist" ref={listRef}>
            {noticeList.length === 0 && <div className="dockempty">{t("notices_empty")}</div>}
            {noticeList.map((n) => (
              <div key={n.id} className={`noticerow ${n.severity}`}>
                <div className="nhead">
                  <span className={`pill sev-${n.severity}`}>{n.severity}</span>
                  <span className="ntitle">{n.title}</span>
                </div>
                <div className="ndetail">{n.detail}</div>
              </div>
            ))}
          </div>
        ) : showMemory ? (
          <div className="consolelist" ref={listRef}>
            {facts.length === 0 && <div className="dockempty">{t("memory_empty")}</div>}
            {facts.map((f) => (
              <div key={f.id} className="factrow">
                <span className={`pill ${f.source === "explizit" ? "aktiv" : ""}`}>{f.source}</span>
                <span className="ftxt">{f.fact}</span>
                <button className="x" onClick={() => void removeFact(f.id)} aria-label={t("close")}>×</button>
              </div>
            ))}
          </div>
        ) : (
          hasConversation && (
            <div className="consolelist" ref={listRef}>
              {msgs.map((m, i) => (
                <div key={i} className={`bubble ${m.role}`}>
                  {m.content || <span className="thinking">{t("thinking")}</span>}
                  {m.role === "assistant" && m.provider && <span className="prov">{m.provider}</span>}
                </div>
              ))}
              {note && <div className="memnote">{note}</div>}
            </div>
          )
        )}
        <div className="dockinput">
          <button
            className={`lockbtn ${sensitive ? "on" : ""}`}
            onClick={() => setSensitive((s) => !s)}
            title={t("sensitive_hint")}
          >
            <Icon name="lock" />
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
            }}
            placeholder={t("chat_placeholder")}
            rows={1}
          />
          <button
            className={`micbtn ${recording ? "rec" : ""}`}
            onClick={() => void toggleMic()}
            title={recording ? t("mic_stop") : t("mic_start")}
          >
            <Icon name="mic" />
          </button>
          <button
            className={`micbtn ${speakOn ? "spk" : ""}`}
            onClick={() => setSpeakOn((s) => !s)}
            title={t("speak_toggle")}
          >
            <Icon name="speaker" />
          </button>
          <button className="sendbtn" onClick={() => void send()} disabled={busy}>
            <Icon name="send" />
          </button>
        </div>
        {note && !hasConversation && !showMemory && <div className="memnote standalone">{note}</div>}
      </div>
    </section>
  );
}
