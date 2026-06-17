import { useEffect, useRef, useState } from "react";
import { Link, usePage } from "@inertiajs/react";
import { fetchJson } from "../../utils/fetchJson.js";

const CSS = `
.home-root { min-height: calc(100vh - 48px); display:flex; flex-direction:column; position:relative; }
.center-wrap { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; padding-bottom:80px; gap:16px; position:relative; z-index:1; }
.panel-label { position:absolute; top:calc(11.8vh - 44px); left:50%; transform:translateX(-50%); font-size:32px; font-weight:700; letter-spacing:3px; white-space:nowrap;
  background:linear-gradient(90deg,var(--text-3) 0%,rgba(255,108,55,.75) 40%,rgba(255,140,80,.9) 50%,rgba(255,108,55,.75) 60%,var(--text-3) 100%);
  background-size:220% auto; -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; animation:shimmer 7s linear infinite; }
[data-theme="light"] .panel-label { background:linear-gradient(90deg,var(--text-2) 0%,rgba(255,108,55,.85) 40%,rgba(255,140,80,1) 50%,rgba(255,108,55,.85) 60%,var(--text-2) 100%); background-size:220% auto; -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
@keyframes shimmer { 0%{background-position:0% center;} 100%{background-position:220% center;} }
.doc-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; width:100%; max-width:400px; }
.doc-tile:last-child:nth-child(3n+1) { grid-column:2; }
@keyframes tileIn { from{opacity:0;transform:translateY(18px) scale(.95);} to{opacity:1;transform:translateY(0) scale(1);} }
.doc-grid .doc-tile:nth-child(1){animation:tileIn .4s .05s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(2){animation:tileIn .4s .10s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(3){animation:tileIn .4s .15s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(4){animation:tileIn .4s .20s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(5){animation:tileIn .4s .25s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(6){animation:tileIn .4s .30s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(7){animation:tileIn .4s .35s cubic-bezier(.34,1.56,.64,1) both;}
.doc-grid .doc-tile:nth-child(8){animation:tileIn .4s .40s cubic-bezier(.34,1.56,.64,1) both;}
.doc-tile { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; padding:24px 12px; text-decoration:none; color:var(--text); border-radius:var(--r-2xl); border:1px solid rgba(255,255,255,.07); background:rgba(255,255,255,.04); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); transition:background .2s,border-color .2s,transform .2s cubic-bezier(.34,1.56,.64,1),box-shadow .2s; position:relative; overflow:hidden; }
.doc-tile::before { content:''; position:absolute; top:0; left:0; right:0; height:1px; background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent); opacity:0; transition:opacity .2s; }
.doc-tile:hover::before { opacity:1; }
[data-theme="light"] .doc-tile { border:1px solid rgba(0,0,0,.07); background:rgba(255,255,255,.55); }
.doc-tile:hover { background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.13); transform:translateY(-3px) scale(1.01); }
[data-theme="light"] .doc-tile:hover { background:rgba(255,255,255,.80); border-color:rgba(0,0,0,.12); }
.doc-tile:active { transform:translateY(0) scale(.98); opacity:.85; }
.doc-tile:hover .tile-icon { transform:scale(1.13); }
.doc-tile.cl:hover{box-shadow:0 8px 30px rgba(255,108,55,.18),0 2px 8px rgba(0,0,0,.2);border-color:rgba(255,108,55,.28);}
.doc-tile.inv:hover{box-shadow:0 8px 30px rgba(139,92,246,.18),0 2px 8px rgba(0,0,0,.2);border-color:rgba(139,92,246,.28);}
.doc-tile.svc:hover{box-shadow:0 8px 30px rgba(16,185,129,.16),0 2px 8px rgba(0,0,0,.2);border-color:rgba(16,185,129,.26);}
.doc-tile.cal:hover{box-shadow:0 8px 30px rgba(245,158,11,.16),0 2px 8px rgba(0,0,0,.2);border-color:rgba(245,158,11,.26);}
.doc-tile.cli:hover{box-shadow:0 8px 30px rgba(16,185,129,.16),0 2px 8px rgba(0,0,0,.2);border-color:rgba(16,185,129,.26);}
.doc-tile.htl:hover{box-shadow:0 8px 30px rgba(255,108,55,.18),0 2px 8px rgba(0,0,0,.2);border-color:rgba(255,108,55,.28);}
.doc-tile.rem:hover{box-shadow:0 8px 30px rgba(245,158,11,.16),0 2px 8px rgba(0,0,0,.2);border-color:rgba(245,158,11,.26);}
.doc-tile.usr:hover{box-shadow:0 8px 30px rgba(239,68,68,.16),0 2px 8px rgba(0,0,0,.2);border-color:rgba(239,68,68,.26);}
.tile-icon { width:44px; height:44px; display:flex; align-items:center; justify-content:center; color:var(--text); transition:transform .2s cubic-bezier(.34,1.56,.64,1),color .15s; }
.tile-icon svg { width:22px; height:22px; }
[data-theme="light"] .tile-name { color:var(--text-2); }
.doc-tile.cl:hover .icon-cl{color:var(--accent-2);} .doc-tile.inv:hover .icon-inv{color:var(--purple);}
.doc-tile.svc:hover .icon-svc{color:var(--green);} .doc-tile.cal:hover .icon-cal{color:var(--yellow);}
.doc-tile.cli:hover .icon-cli{color:var(--green);} .doc-tile.htl:hover .icon-htl{color:var(--accent-2);}
.doc-tile.rem:hover .icon-rem{color:var(--yellow);} .doc-tile.usr:hover .icon-usr{color:var(--red);}
.tile-name { font-size:11px; font-weight:600; color:var(--text-2); text-align:center; line-height:1.3; letter-spacing:.1px; }
@media (max-width:600px){
  .panel-label { font-size:22px; letter-spacing:1.5px; top:calc(11.8vh - 34px); }
  .center-wrap { padding:8px 72px 100px; gap:12px; }
  .doc-grid { grid-template-columns:repeat(2,1fr); max-width:100%; gap:8px; }
  .doc-tile { padding:16px 8px; gap:8px; }
  .doc-tile:last-child:nth-child(3n+1) { grid-column:unset; }
  .doc-tile:last-child:nth-child(odd) { grid-column:1 / span 2; justify-self:center; width:calc(50% - 5px); }
}
@keyframes fabGlow { 0%,100%{box-shadow:0 4px 18px rgba(255,108,55,.35),0 2px 8px rgba(0,0,0,.3);} 50%{box-shadow:0 4px 26px rgba(255,108,55,.55),0 2px 8px rgba(0,0,0,.3);} }
.ai-fab { position:fixed; bottom:56px; right:24px; width:52px; height:52px; border-radius:50%; background:linear-gradient(135deg,var(--accent-2) 0%,var(--accent) 55%,#E04E1A 100%); border:none; cursor:pointer; display:flex; align-items:center; justify-content:center; animation:fabGlow 3.5s ease-in-out infinite; transition:transform .2s cubic-bezier(.34,1.56,.64,1); z-index:10; }
.ai-fab:hover { transform:scale(1.08) rotate(8deg); } .ai-fab:active { transform:scale(.93); }
.ai-fab svg { width:21px; height:21px; color:#fff; position:absolute; transition:opacity .18s,transform .25s cubic-bezier(.34,1.56,.64,1); }
.ai-fab .fab-ic-close { opacity:0; transform:rotate(-90deg) scale(.5); }
.ai-fab.open .fab-ic-spark { opacity:0; transform:rotate(90deg) scale(.5); }
.ai-fab.open .fab-ic-close { opacity:1; transform:rotate(0deg) scale(1); }
.ai-panel { position:fixed; bottom:120px; right:24px; width:340px; max-height:480px; background:var(--surface); border:1px solid var(--border-2); border-radius:16px; overflow:hidden; box-shadow:var(--shadow-xl),0 0 40px rgba(255,108,55,.07); display:flex; flex-direction:column; z-index:10; transform:translateY(16px) scale(.95); transform-origin:bottom right; opacity:0; pointer-events:none; transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .16s; }
.ai-panel.open { transform:translateY(0) scale(1); opacity:1; pointer-events:all; }
@media (max-width:640px){ .ai-fab{bottom:108px;right:16px;} .ai-panel{bottom:172px;right:16px;left:16px;width:auto;} }
.ai-panel-head { display:flex; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid var(--border); flex-shrink:0; }
.ai-head-icon { width:30px; height:30px; border-radius:var(--r-lg); background:var(--accent-muted); color:var(--accent-2); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ai-head-text { flex:1; min-width:0; }
.ai-panel-title { font-size:13px; font-weight:600; color:var(--text); line-height:1.2; }
.ai-panel-sub { font-size:11px; color:var(--text-3); line-height:1.3; }
.ai-panel-close { background:none; border:none; cursor:pointer; color:var(--text-3); padding:4px; display:flex; align-items:center; border-radius:var(--r); transition:color .12s,background .12s; }
.ai-panel-close:hover { color:var(--text); background:var(--surface-2); }
.chat-messages { flex:1; padding:12px; display:flex; flex-direction:column; gap:8px; overflow-y:auto; min-height:0; }
.chat-empty { margin:auto; display:flex; flex-direction:column; align-items:center; gap:6px; padding:18px 14px; text-align:center; }
.chat-empty-icon { width:38px; height:38px; border-radius:50%; background:var(--accent-muted); color:var(--accent-2); display:flex; align-items:center; justify-content:center; margin-bottom:2px; }
.chat-empty-title { font-size:13px; font-weight:600; color:var(--text); }
.chat-empty-sub { font-size:11.5px; color:var(--text-3); }
.chat-sugs { display:flex; flex-wrap:wrap; justify-content:center; gap:6px; margin-top:8px; }
.chat-sug { background:var(--surface-2); border:1px solid var(--border); border-radius:var(--r-full); padding:5px 11px; font-size:11.5px; font-weight:500; color:var(--text-2); cursor:pointer; transition:background .12s,color .12s,border-color .12s; }
.chat-sug:hover { background:var(--accent-muted); color:var(--accent-2); border-color:rgba(255,108,55,.3); }
@keyframes bubbleIn { from{opacity:0;transform:translateY(8px) scale(.96);} to{opacity:1;transform:translateY(0) scale(1);} }
.chat-bubble { padding:8px 12px; border-radius:var(--r-xl); font-size:13px; line-height:1.5; max-width:88%; word-break:break-word; animation:bubbleIn .22s cubic-bezier(.34,1.56,.64,1) both; }
.bubble-user { background:linear-gradient(135deg,rgba(255,140,90,.18),rgba(255,108,55,.14)); border:1px solid rgba(255,108,55,.22); color:var(--accent-2); align-self:flex-end; border-bottom-right-radius:4px; }
.bubble-ai { background:var(--surface-2); border:1px solid var(--border); color:var(--text); align-self:flex-start; border-bottom-left-radius:4px; }
.bubble-typing { display:flex; gap:4px; align-items:center; padding:10px 14px; }
.bubble-typing span { width:5px; height:5px; background:var(--text-3); border-radius:50%; animation:bounce 1.2s infinite; }
.bubble-typing span:nth-child(2){animation-delay:.2s;} .bubble-typing span:nth-child(3){animation-delay:.4s;}
@keyframes bounce { 0%,60%,100%{transform:translateY(0);} 30%{transform:translateY(-4px);} }
.chat-input-row { display:flex; align-items:center; border-top:1px solid var(--border); padding:10px 12px; gap:8px; flex-shrink:0; }
.chat-input-pill { flex:1; display:flex; align-items:center; background:var(--surface-2); border:1px solid var(--border); border-radius:var(--r-full); padding:0 14px; height:36px; transition:border-color .15s,box-shadow .15s; }
.chat-input-pill:focus-within { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-muted); }
.chat-input { flex:1; background:transparent; border:none; outline:none; box-shadow:none; font-size:13px; font-family:inherit; color:var(--text); height:100%; padding:0; border-radius:0; }
.chat-input::placeholder { color:var(--text-3); }
.chat-send { background:linear-gradient(135deg,var(--accent-2),var(--accent)); color:#fff; border:none; border-radius:50%; width:36px; height:36px; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:transform .15s cubic-bezier(.34,1.56,.64,1),opacity .15s,box-shadow .15s; flex-shrink:0; }
.chat-send:hover { transform:scale(1.08); box-shadow:0 2px 12px rgba(255,108,55,.4); }
.chat-send:active { transform:scale(.92); } .chat-send:disabled { opacity:.4; cursor:not-allowed; transform:none; box-shadow:none; }
.chat-send svg { width:14px; height:14px; }
.bubble-ai .ai-ul { margin:4px 0 2px 4px; padding-left:14px; display:flex; flex-direction:column; gap:3px; }
.bubble-ai .ai-ul li { font-size:13px; line-height:1.5; } .bubble-ai strong { font-weight:600; color:var(--text); }
.ai-card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin:3px 0; display:flex; flex-direction:column; gap:3px; }
.ai-card-head { display:flex; align-items:center; justify-content:space-between; gap:6px; }
.ai-card-num { font-family:'Courier New',monospace; font-size:11px; font-weight:700; color:var(--text); }
.ai-card-badge { font-size:10px; font-weight:600; padding:1px 7px; border-radius:9999px; flex-shrink:0; }
.ai-badge-green { background:var(--green-muted); color:var(--green); } .ai-badge-red { background:var(--red-muted); color:var(--red); }
.ai-card-name { font-size:12px; font-weight:500; color:var(--text); } .ai-card-meta { font-size:11px; color:var(--text-2); }
`;

// ── AI reply formatter (ported from home.html) ──
const esc = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
function makeCard(raw) {
  const p = raw.split("|").map((s) => s.trim());
  const [nomor = "", nama = "", total = "", sisa = "", status = ""] = p;
  const lunas = /^lunas$/i.test(status);
  return '<div class="ai-card"><div class="ai-card-head"><span class="ai-card-num">' + esc(nomor) +
    '</span><span class="ai-card-badge ' + (lunas ? "ai-badge-green" : "ai-badge-red") + '">' + esc(status) +
    '</span></div><div class="ai-card-name">' + esc(nama) + '</div><div class="ai-card-meta">' + esc(total) +
    " &middot; Sisa " + esc(sisa) + "</div></div>";
}
function formatAI(text) {
  const lines = String(text || "").split("\n");
  let html = "", inList = false;
  for (const line of lines) {
    const cardMatch = line.match(/\[inv:\s*([^\]]+)\]/);
    if (cardMatch) {
      if (inList) { html += "</ul>"; inList = false; }
      html += makeCard(cardMatch[1]);
    } else if (/^[-•]\s+/.test(line)) {
      if (!inList) { html += '<ul class="ai-ul">'; inList = true; }
      html += "<li>" + bold(esc(line.replace(/^[-•]\s+/, ""))) + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      const e = bold(esc(line));
      html += e ? "<span>" + e + "</span><br>" : "<br>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

const SPARK = <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />;

const TILES = [
  { key: "cl", href: "/cl/", name: <>Confirmation<br />Letter</>, path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" },
  { key: "inv", href: "/invoice/", name: <>Invoice<br />Hotel</>, path: "M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" },
  { key: "svc", href: "/services/", name: <>Invoice<br />Services</>, path: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" },
  { key: "cal", href: "/calendar/", name: <>Reservation<br />Calendar</>, path: "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" },
  { key: "cli", href: "/clients/", name: "Clients", path: "M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" },
  { key: "htl", href: "/hotels/", name: "Hotel", path: "M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M12 3.75h.008v.008H12V3.75z" },
];

function Tile({ t }) {
  return (
    <a href={t.href} className={`doc-tile ${t.key}`}>
      <div className={`tile-icon icon-${t.key}`}>
        <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d={t.path} /></svg>
      </div>
      <span className="tile-name">{t.name}</span>
    </a>
  );
}

export default function Home() {
  const { props } = usePage();
  const user = props.auth?.user;
  const company = props.active_company;
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState("");
  const inputRef = useRef(null);
  const msgRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 180); }, [open]);
  useEffect(() => { if (msgRef.current) msgRef.current.scrollTop = msgRef.current.scrollHeight; }, [messages, typing]);

  const send = async (preset) => {
    const text = (preset ?? input).trim();
    if (!text || typing) return;
    setInput("");
    setMessages((m) => [...m, { type: "user", text }]);
    setTyping(true);
    try {
      const data = await fetchJson("/ai/chat/", { method: "POST", json: { message: text } });
      setMessages((m) => [...m, { type: "ai", html: formatAI(data.reply) }]);
    } catch {
      setMessages((m) => [...m, { type: "ai", html: formatAI("Failed to connect to server.") }]);
    } finally {
      setTyping(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="home-root">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      <div className="center-wrap">
        <span className="panel-label">Learn. Build. Iterate.</span>
        <div className="doc-grid">
          {TILES.map((t) => <Tile key={t.key} t={t} />)}
          {company === "konoz" && <Tile t={{ key: "rem", href: "/remittance/", name: "Remittance", path: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" }} />}
          {user?.is_superuser && <Tile t={{ key: "usr", href: "/users/", name: <>Manage<br />Users</>, path: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" }} />}
        </div>
      </div>

      <button className={"ai-fab" + (open ? " open" : "")} title="Ask AI" onClick={() => setOpen((v) => !v)}>
        <svg className="fab-ic-spark" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg>
        <svg className="fab-ic-close" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
      </button>

      <div className={"ai-panel" + (open ? " open" : "")}>
        <div className="ai-panel-head">
          <div className="ai-head-icon"><svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg></div>
          <div className="ai-head-text">
            <div className="ai-panel-title">Ask AI</div>
            <div className="ai-panel-sub">Jawaban instan dari data Anda</div>
          </div>
          <button className="ai-panel-close" onClick={() => setOpen(false)}>
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="chat-messages" ref={msgRef}>
          {messages.length === 0 && !typing && (
            <div className="chat-empty">
              <div className="chat-empty-icon"><svg width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg></div>
              <div className="chat-empty-title">Tanya apa saja</div>
              <div className="chat-empty-sub">Invoice, reservasi, atau klien — dijawab dari data Anda</div>
              <div className="chat-sugs">
                {["Invoice belum lunas", "Reservasi bulan ini", "Total outstanding"].map((s) => (
                  <button key={s} type="button" className="chat-sug" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.type === "user"
              ? <div key={i} className="chat-bubble bubble-user">{m.text}</div>
              : <div key={i} className="chat-bubble bubble-ai" dangerouslySetInnerHTML={{ __html: m.html }} />
          ))}
          {typing && <div className="chat-bubble bubble-ai bubble-typing"><span></span><span></span><span></span></div>}
        </div>
        <div className="chat-input-row">
          <div className="chat-input-pill">
            <input ref={inputRef} type="text" className="chat-input" placeholder="Ask about your data…" autoComplete="off"
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
          </div>
          <button className="chat-send" title="Send" disabled={typing} onClick={() => send()}>
            <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" /></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
