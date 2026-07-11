'use client'
import { useEffect, useRef } from 'react'

// Rue Personal — redesigned welcome BODY (everything below the painterly hero).
// Faithful port of personal_welcome_body_mockup_v9.html. The painterly hero
// (components/landing/Hero.js) renders ABOVE this, untouched.
//
// CSS + markup are injected scoped under `.jpw-root` so nothing leaks to other
// routes. The imperative bits (ASCII logo, memory stepper, study flow, voice,
// waveform) run in a single effect with rAF loops that:
//   - respect prefers-reduced-motion (render a static frame instead), and
//   - pause when their canvas is off-screen (IntersectionObserver).
// CTA buttons (.jpw-cta) route to the same flow as the hero's BEGIN (onBegin).

const CSS = `
.jpw-root{
  --ivory:#F1EEE6;--paper:#FBFAF6;--ink:#1A1813;--muted:#6E6A60;--clay:#CC785C;--clay-deep:#A8543B;
  --peach:#F2E1D4;--sage:#E3EADF;--sky:#E1E8EE;--line:rgba(26,24,19,0.10);--night:#1d1a2e;
  --serif:var(--font-fraunces),Georgia,serif;--sans:var(--font-hanken),system-ui,sans-serif;
  --word:var(--font-sans),sans-serif;--mono:var(--font-jetbrains),monospace;
  background:var(--ivory);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;
  overflow-x:hidden;line-height:1.6;position:relative;
}
.jpw-root *{margin:0;padding:0;box-sizing:border-box}
.jpw-root .wrap{max-width:1080px;margin:0 auto;padding:0 32px}
.jpw-root .reveal{opacity:0;transform:translateY(22px);transition:opacity .9s ease,transform .9s ease}
.jpw-root .reveal.in{opacity:1;transform:none}
.jpw-root .hero{padding:70px 0;text-align:center}
.jpw-root .asciihero{position:relative;width:clamp(260px,38vw,420px);height:clamp(260px,38vw,420px);margin:0 auto 24px;cursor:crosshair}
.jpw-root .asciihero .glow{position:absolute;inset:8%;border-radius:50%;background:radial-gradient(circle,rgba(204,120,92,.22),rgba(204,120,92,.05) 55%,transparent 72%);filter:blur(26px);animation:jpwbreathe 5s ease-in-out infinite}
@keyframes jpwbreathe{0%,100%{transform:scale(.9);opacity:.7}50%{transform:scale(1.08);opacity:1}}
.jpw-root .asciihero canvas{position:absolute;inset:0;width:100%;height:100%}
.jpw-root .eyebrow{display:inline-block;font-weight:600;font-size:13px;letter-spacing:.05em;color:var(--clay-deep);background:var(--peach);padding:7px 16px;border-radius:999px;margin-bottom:24px}
.jpw-root h1.display{font-family:var(--serif);font-weight:400;font-size:clamp(42px,6.2vw,82px);line-height:1.0;letter-spacing:-.02em;max-width:15ch;margin:0 auto}
.jpw-root h1.display em{font-style:italic;color:var(--clay)}
.jpw-root .herop{font-size:clamp(17px,2vw,21px);color:var(--muted);max-width:600px;margin:26px auto 34px;line-height:1.55}
.jpw-root .pill{font-family:var(--sans);font-weight:600;font-size:16px;padding:14px 28px;border-radius:999px;border:1px solid transparent;cursor:pointer;text-decoration:none;transition:.25s;display:inline-flex;align-items:center;gap:9px}
.jpw-root .pill.solid{background:var(--ink);color:var(--ivory)}
.jpw-root .pill.solid:hover{background:#332f27;transform:translateY(-2px)}
.jpw-root .pill svg{width:18px;height:18px}
.jpw-root .sec{padding:84px 0;border-top:1px solid var(--line)}
.jpw-root .lab{font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--clay-deep);margin-bottom:14px}
.jpw-root .sec h2{font-family:var(--serif);font-weight:400;font-size:clamp(30px,4.2vw,52px);line-height:1.06;letter-spacing:-.015em;margin-bottom:14px;max-width:20ch}
.jpw-root .sec .intro{font-size:18px;color:var(--muted);max-width:56ch;margin-bottom:36px;line-height:1.6}
.jpw-root .demo{background:var(--paper);border:1px solid var(--line);border-radius:24px;padding:28px;position:relative;overflow:hidden}
.jpw-root .modeswitch{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:4px;margin-bottom:22px;background:var(--ivory)}
.jpw-root .modeswitch button{font-family:var(--sans);font-weight:600;font-size:13px;padding:9px 18px;border:none;border-radius:999px;background:transparent;color:var(--muted);cursor:pointer;transition:.2s}
.jpw-root .modeswitch button.on{background:var(--ink);color:var(--ivory)}
.jpw-root .days{display:flex;gap:8px;margin-bottom:22px;flex-wrap:wrap}
.jpw-root .day{font-family:var(--mono);font-size:12px;padding:8px 14px;border:1px solid var(--line);border-radius:10px;cursor:pointer;color:var(--muted);background:var(--ivory);transition:.2s}
.jpw-root .day.on{border-color:var(--clay);color:var(--clay-deep);background:var(--peach)}
.jpw-root .chat{min-height:150px}
.jpw-root .bub{max-width:80%;padding:13px 17px;border-radius:16px;margin-bottom:12px;font-size:15px;line-height:1.5}
.jpw-root .bub.you{background:var(--ink);color:var(--ivory);margin-left:auto;border-bottom-right-radius:5px}
.jpw-root .bub.jv{background:var(--peach);color:#46342b;border-bottom-left-radius:5px}
.jpw-root .bub.jv.cold{background:#ece9e2;color:var(--muted)}
.jpw-root .bub .em{color:var(--clay-deep);font-weight:600}
.jpw-root .note{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:8px}
.jpw-root .insights{display:flex;flex-direction:column;gap:12px;margin-top:8px}
.jpw-root .ins{display:flex;gap:14px;align-items:flex-start;padding:16px 18px;border:1px solid var(--line);border-radius:14px;background:var(--ivory);opacity:0;transform:translateX(-12px);transition:.6s}
.jpw-root .ins.show{opacity:1;transform:none}
.jpw-root .ins .d{width:8px;height:8px;border-radius:50%;background:var(--clay);margin-top:8px;flex-shrink:0}
.jpw-root .ins p{font-size:15px;color:var(--ink)}
.jpw-root .ins p b{color:var(--clay-deep)}
.jpw-root .noteform{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.jpw-root .noteform input{flex:1;min-width:220px;font-family:var(--sans);font-size:15px;padding:13px 16px;border:1px solid var(--line);border-radius:12px;background:var(--ivory);color:var(--ink);outline:none}
.jpw-root .noteform input:focus{border-color:var(--clay)}
.jpw-root .chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.jpw-root .chip{font-size:13px;padding:7px 13px;border:1px solid var(--line);border-radius:999px;cursor:pointer;color:var(--muted);background:var(--ivory)}
.jpw-root .chip:hover{border-color:var(--clay);color:var(--clay-deep)}
.jpw-root .parsed{font-size:15px;color:var(--ink);min-height:24px}
.jpw-root .notif{position:relative;margin-top:18px;max-width:380px;background:var(--ink);color:var(--ivory);border-radius:16px;padding:14px 16px;display:flex;gap:12px;align-items:center;opacity:0;transform:translateY(14px);transition:.5s}
.jpw-root .notif.show{opacity:1;transform:none}
.jpw-root .notif .ic{width:34px;height:34px;border-radius:9px;background:var(--clay);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-family:var(--word);font-weight:900;font-size:15px;color:#fff}
.jpw-root .notif .t1{font-weight:600;font-size:13px}
.jpw-root .notif .t2{font-size:13px;color:rgba(241,238,230,.7)}
.jpw-root .flowgrid{display:grid;grid-template-columns:1.05fr .95fr;gap:26px}
.jpw-root .photo{position:relative;background:#fff;border-radius:10px;box-shadow:0 14px 34px rgba(0,0,0,.18);padding:22px 22px 26px;transform:rotate(-1.6deg);border:1px solid var(--line);overflow:hidden}
.jpw-root .photo h5{font-family:var(--serif);font-size:21px;margin-bottom:12px;color:#222}
.jpw-root .photo .ln{height:8px;background:rgba(26,24,19,.13);border-radius:4px;margin:9px 0}
.jpw-root .photo .ln.s{width:70%}
.jpw-root .photo .eq{font-family:var(--mono);font-size:13px;margin-top:14px;color:#333}
.jpw-root .photo .scan{position:absolute;left:0;right:0;height:40px;background:linear-gradient(rgba(204,120,92,0),rgba(204,120,92,.55),rgba(204,120,92,0));top:-44px;opacity:0}
.jpw-root .photo.scanning .scan{animation:jpwscan 1.5s ease-in-out forwards}
@keyframes jpwscan{0%{top:-44px;opacity:1}100%{top:104%;opacity:1}}
.jpw-root .capbtnrow{margin-top:18px}
.jpw-root .steps{margin-top:16px;font-family:var(--mono);font-size:12.5px;color:var(--muted);min-height:74px}
.jpw-root .steps .s{opacity:0;transform:translateX(-8px);transition:.4s;margin:7px 0;display:flex;gap:8px;align-items:center}
.jpw-root .steps .s.show{opacity:1;transform:none}
.jpw-root .steps .s b{color:var(--clay-deep)}
.jpw-root .foldhead{font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:14px}
.jpw-root .folder{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;margin-bottom:10px;background:var(--ivory);transition:.4s}
.jpw-root .folder.hot{border-color:var(--clay);background:var(--peach);transform:scale(1.02)}
.jpw-root .folder .fi{width:30px;height:30px;border-radius:8px;background:var(--paper);display:flex;align-items:center;justify-content:center}
.jpw-root .folder .fi svg{width:17px;height:17px}
.jpw-root .folder .fn{font-weight:600;font-size:14px}
.jpw-root .folder .fc{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--muted)}
.jpw-root .notecard{margin-top:16px;border:1px solid var(--line);border-radius:14px;background:#fff;padding:18px;opacity:0;max-height:0;overflow:hidden;transition:.7s}
.jpw-root .notecard.show{opacity:1;max-height:360px}
.jpw-root .notecard .nh{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.jpw-root .notecard .nt{font-family:var(--serif);font-size:19px}
.jpw-root .notecard .tools{display:flex;gap:10px;color:var(--clay-deep)}
.jpw-root .notecard .tools svg{width:18px;height:18px;cursor:pointer}
.jpw-root .notecard .ntopic{font-family:var(--mono);font-size:11px;color:var(--clay-deep);background:var(--peach);padding:3px 9px;border-radius:999px;display:inline-block;margin-bottom:9px}
.jpw-root .notecard p{font-size:14px;color:#2a2722;line-height:1.65}
.jpw-root .extras{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px}
.jpw-root .ex{border:1px solid var(--line);border-radius:14px;padding:20px;background:var(--ivory)}
.jpw-root .ex svg{width:22px;height:22px;margin-bottom:10px;color:var(--clay-deep)}
.jpw-root .ex h5{font-family:var(--serif);font-size:16px;margin-bottom:6px}
.jpw-root .ex p{font-size:13px;color:var(--muted);line-height:1.55}
.jpw-root .voicecard{display:flex;gap:24px;align-items:center;flex-wrap:wrap}
.jpw-root .voicecard canvas{width:320px;height:90px;max-width:100%}
.jpw-root .playbtn{font-family:var(--sans);font-weight:600;font-size:15px;padding:13px 22px;border-radius:999px;background:var(--clay);color:#fff;border:none;cursor:pointer;transition:.2s;display:inline-flex;align-items:center;gap:9px}
.jpw-root .playbtn:hover{background:var(--clay-deep)}
.jpw-root .playbtn svg{width:16px;height:16px}
.jpw-root .vtags{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.jpw-root .vtag{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:5px 11px}
.jpw-root .cta{margin:0 32px;border-radius:32px;background:var(--peach);padding:90px 32px;text-align:center}
.jpw-root .cta h2{font-family:var(--serif);font-weight:400;font-size:clamp(34px,5vw,62px);line-height:1.04;letter-spacing:-.02em;margin:0 auto 14px}
.jpw-root .cta h2 em{font-style:italic;color:var(--clay-deep)}
.jpw-root .cta p{font-size:18px;color:var(--muted);margin-bottom:30px}
.jpw-root .signoff{padding:104px 0 84px;text-align:center}
.jpw-root .signoff .lockup{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:28px}
.jpw-root .signoff .dot{width:40px;height:40px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center}
.jpw-root .signoff .dot img{width:74%;height:74%;object-fit:contain}
.jpw-root .signoff .jl{font-family:var(--serif);font-style:italic;font-size:22px;color:var(--muted)}
.jpw-root .megabrand{font-family:var(--word);font-weight:900;font-size:clamp(64px,14vw,190px);line-height:.9;letter-spacing:-.05em;color:var(--ink)}
.jpw-root .megabrand sup{font-size:.18em;vertical-align:super;font-weight:400;color:var(--muted)}
.jpw-root .megabrand .amp{color:var(--clay)}
.jpw-root .signoff .tech{font-weight:600;letter-spacing:.3em;font-size:13px;color:var(--muted);text-transform:uppercase;margin-top:24px;padding-left:.3em}
.jpw-root .signoff .foot{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:34px}
.jpw-root .signoff .foot span{margin:0 10px;color:var(--clay)}
@media(prefers-reduced-motion:reduce){
  .jpw-root .asciihero .glow{animation:none}
  .jpw-root .reveal{opacity:1;transform:none;transition:none}
}
@media(max-width:780px){.jpw-root .flowgrid,.jpw-root .extras{grid-template-columns:1fr}}
`

const BODY_HTML = `
<section class="hero"><div class="wrap">
  <div class="asciihero reveal"><div class="glow"></div><canvas class="alogo"></canvas></div>
  <span class="eyebrow reveal">Rue &middot; Personal</span>
  <h1 class="display reveal">This is not<br>another <em>chatbot</em>.</h1>
  <p class="herop reveal">Every other AI forgets you the moment you close the tab. Rue is one continuous relationship that <b>remembers, learns you, and acts</b> — for real. Try it below. ↓</p>
  <a class="pill solid reveal jpw-cta" href="#">Meet Rue</a>
</div></section>

<section class="sec"><div class="wrap reveal">
  <div class="lab">// one continuous memory</div>
  <h2>It never forgets. Like texting a friend who actually remembers.</h2>
  <p class="intro">Other AIs start every chat from zero. Rue is <em>one</em> conversation that compounds — day after day. Walk through a week and watch the difference.</p>
  <div class="demo"><div class="modeswitch"><button data-m="other">A normal AI</button><button data-m="jarvis" class="on">Rue</button></div>
  <div class="days" id="days"></div><div class="chat" id="chat"></div><div class="note" id="mnote"></div></div>
</div></section>

<section class="sec"><div class="wrap reveal">
  <div class="lab">// it learns you</div>
  <h2>It doesn't just store facts. It studies your patterns.</h2>
  <p class="intro">Rue quietly notices how you actually work and feel — then adapts. Let it watch a week and see what it picks up.</p>
  <div class="demo"><button class="pill solid" id="watchbtn" style="margin-bottom:18px">Let Rue watch a week →</button><div class="insights" id="insights"></div></div>
</div></section>

<section class="sec"><div class="wrap reveal">
  <div class="lab">// study mode</div>
  <h2>Snap it once. Forget it. Rue turns it into organized notes.</h2>
  <p class="intro">That photo of the whiteboard rotting in your camera roll? Capture any study material in Rue and forget it — it reads the page, writes it up as a real note you can edit, detects the subject, and files it into the right folder for you. You never drown in scattered screenshots again.</p>
  <div class="demo"><div class="flowgrid">
    <div>
      <div class="photo" id="photo"><div class="scan"></div><h5>Photosynthesis</h5><div class="ln"></div><div class="ln"></div><div class="ln s"></div><div class="eq">6CO&#8322; + 6H&#8322;O &#8594; C&#8326;H&#8321;&#8322;O&#8326; + 6O&#8322;</div><div class="ln" style="margin-top:14px"></div><div class="ln s"></div></div>
      <div class="capbtnrow"><button class="pill solid" id="capbtn"><svg viewBox="0 0 24 24" fill="none"><path d="M3 8a2 2 0 012-2h2l1.5-2h7L17 6h2a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12.5" r="3.2" stroke="currentColor" stroke-width="1.6"/></svg> Capture study material</button></div>
      <div class="steps" id="steps"></div>
      <div class="notecard" id="notecard"><div class="nh"><div class="nt">Photosynthesis</div><div class="tools">
        <svg viewBox="0 0 24 24" fill="none"><path d="M4 20h4L20 8l-4-4L4 16v4z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
        <svg viewBox="0 0 24 24" fill="none"><path d="M3 17l6-6 4 4 8-8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <svg viewBox="0 0 24 24" fill="none"><path d="M21 12l-9 9a5 5 0 01-7-7l9-9a3.5 3.5 0 015 5l-9 9a2 2 0 01-3-3l8-8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      </div></div><span class="ntopic">Biology · auto-sorted</span><p>Plants convert sunlight, water and CO&#8322; into glucose and oxygen, inside the chloroplasts. Two stages: the light-dependent reactions, then the Calvin cycle. <span style="color:var(--clay-deep)">[source: your photo, p.1]</span></p></div>
    </div>
    <div>
      <div class="foldhead">Your notes — auto-organized</div>
      <div class="folder" data-f="Calculus"><span class="fi"><svg viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" stroke="#A8543B" stroke-width="1.5"/></svg></span><span class="fn">Calculus</span><span class="fc">5 notes</span></div>
      <div class="folder" data-f="Biology" id="folderBio"><span class="fi"><svg viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" stroke="#A8543B" stroke-width="1.5"/></svg></span><span class="fn">Biology</span><span class="fc" id="bioCount">2 notes</span></div>
      <div class="folder" data-f="History"><span class="fi"><svg viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" stroke="#A8543B" stroke-width="1.5"/></svg></span><span class="fn">History</span><span class="fc">3 notes</span></div>
      <p style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:14px;line-height:1.6">Capture three of these and Rue builds the whole folder tree itself — no filing, no chaos.</p>
    </div>
  </div>
  <div class="extras">
    <div class="ex"><svg viewBox="0 0 24 24" fill="none"><path d="M4 20h4L20 8l-4-4L4 16v4z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg><h5>Edit &amp; annotate</h5><p>Every note is yours to rewrite, draw on, and attach files to.</p></div>
    <div class="ex"><svg viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2z" stroke="currentColor" stroke-width="1.6"/></svg><h5>Sorts itself by topic</h5><p>Math, science, English — detected and filed into the right folder, automatically.</p></div>
    <div class="ex"><svg viewBox="0 0 24 24" fill="none"><path d="M12 4L2 9l10 5 10-5-10-5z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M6 11v4c0 1 2.5 2.5 6 2.5s6-1.5 6-2.5v-4" stroke="currentColor" stroke-width="1.6"/></svg><h5>Quizzes &amp; a tutor</h5><p>It teaches like your favorite teacher, never says "I can't," and cites every source.</p></div>
  </div>
  </div>
</div></section>

<section class="sec"><div class="wrap reveal">
  <div class="lab">// a real, emotional voice</div>
  <h2>It doesn't read to you. It talks to you.</h2>
  <p class="intro">A warm, human voice with actual tone — wry, calm, encouraging. This is Rue's real voice. Press play (and pause whenever you like).</p>
  <div class="demo"><div class="voicecard"><canvas id="wave"></canvas>
    <div><audio id="jaudio" src="/jarvis-voice.mp3" preload="auto"></audio>
    <button class="playbtn" id="playbtn"><svg id="playicon" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg><span id="playlabel">Hear Rue</span></button>
    <div class="vtags"><span class="vtag">warm</span><span class="vtag">wry</span><span class="vtag">calm</span><span class="vtag">knows you</span></div></div>
  </div></div>
</div></section>

<div class="cta reveal"><h2>Not a tool.<br>A <em>presence</em>.</h2><p>The first AI that's actually yours.</p><a class="pill solid jpw-cta" href="#">Begin with Rue</a></div>
<div class="signoff"><div class="lockup"><span class="dot"><img src="/jarvis-logo-mono.png" alt="Rue"></span><span class="jl">Rue</span></div><div class="megabrand">MG<span class="amp">&amp;</span>CO<sup>&#8482;</sup></div><div class="tech">Technologies Inc.</div><div class="foot">mgcotechnologies.com <span>&middot;</span> Based in Toronto, Canada <span>&middot;</span> &copy; 2026 MG&amp;CO Technologies Inc.</div></div>
`

const MASK = ["0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000012456410000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000013689999960000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000001589999999981000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000003999999999996210000000000000000000000000000000000000000000000000000","0000000000000000000000000000000001359999999999996100000000000000000000000000000000000000000000000000","0000000000000000000000000000000000005999999999999500000000000463000000000000000000000000000000000000","0000000000000000000000000000266200003999999999999600000000000899200000000000000000000000000000000000","0000000000000000000000000026899832348999999999999810000000000387200000000000000000000000000000000000","0000000000000000000000000499999999999999999999999961000000000000000001000000000000000000000000000000","0000000000000000000000000477899999999999999999999998410001342000000188200000000000000000000000000000","0000000000000000000000000000146742699999999999999999997568999710000179400000000000000000000000000000","0000000000000000000000000000000000599999999999999999999999999983111002000320000000000000000000000000","0000000000000000000100000000000000799999999999999999999999999999888730003997300000000000000000000000","0000000000000000005872000000000000389999999999999999999999999999999996411899950000000000000000000000","0000000000000000059997212100000000001358999999999999999999999999999999984899996100000000000000000000","0000000000000000399999999830000000000001489999999999999999999999999999999999999710000000000000000000","0000000000000002899999999981000000000000039999999999999999999999999999999999999982000000000000000000","0000000000000017999999999997300000000000179999999999999999999999999999999999999998200000000000000000","0000000000000059999999999999940000000000499999999999999999999999999999999999999999710000000000000000","0000000000000399999999999999940000000000188349999999999999999999999999999999999999960000000000000000","0000000000000798547999999999600000000000011006999999999999999999999999999999999999995000000000000000","0000000000004982000699999999200000000000000002999999999999999999999999999999999999999200000000000000","0000000000018930000189999999200000000000000002999999999999999999999999999999999999999700000000000000","0000000000059500000049999999400000000000000005999999999999999999999999999999999999999940000000000000","0000000000188100000029999999300000000000000059999999999999999999999999999999999999999981000000000000","0000000000493000000007999995000000000000000599999999999999999999999999999999999999999995000000000000","0000000000880000000002899981000000000000000899999999999999999999999999999999999999997898000000000000","0000000003940000000000299993000000002651004999999999999999999999999999999999999999970179300000000000","0000000006810000000000079997000000006998679999999999999999999999999999999999999999981017400000000000","0000000019600000000012389997000000007999999999999999999999999999999999999999999999996000000000000000","0000000049300000000079999994000000039999999999899999999999999999999999999999999999999100000000000000","0000000068100000000089999981000005899999999973159999999999999999999999999999999999999200000000000000","0000000186000000000038999993000029999999953200019999999999999999999999999999999999999600000000000000","0000000294000000000001489998100049999999300000019999999999999999999999999999999999999962000000000000","0000000492000000000000017999842489965784000000004799999999999999999999999999999999999999300000000000","0000000681000000000000001899999999300000000000000059999999999999999999999999999999999999700000000000","0000000880000000000000000599999996000000000000000018999999999999999999999999999999999999800000000000","0000001970000000000000000289999993000000000000000018999999999999999999999999999999999999920000000000","0000002980000000000000000039999992000000000000000049999999972357999999999999999999999999982000000000","0000003992000000000000000003799993000000000000000059999999984000379999999999999999999999999200000000","0000003997000000000000000000158996000000000000000029999999999400015999999999999999999999999500000000","0000004999600000000000000000002799200000000000000003799999999920000599999999999999999998999500000000","0000004999940000000000000000000179820000000000000000025899999940000179999999999999999930266100000000","0000004999970000000000000000000017984000000000000000000289999950000013589999999999999800000000000000","0000004999960000000000000000000001899610000000000000000049999950000000029999999999999920000000000000","0000003999930000000000000000000000399971000000000000000019999970000000003899999999999982000000000000","0000003999930000000000000000000000049996000000000000000007999996000000000038999999999999654100000000","0000002999970000000000000000000000004999720000000000000002899999610000000003999999999999999820000000","0000001899996100000000000000000000000269996300000000000000255589940000000001899999999999999960000000","0000000899999840000000000000000000000002577500000000000000000017970000000004999999999999999980000000","0000000699999995000000000000000000000000000000035300000000000003994000000018999999999999999981000000","0000000599999999200000000000000000000000000000069940000000000000699620000029999999999976799970000000","0000000399999999200000000000000000000000000000003310000000000000026996000007999999999300039970000000","0000000189999995000000000000000000000000000000000000000000000000000799500005999999995000005950000000","0000000069999960000000000000000000000000000000000000000000000000000399810018999999850000002940000000","0000000039999950000000000000000000000000000000000000000000000000000399973379999995100000002920000000","0000000018999971000000000000000000000000000000000000000000000000000399999999999980000000005800000000","0000000005999997100000000000000000000000000000000000000000000000000179999999999960000000049600000000","0000000002999999200000000000000000000000000000000000000000000000000027999999999981000000399300000000","0000000000699998100000000000000000000000000000000000000000000000000000799974479996100000698100000000","0000000000299971000000000000000000000015630000000000000000000000000000299710017999710000595000000000","0000000000069950000000000020000000000069993000000000000000000000000000199400004999930000492000000000","0000000000029981000000001797200000000069998000000000000000000000000000499300003999920000770000000000","0000000000005994000000003999820000000028999600000000000000000000000000697100001899950004920000000000","0000000000001898100000001899960000000002799974100000000000000000000000793000000399997569600000000000","0000000000000399600000000279995000000000499999710000000000000000000003992000000025999999200000000000","0000000000000059961000000005999740000001799999950000000000000000000148970000000000599995000000000000","0000000000000007997300000000599994003888999999995100000000134100002899610000000000299970000000000000","0000000000000002899972000000189998128999999999999877500001799940008994000000000000189920000000000000","0000000000000000399998100000089999889999999999999999962017999993019980000001330000037300000000000000","0000000000000000049999400000069999999999999999999999999889999996008981000028996000000000000000000000","0000000000000000004999600000017999999999999999999999999999999998328996211489999751000000000000000000","0000000000000000000499820000001599999999999999999999999999999999999999988999999995000000000000000000","0000000000000000000049982000000069999999999999999974589999999999999999999999999992000000000000000000","0000000000000000000003999610000018999999999999999600014899999999999999999999999940000000000000000000","0000000000000000000000389981000001579999999999999300000289999999999999999999999300000000000000000000","0000000000000000000000027996000000002799999999998100000025689999999999999999982000000000000000000000","0000000000000000000000001599510000000189999998552000000000028999999999999999610000000000000000000000","0000000000000000000000000038983000000038999992000000000000007999999999999984000000000000000000000000","0000000000000000000000000001599620000002699980000000000000049999999999999620000000000000000000000000","0000000000000000000000000000026996200000079993000000000005899999999999973000000000000000000000000000","0000000000000000000000000000000269973100059999410000000029999999999997300000000000000000000000000000","0000000000000000000000000000000002589863489999986100000005658999998520000000000000000000000000000000","0000000000000000000000000000000000013699999999999700000000002998631000000000000000000000000000000000","0000000000000000000000000000000000000013578999999950000000000231000000000000000000000000000000000000","0000000000000000000000000000000000000000001234556630000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"]

const MEM = {
  days: ["Mon", "Tue", "Wed", "Thu", "Fri"],
  jarvis: [
    { you: "Big launch Friday. Kinda scared no one shows up.", jv: "Noted — Friday's the launch, and the worry is turnout. Want me to start a reminder list so we fill the room?" },
    { you: "Had that investor pitch today. Went ok I think.", jv: "Good — that's the pitch you were dreading <span class='em'>yesterday</span>, off your plate. Three days to launch." },
    { you: "forgot to eat again lol", jv: "You said that <span class='em'>Monday</span> too. I'll nudge you at 1pm from now on. And the launch is in 2 days — still good?" },
    { you: "can't sleep", jv: "Night before the night before. It's the turnout, isn't it — <span class='em'>same worry as Monday</span>. I already drafted the reminders. Send them at 9am?" },
    { you: "it's today.", jv: "Launch day. Reminders went out at 9 — <span class='em'>41 people RSVP'd</span>, way more than you feared Monday. Go. I've got the follow-ups ready." },
  ],
  other: [
    { you: "Big launch Friday. Kinda scared no one shows up.", jv: "Hi! I can help. Here are 5 general tips for a product launch...", cold: 1 },
    { you: "Had that investor pitch today. Went ok I think.", jv: "Hello! How can I help you today? Tell me more about the pitch?", cold: 1 },
    { you: "forgot to eat again lol", jv: "Hi there! Remember to eat regular meals. How can I assist?", cold: 1 },
    { you: "can't sleep", jv: "Hello! Here are some general tips for better sleep hygiene...", cold: 1 },
    { you: "it's today.", jv: "Hi! What's today? Happy to help with more context.", cold: 1 },
  ],
}

const INS = [
  "You think clearest <b>after 10pm</b> — I save the heavy decisions for then.",
  "<b>Mondays</b> drain you. I keep them light and quiet.",
  "When you go deep on work, <b>you forget to eat</b>. I nudge you now.",
  "You commit faster when I show you <b>one option, not five</b>.",
  "You say \"lol\" when you're actually <b>stressed</b>. I read past it.",
]

export function WelcomeBody({ onBegin }) {
  const rootRef = useRef(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const $ = (sel) => root.querySelector(sel)
    const cleanups = []
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // ---- ASCII breathing planet (real logo, baked MASK) ----
    function asciiLogo(c) {
      const x = c.getContext('2d')
      const CW = 5, CH = 7, fs = 8
      const ramp = " .:-=+*oxOX#%@".split("")
      let W, H, cols, rows, t = Math.random() * 9, mx = -999, my = -999
      function sz() {
        const r = c.getBoundingClientRect()
        W = c.width = Math.max(1, r.width)
        H = c.height = Math.max(1, r.height)
        cols = Math.ceil(W / CW); rows = Math.ceil(H / CH)
      }
      sz()
      function frame() {
        x.clearRect(0, 0, W, H)
        x.font = fs + "px monospace"; x.textBaseline = 'top'
        const p = 0.84 + 0.16 * Math.sin(t * 1.4), sc = 1 + 0.04 * Math.sin(t * 1.4)
        for (let gy = 0; gy < rows; gy++) for (let gx = 0; gx < cols; gx++) {
          const u = ((gx + 0.5) / cols - 0.5) / sc + 0.5, v = ((gy + 0.5) / rows - 0.5) / sc + 0.5
          if (u < 0 || u >= 1 || v < 0 || v >= 1) continue
          let b = (MASK[Math.floor(v * 100)].charCodeAt(Math.floor(u * 100)) - 48) / 9
          if (b <= 0.02) continue
          b = b * p + 0.10 * Math.sin((gx * 0.5 + gy * 0.4) - t * 2.0)
          const px = gx * CW, py = gy * CH
          if (mx > -900) { const dx = px - mx, dy = py - my, d = Math.sqrt(dx * dx + dy * dy); if (d < 90) b += (1 - d / 90) * 0.6 }
          b = Math.max(0, Math.min(1, b))
          const ch = ramp[Math.floor(b * (ramp.length - 1))]
          if (ch === ' ') continue
          const r2 = Math.round(204 - b * 178), g2 = Math.round(120 - b * 96), bl = Math.round(92 - b * 73)
          x.fillStyle = 'rgba(' + r2 + ',' + g2 + ',' + bl + ',' + (0.22 + b * 0.74) + ')'
          x.fillText(ch, px, py)
        }
      }
      if (reduce) {
        // static logo (no animation, no cursor interaction)
        frame()
        const ro = new ResizeObserver(() => { sz(); frame() }); ro.observe(c)
        return () => ro.disconnect()
      }
      const ro = new ResizeObserver(sz); ro.observe(c)
      function onMove(e) { const r = c.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top }
      function onLeave() { mx = -999 }
      c.addEventListener('mousemove', onMove)
      c.addEventListener('mouseleave', onLeave)
      let rafId = null, running = true
      function f() { if (!running) { rafId = null; return } t += 0.018; frame(); rafId = requestAnimationFrame(f) }
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { running = e.isIntersecting; if (running && !rafId) rafId = requestAnimationFrame(f) })
      }, { threshold: 0 })
      io.observe(c)
      rafId = requestAnimationFrame(f)
      return () => {
        running = false; if (rafId) cancelAnimationFrame(rafId)
        io.disconnect(); ro.disconnect()
        c.removeEventListener('mousemove', onMove); c.removeEventListener('mouseleave', onLeave)
      }
    }

    // ---- one continuous memory (day stepper + mode toggle) ----
    let memMode = "jarvis", memDay = 4
    function renderMem() {
      const c = $('#chat'); if (!c) return
      const d = MEM[memMode][memDay]
      c.innerHTML = '<div class="bub you">' + d.you + '</div><div class="bub jv' + (d.cold ? ' cold' : '') + '">' + d.jv + '</div>'
      const mn = $('#mnote')
      if (mn) mn.textContent = memMode === 'jarvis'
        ? '↑ Rue carries Monday into Friday — one unbroken thread.'
        : '↑ A normal AI: every day is a stranger. No memory of Monday.'
    }
    function buildDays() {
      const d = $('#days'); if (!d) return
      d.innerHTML = ''
      MEM.days.forEach((n, i) => {
        const b = document.createElement('div')
        b.className = 'day' + (i === memDay ? ' on' : '')
        b.textContent = n
        b.onclick = () => { memDay = i; buildDays(); renderMem() }
        d.appendChild(b)
      })
    }
    root.querySelectorAll('.modeswitch button').forEach((b) => {
      b.onclick = () => {
        memMode = b.dataset.m
        root.querySelectorAll('.modeswitch button').forEach((z) => z.classList.remove('on'))
        b.classList.add('on'); renderMem()
      }
    })

    // ---- it learns you ----
    const watchbtn = $('#watchbtn')
    if (watchbtn) watchbtn.onclick = function () {
      this.disabled = true; this.textContent = "Watching… learning you"
      const box = $('#insights'); box.innerHTML = ''
      INS.forEach((t, i) => {
        const e = document.createElement('div'); e.className = 'ins'
        e.innerHTML = '<div class="d"></div><p>' + t + '</p>'
        box.appendChild(e)
        setTimeout(() => e.classList.add('show'), 500 + i * 700)
      })
      setTimeout(() => { watchbtn.textContent = "Rue knows you now ✓" }, 500 + INS.length * 700)
    }

    // ---- study flow ----
    const capbtn = $('#capbtn')
    if (capbtn) capbtn.onclick = function () {
      capbtn.disabled = true
      const photo = $('#photo'), steps = $('#steps'); steps.innerHTML = ''
      photo.classList.add('scanning')
      function step(txt, delay) {
        setTimeout(() => {
          const s = document.createElement('div'); s.className = 's'; s.innerHTML = txt
          steps.appendChild(s); setTimeout(() => s.classList.add('show'), 30)
        }, delay)
      }
      step('<b>Reading</b> the page… (OCR)', 300)
      step('Extracted <b>84 words</b> + 1 equation', 1500)
      step('Detected subject: <b>Biology · Photosynthesis</b>', 2300)
      setTimeout(() => { $('#notecard').classList.add('show') }, 2500)
      setTimeout(() => { $('#folderBio').classList.add('hot'); $('#bioCount').textContent = '3 notes' }, 3100)
      step('Filed into <b>📁 Biology</b> — quiz ready, want me to teach it?', 3300)
      setTimeout(() => { capbtn.disabled = false }, 4200)
    }

    // ---- voice (real audio, play/pause) ----
    let speaking = false
    const au = $('#jaudio'), pb = $('#playbtn'), pl = $('#playlabel'), pic = $('#playicon')
    const PLAY = '<path d="M8 5v14l11-7z"/>', PAUSE = '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>'
    if (pb && au) {
      pb.onclick = () => { if (au.paused) au.play(); else au.pause() }
      const onPlay = () => { speaking = true; pic.innerHTML = PAUSE; pl.textContent = 'Pause' }
      const onPause = () => { speaking = false; pic.innerHTML = PLAY; pl.textContent = 'Hear Rue' }
      au.addEventListener('play', onPlay)
      au.addEventListener('pause', onPause)
      au.addEventListener('ended', onPause)
      cleanups.push(() => {
        au.removeEventListener('play', onPlay)
        au.removeEventListener('pause', onPause)
        au.removeEventListener('ended', onPause)
        try { au.pause() } catch (e) {}
      })
    }

    // ---- waveform ----
    function drawWave() {
      const wave = $('#wave'); if (!wave) return null
      const wx = wave.getContext('2d')
      function size() { wave.width = wave.clientWidth || 320; wave.height = 90 }
      size()
      if (reduce) {
        wx.clearRect(0, 0, wave.width, 90); wx.strokeStyle = '#CC785C'; wx.lineWidth = 2; wx.beginPath()
        for (let i = 0; i < wave.width; i++) { const y = 45 + Math.sin(i * 0.055) * 4 * Math.sin(i * 0.012); i === 0 ? wx.moveTo(i, y) : wx.lineTo(i, y) }
        wx.stroke()
        const ro = new ResizeObserver(() => { size(); wx.clearRect(0, 0, wave.width, 90); wx.strokeStyle = '#CC785C'; wx.lineWidth = 2; wx.beginPath(); for (let i = 0; i < wave.width; i++) { const y = 45 + Math.sin(i * 0.055) * 4 * Math.sin(i * 0.012); i === 0 ? wx.moveTo(i, y) : wx.lineTo(i, y) } wx.stroke() })
        ro.observe(wave)
        return () => ro.disconnect()
      }
      let wt = 0, rafId = null, running = true
      function loop() {
        if (!running) { rafId = null; return }
        wt += 0.09; wx.clearRect(0, 0, wave.width, 90); wx.strokeStyle = '#CC785C'; wx.lineWidth = 2; wx.beginPath()
        for (let i = 0; i < wave.width; i++) {
          const amp = speaking ? (16 + 11 * Math.sin(wt * 2.3)) : 4
          const y = 45 + Math.sin(i * 0.055 + wt) * amp * Math.sin(i * 0.012)
          if (i === 0) wx.moveTo(i, y); else wx.lineTo(i, y)
        }
        wx.stroke(); rafId = requestAnimationFrame(loop)
      }
      const ro = new ResizeObserver(size); ro.observe(wave)
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { running = e.isIntersecting; if (running && !rafId) rafId = requestAnimationFrame(loop) })
      }, { threshold: 0 })
      io.observe(wave)
      rafId = requestAnimationFrame(loop)
      return () => { running = false; if (rafId) cancelAnimationFrame(rafId); io.disconnect(); ro.disconnect() }
    }

    // ---- init ----
    root.querySelectorAll('canvas.alogo').forEach((cv) => { const cl = asciiLogo(cv); if (cl) cleanups.push(cl) })
    buildDays(); renderMem()
    const waveCleanup = drawWave(); if (waveCleanup) cleanups.push(waveCleanup)

    // reveal-on-scroll
    if (!reduce) {
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } })
      }, { threshold: 0.15 })
      root.querySelectorAll('.reveal').forEach((el) => io.observe(el))
      cleanups.push(() => io.disconnect())
    } else {
      root.querySelectorAll('.reveal').forEach((el) => el.classList.add('in'))
    }

    // CTA → same flow as hero's BEGIN
    const ctaHandler = (e) => { e.preventDefault(); if (onBegin) onBegin() }
    const ctas = root.querySelectorAll('.jpw-cta')
    ctas.forEach((a) => a.addEventListener('click', ctaHandler))
    cleanups.push(() => ctas.forEach((a) => a.removeEventListener('click', ctaHandler)))

    return () => cleanups.forEach((fn) => { try { fn() } catch (e) {} })
  }, [onBegin])

  return (
    <div
      className="jpw-root"
      ref={rootRef}
      suppressHydrationWarning
    >
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div dangerouslySetInnerHTML={{ __html: BODY_HTML }} />
    </div>
  )
}
