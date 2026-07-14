"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { supabase } from "@/lib/supabase"
import { jarvisUserId, getOS1Status, startCheckout } from "@/lib/os1"
import { setJarvisMode } from "@/lib/userPreferences"
import { stashAuthNext, authRedirectBase } from "@/lib/authNext"

// Rue OS1 — redesigned Hermes / terminal / ASCII body, APPENDED below the existing
// (loved) hero + operator/connections/etc sections. RESTYLE ONLY: the three tier cards
// stay wired to the real checkout engine (onSelect → goCheckout → startCheckout / Stripe,
// not-logged-in → Google OAuth + os1_intent resume, already-entitled → /business/chat).
// Everything is scoped under `.os1h-root`; the wave field + scanline are contained to this
// body so the sections above are untouched. Canvas loops respect prefers-reduced-motion and
// pause off-screen via IntersectionObserver.

type PlanId = "pro" | "emperor" | "tailored"
interface HermesPlan {
  id: PlanId
  tier: string
  name: string
  promise: string
  monthly: string
  yearly: string
  perMonthly: string
  perYearly: string
  billedMonthly: string
  billedYearly: string
  talk?: boolean
  headFeature?: string
  features: { html: string }[]
  more: string
  cta: string
  primary?: boolean
  action: "checkout" | "contact"
  feat?: boolean
}

const PLANS: HermesPlan[] = [
  {
    id: "pro",
    tier: "[ tier 01 ]",
    name: "Pro",
    promise: "Your whole back office, run by one operator.",
    monthly: "$49",
    yearly: "$490",
    perMonthly: "/mo · CAD",
    perYearly: "/yr · CAD",
    billedMonthly: "billed monthly · 7-day trial",
    billedYearly: "billed annually · 2 months free",
    action: "checkout",
    cta: "Start 7-day trial →",
    features: [
      { html: "Talk by voice or text — it already knows your business" },
      { html: "2 autonomous Operator runs each month — goal to finished work" },
      { html: "Builds for you on command — landing pages, campaigns, copy" },
      { html: "Plugs into the apps you run — Gmail, Calendar, socials" },
      { html: "Your own CRM, 9 industry playbooks, post to 2 platforms" },
    ],
    more: "and a lot more inside",
  },
  {
    id: "emperor",
    tier: "[ tier 02 ]",
    name: "Emperor",
    promise: "Maximum power. Fully yours. High-capacity execution.",
    monthly: "$199",
    yearly: "$1,990",
    perMonthly: "/mo · CAD",
    perYearly: "/yr · CAD",
    billedMonthly: "billed monthly · 7-day trial",
    billedYearly: "billed annually · 2 months free",
    action: "checkout",
    cta: "Start 7-day trial →",
    primary: true,
    feat: true,
    headFeature: "everything in Pro, plus",
    features: [
      { html: "15 autonomous Operator runs each month" },
      { html: "5× the horsepower — it runs harder and longer for you" },
      { html: "<b>Rue Leads</b> — it hunts, scores &amp; hands you ready-to-close clients" },
      { html: "A CRM that’s 100% your brand — fully white-labeled" },
      { html: "Unlimited social + your own custom command center" },
    ],
    more: "and a lot more inside",
  },
  {
    id: "tailored",
    tier: "[ tier 03 ]",
    name: "Tailored",
    promise: "Rue, custom-built around how you operate.",
    monthly: "Let’s talk",
    yearly: "Let’s talk",
    perMonthly: "",
    perYearly: "",
    billedMonthly: "custom engagement",
    billedYearly: "custom engagement",
    talk: true,
    action: "contact",
    cta: "Talk to sales →",
    headFeature: "everything in Emperor, plus",
    features: [
      { html: "Custom workflows wired to your exact operation" },
      { html: "A dedicated onboarding &amp; support team" },
      { html: "Volume &amp; enterprise pricing" },
    ],
    more: "scoped to you",
  },
]

const MASK = ["0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000012456410000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000013689999960000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000001589999999981000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000003999999999996210000000000000000000000000000000000000000000000000000","0000000000000000000000000000000001359999999999996100000000000000000000000000000000000000000000000000","0000000000000000000000000000000000005999999999999500000000000463000000000000000000000000000000000000","0000000000000000000000000000266200003999999999999600000000000899200000000000000000000000000000000000","0000000000000000000000000026899832348999999999999810000000000387200000000000000000000000000000000000","0000000000000000000000000499999999999999999999999961000000000000000001000000000000000000000000000000","0000000000000000000000000477899999999999999999999998410001342000000188200000000000000000000000000000","0000000000000000000000000000146742699999999999999999997568999710000179400000000000000000000000000000","0000000000000000000000000000000000599999999999999999999999999983111002000320000000000000000000000000","0000000000000000000100000000000000799999999999999999999999999999888730003997300000000000000000000000","0000000000000000005872000000000000389999999999999999999999999999999996411899950000000000000000000000","0000000000000000059997212100000000001358999999999999999999999999999999984899996100000000000000000000","0000000000000000399999999830000000000001489999999999999999999999999999999999999710000000000000000000","0000000000000002899999999981000000000000039999999999999999999999999999999999999982000000000000000000","0000000000000017999999999997300000000000179999999999999999999999999999999999999998200000000000000000","0000000000000059999999999999940000000000499999999999999999999999999999999999999999710000000000000000","0000000000000399999999999999940000000000188349999999999999999999999999999999999999960000000000000000","0000000000000798547999999999600000000000011006999999999999999999999999999999999999995000000000000000","0000000000004982000699999999200000000000000002999999999999999999999999999999999999999200000000000000","0000000000018930000189999999200000000000000002999999999999999999999999999999999999999700000000000000","0000000000059500000049999999400000000000000005999999999999999999999999999999999999999940000000000000","0000000000188100000029999999300000000000000059999999999999999999999999999999999999999981000000000000","0000000000493000000007999995000000000000000599999999999999999999999999999999999999999995000000000000","0000000000880000000002899981000000000000000899999999999999999999999999999999999999997898000000000000","0000000003940000000000299993000000002651004999999999999999999999999999999999999999970179300000000000","0000000006810000000000079997000000006998679999999999999999999999999999999999999999981017400000000000","0000000019600000000012389997000000007999999999999999999999999999999999999999999999996000000000000000","0000000049300000000079999994000000039999999999899999999999999999999999999999999999999100000000000000","0000000068100000000089999981000005899999999973159999999999999999999999999999999999999200000000000000","0000000186000000000038999993000029999999953200019999999999999999999999999999999999999600000000000000","0000000294000000000001489998100049999999300000019999999999999999999999999999999999999962000000000000","0000000492000000000000017999842489965784000000004799999999999999999999999999999999999999300000000000","0000000681000000000000001899999999300000000000000059999999999999999999999999999999999999700000000000","0000000880000000000000000599999996000000000000000018999999999999999999999999999999999999800000000000","0000001970000000000000000289999993000000000000000018999999999999999999999999999999999999920000000000","0000002980000000000000000039999992000000000000000049999999972357999999999999999999999999982000000000","0000003992000000000000000003799993000000000000000059999999984000379999999999999999999999999200000000","0000003997000000000000000000158996000000000000000029999999999400015999999999999999999999999500000000","0000004999600000000000000000002799200000000000000003799999999920000599999999999999999998999500000000","0000004999940000000000000000000179820000000000000000025899999940000179999999999999999930266100000000","0000004999970000000000000000000017984000000000000000000289999950000013589999999999999800000000000000","0000004999960000000000000000000001899610000000000000000049999950000000029999999999999920000000000000","0000003999930000000000000000000000399971000000000000000019999970000000003899999999999982000000000000","0000003999930000000000000000000000049996000000000000000007999996000000000038999999999999654100000000","0000002999970000000000000000000000004999720000000000000002899999610000000003999999999999999820000000","0000001899996100000000000000000000000269996300000000000000255589940000000001899999999999999960000000","0000000899999840000000000000000000000002577500000000000000000017970000000004999999999999999980000000","0000000699999995000000000000000000000000000000035300000000000003994000000018999999999999999981000000","0000000599999999200000000000000000000000000000069940000000000000699620000029999999999976799970000000","0000000399999999200000000000000000000000000000003310000000000000026996000007999999999300039970000000","0000000189999995000000000000000000000000000000000000000000000000000799500005999999995000005950000000","0000000069999960000000000000000000000000000000000000000000000000000399810018999999850000002940000000","0000000039999950000000000000000000000000000000000000000000000000000399973379999995100000002920000000","0000000018999971000000000000000000000000000000000000000000000000000399999999999980000000005800000000","0000000005999997100000000000000000000000000000000000000000000000000179999999999960000000049600000000","0000000002999999200000000000000000000000000000000000000000000000000027999999999981000000399300000000","0000000000699998100000000000000000000000000000000000000000000000000000799974479996100000698100000000","0000000000299971000000000000000000000015630000000000000000000000000000299710017999710000595000000000","0000000000069950000000000020000000000069993000000000000000000000000000199400004999930000492000000000","0000000000029981000000001797200000000069998000000000000000000000000000499300003999920000770000000000","0000000000005994000000003999820000000028999600000000000000000000000000697100001899950004920000000000","0000000000001898100000001899960000000002799974100000000000000000000000793000000399997569600000000000","0000000000000399600000000279995000000000499999710000000000000000000003992000000025999999200000000000","0000000000000059961000000005999740000001799999950000000000000000000148970000000000599995000000000000","0000000000000007997300000000599994003888999999995100000000134100002899610000000000299970000000000000","0000000000000002899972000000189998128999999999999877500001799940008994000000000000189920000000000000","0000000000000000399998100000089999889999999999999999962017999993019980000001330000037300000000000000","0000000000000000049999400000069999999999999999999999999889999996008981000028996000000000000000000000","0000000000000000004999600000017999999999999999999999999999999998328996211489999751000000000000000000","0000000000000000000499820000001599999999999999999999999999999999999999988999999995000000000000000000","0000000000000000000049982000000069999999999999999974589999999999999999999999999992000000000000000000","0000000000000000000003999610000018999999999999999600014899999999999999999999999940000000000000000000","0000000000000000000000389981000001579999999999999300000289999999999999999999999300000000000000000000","0000000000000000000000027996000000002799999999998100000025689999999999999999982000000000000000000000","0000000000000000000000001599510000000189999998552000000000028999999999999999610000000000000000000000","0000000000000000000000000038983000000038999992000000000000007999999999999984000000000000000000000000","0000000000000000000000000001599620000002699980000000000000049999999999999620000000000000000000000000","0000000000000000000000000000026996200000079993000000000005899999999999973000000000000000000000000000","0000000000000000000000000000000269973100059999410000000029999999999997300000000000000000000000000000","0000000000000000000000000000000002589863489999986100000005658999998520000000000000000000000000000000","0000000000000000000000000000000000013699999999999700000000002998631000000000000000000000000000000000","0000000000000000000000000000000000000013578999999950000000000231000000000000000000000000000000000000","0000000000000000000000000000000000000000001234556630000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000","0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"]

const COMPARE = {
  jarvis: {
    cls: "",
    html: "<span class=\"ac\">Done.</span> Pulled your 3 leads, sent each your usual follow-up, and booked <b>King Ritson Dental</b> into Tuesday 2pm — all logged in your CRM. Want me to ping you when they reply?",
    tags: [["remembered your follow-up", "good"], ["knew the 3 leads", "good"], ["sent + booked + logged", "good"]] as [string, string][],
  },
  other: {
    cls: "meh",
    html: "I can’t send emails or see your leads or calendar. Here’s a follow-up template you can copy — you’ll have to send it and book it yourself.",
    tags: [["no memory of your leads", ""], ["can’t take the action", ""], ["hands you homework", ""]] as [string, string][],
  },
}

// "what only jarvis os1 does" — tabbed visual showcase, ported verbatim from
// os1_body_mockup_v7_visual.html (baked map/lead/board/scheduler data). Rendered as raw
// HTML so the markup + entities stay faithful; the .ftab tab logic + one-shot .run
// animations are wired in the effect below (CSS-only animations, no rAF). The lead-list
// A/B/C badge class `tier` is renamed to `ltier` so it can't collide with the pricing
// `.tier` cards in this same scope.
const FORKS_HTML = `<div class="wrap"><div class="kick">what only jarvis os1 does</div>
<p class="leadsans">Three weapons most AI can&rsquo;t touch &mdash; bolted into one operator. <span class="ac">See them actually run.</span></p>
<p class="subp">Tap a fork to watch it work &darr;</p>
<div class="forks">
<div class="ftabs">
<button class="ftab on" data-k="leads">Rue Leads<small>finds &amp; scores clients</small></button>
<button class="ftab" data-k="crm">Rue CRM<small>your white-label pipeline</small></button>
<button class="ftab" data-k="social">Social Autopilot<small>runs your feed</small></button>
</div>

<div class="fpanel on" data-k="leads">
<div class="fbar"><span class="dotlive"></span>RUE LEADS<i>//</i> scanning Toronto &middot; <b>212</b> businesses found &middot; <b class="hot">14 A-tier ready to call</b></div>
<div class="leadwrap">
<div class="map">
<span class="road h" style="top:24%"></span><span class="road h" style="top:58%"></span><span class="road h" style="top:84%"></span>
<span class="road v" style="left:30%"></span><span class="road v" style="left:62%"></span><span class="road v" style="left:84%"></span>
<span class="pin a" style="top:26%;left:24%"><em><b>92</b></em><i>King Ritson Dental</i></span>
<span class="pin a" style="top:54%;left:17%"><em><b>88</b></em><i>Bloor Auto Repair</i></span>
<span class="pin a" style="top:40%;left:47%"><em><b>84</b></em><i>Lakeview Dental</i></span>
<span class="pin a" style="top:50%;left:73%"><em><b>81</b></em><i>Summit Roofing</i></span>
<span class="pin b" style="top:70%;left:55%"><em><b>71</b></em><i>Glow Med Spa</i></span>
<span class="pin c" style="top:20%;left:78%"><em><b>49</b></em><i>Pine Law Group</i></span>
<span class="scan"></span>
</div>
<div class="leadlist">
<div class="lrow"><div class="lname">King Ritson Dental<span>Dental clinic &middot; &#9742; (905) 555-0142</span></div><div class="lscore"><span class="bar"><b style="--w:92%"></b></span><span class="ltier a">A &middot; 92</span></div></div>
<div class="lrow"><div class="lname">Bloor Auto Repair<span>Auto shop &middot; &#9742; (416) 555-0198</span></div><div class="lscore"><span class="bar"><b style="--w:88%"></b></span><span class="ltier a">A &middot; 88</span></div></div>
<div class="lrow"><div class="lname">Lakeview Dental<span>Dental clinic &middot; &#9742; (647) 555-0173</span></div><div class="lscore"><span class="bar"><b style="--w:84%"></b></span><span class="ltier a">A &middot; 84</span></div></div>
<div class="lrow"><div class="lname">Summit Roofing<span>Roofing &middot; &#9742; (905) 555-0120</span></div><div class="lscore"><span class="bar"><b style="--w:81%"></b></span><span class="ltier a">A &middot; 81</span></div></div>
<div class="lrow"><div class="lname">Glow Med Spa<span>Med spa &middot; &#9742; (416) 555-0155</span></div><div class="lscore"><span class="bar"><b style="--w:71%"></b></span><span class="ltier b">B &middot; 71</span></div></div>
</div>
</div>
</div>

<div class="fpanel" data-k="crm">
<div class="fbar"><span class="dotlive"></span>RUE CRM<i>//</i> <span class="wlchip">&#9698; YOURBRAND CRM</span> <b>100% white-label</b> &middot; pipeline live</div>
<div class="board">
<div class="col"><div class="ch">New Lead<span>3</span></div>
<div class="card"><h5>Pine Law Group</h5><div class="svc">Legal intake</div><div class="val">$4,200</div></div>
<div class="card"><h5>Corner Barber Co</h5><div class="svc">Website + booking</div><div class="val">$2,600</div></div>
<div class="card"><h5>Glow Med Spa</h5><div class="svc">Waitlist auto-fill</div><div class="val">$3,400</div></div>
</div>
<div class="col"><div class="ch">Quoted<span>2</span></div>
<div class="card"><h5>King Ritson Dental</h5><div class="svc">No-show prevention</div><div class="val">$5,400</div><span class="pdfchip">&#9678; proposal.pdf sent</span></div>
<div class="card"><h5>Bloor Auto Repair</h5><div class="svc">AI voice agent</div><div class="val">$3,200</div></div>
</div>
<div class="col"><div class="ch">In Progress<span>1</span></div>
<div class="card"><h5>Lakeview Dental</h5><div class="svc">Smart booking</div><div class="val">$4,800</div></div>
</div>
<div class="col"><div class="ch">Won<span>1</span></div>
<div class="card win"><h5>Summit Roofing</h5><div class="svc">Site + auto-portfolio</div><div class="val">$6,100</div></div>
</div>
</div>
<div class="crmtoast">Branded proposal generated &amp; emailed to King Ritson Dental &mdash; your logo, your colors, zero spreadsheets touched.</div>
</div>

<div class="fpanel" data-k="social">
<div class="fbar"><span class="dotlive"></span>SOCIAL AUTOPILOT<i>//</i> this week &middot; <b>5 posts</b> queued &middot; written in your voice</div>
<div class="socwrap">
<div class="week">
<div class="day"><div class="dh">Mon</div><div class="post"><div class="pf">IG<u>9:00a</u></div><div class="cap">&ldquo;5 signs your dentist is ghosting your calls&hellip;&rdquo;</div><div class="st"><b>&#9679;</b> Scheduled</div></div></div>
<div class="day"><div class="dh">Tue</div></div>
<div class="day"><div class="dh">Wed</div><div class="post"><div class="pf">FB<u>12:30p</u></div><div class="cap">Behind the scenes: how we book 24/7</div><div class="st"><b>&#9679;</b> Scheduled</div></div><div class="post"><div class="pf">IN<u>5:00p</u></div><div class="cap">How we cut no-shows by 38%</div><div class="st"><b>&#9679;</b> Scheduled</div></div></div>
<div class="day"><div class="dh">Thu</div></div>
<div class="day"><div class="dh">Fri</div><div class="post"><div class="pf">IG<u>6:00p</u></div><div class="cap">Friday tip: never miss a lead again</div><div class="st"><b>&#9679;</b> Scheduled</div></div></div>
<div class="day"><div class="dh">Sat</div></div>
<div class="day"><div class="dh">Sun</div><div class="post"><div class="pf">IN<u>11:00a</u></div><div class="cap">The 1 system every clinic needs</div><div class="st"><b>&#9679;</b> Scheduled</div></div></div>
</div>
<div class="compose"><div class="ct">&#9679;_ draft &mdash; in your voice</div>
<div class="pvtags"><span class="pvtag">Instagram</span><span class="pvtag">Facebook</span><span class="pvtag">LinkedIn</span></div>
<div class="pvcap">&ldquo;Most dental offices lose <b>6 calls a day</b>. Here&rsquo;s the fix that pays for itself in week one&hellip;&rdquo;</div>
<div class="acts"><span class="abtn">Edit</span><span class="abtn pri">Approve &amp; publish</span></div>
</div>
</div>
</div>

</div></div>`

const CSS = `
.os1h-root{
  --bg:#0a0a0a;--line:rgba(243,234,217,0.12);--cream:#f3ead9;--muted:rgba(243,234,217,0.55);
  --faint:rgba(243,234,217,0.30);--accent:#c84b31;--surface:#101010;
  --word:var(--font-sans),'Helvetica Neue',sans-serif;--brand:var(--font-hanken),sans-serif;
  --mono:var(--font-jetbrains),ui-monospace,monospace;--arcade:var(--font-arcade),monospace;
  position:relative;background:var(--bg);color:var(--cream);font-family:var(--brand);font-weight:400;
  -webkit-font-smoothing:antialiased;line-height:1.6;overflow:hidden;
}
.os1h-root *{margin:0;padding:0;box-sizing:border-box}
.os1h-root::before{content:"";position:absolute;inset:0;pointer-events:none;z-index:5;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.15) 0,rgba(0,0,0,.15) 1px,transparent 1px,transparent 3px);
  mix-blend-mode:multiply;opacity:.3}
.os1h-root .bgfield{position:absolute;inset:0;width:100%;height:100%;z-index:0;opacity:.16;pointer-events:none}
.os1h-root .os1h-content{position:relative;z-index:2}
.os1h-root .wrap{max-width:1140px;margin:0 auto;padding:0 28px}
.os1h-root .statusbar{position:sticky;top:0;z-index:40;display:flex;justify-content:space-between;align-items:center;
  font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--faint);
  border-bottom:1px solid var(--line);padding:10px 28px;background:rgba(10,10,10,.82);backdrop-filter:blur(6px)}
.os1h-root .statusbar b{color:var(--muted);font-weight:400}
.os1h-root .blink{animation:os1hblink 1.05s steps(1) infinite}@keyframes os1hblink{50%{opacity:0}}
.os1h-root section{padding:92px 0;border-bottom:1px solid var(--line);position:relative}
.os1h-root .kick{font-family:var(--mono);font-size:11px;letter-spacing:.4em;text-transform:uppercase;color:var(--accent);
  margin-bottom:22px;display:flex;align-items:center;gap:14px}.os1h-root .kick::before{content:"";width:28px;height:1px;background:var(--accent)}
.os1h-root .intro{display:flex;align-items:center;gap:44px}
.os1h-root .logobox{position:relative;width:300px;height:300px;flex-shrink:0;cursor:crosshair}
.os1h-root .logobox .glow{position:absolute;inset:14%;border-radius:50%;
  background:radial-gradient(circle,rgba(200,75,49,.30),rgba(200,75,49,.05) 55%,transparent 72%);filter:blur(20px);animation:os1hbreathe 4.6s ease-in-out infinite}
@keyframes os1hbreathe{0%,100%{transform:scale(.9);opacity:.6}50%{transform:scale(1.08);opacity:1}}
.os1h-root .logobox canvas{position:absolute;inset:0;width:100%;height:100%}
.os1h-root .bigword{font-family:var(--word);font-weight:900;letter-spacing:-.035em;font-size:clamp(34px,5vw,66px);line-height:.96}
.os1h-root .bigword em{font-style:normal;color:var(--accent)}
.os1h-root .tagline{font-family:var(--mono);font-size:12.5px;color:var(--muted);margin-top:16px;letter-spacing:.04em}.os1h-root .tagline .pr{color:var(--accent)}
.os1h-root .asciiband{position:relative;border:1px solid var(--line);background:#080808;overflow:hidden;padding:54px 44px;margin-top:8px}
.os1h-root .asciiband .bandfx{position:absolute;inset:0;width:100%;height:100%;opacity:.5;z-index:0}
.os1h-root .asciiband .bandtext{position:relative;z-index:1}
.os1h-root .cb{position:absolute;width:14px;height:14px;border-color:var(--accent);z-index:2}
.os1h-root .cb.tl{top:-1px;left:-1px;border-top:2px solid;border-left:2px solid}.os1h-root .cb.tr{top:-1px;right:-1px;border-top:2px solid;border-right:2px solid}
.os1h-root .cb.bl{bottom:-1px;left:-1px;border-bottom:2px solid;border-left:2px solid}.os1h-root .cb.br{bottom:-1px;right:-1px;border-bottom:2px solid;border-right:2px solid}
.os1h-root .leadsans{font-family:var(--brand);font-size:clamp(20px,2.6vw,30px);line-height:1.45;max-width:840px;font-weight:400}
.os1h-root .leadsans b{font-weight:700}.os1h-root .leadsans .ac{color:var(--accent);font-weight:500}
.os1h-root .subp{margin-top:18px;font-family:var(--brand);font-size:15px;color:var(--muted);max-width:640px}
.os1h-root .compare{margin-top:38px;border:1px solid var(--line);background:#0c0c0c}.os1h-root .compare .tabs{display:flex;border-bottom:1px solid var(--line)}
.os1h-root .compare .tab{flex:1;padding:15px;font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;text-align:center;
  cursor:pointer;color:var(--faint);background:transparent;border:none;transition:.25s}
.os1h-root .compare .tab.on{color:var(--cream);background:#141110;box-shadow:inset 0 -2px 0 var(--accent)}
.os1h-root .compare .stage{padding:26px 24px;min-height:168px}.os1h-root .compare .q{font-family:var(--mono);font-size:12.5px;color:var(--muted);margin-bottom:16px}
.os1h-root .compare .q b{color:var(--cream)}.os1h-root .compare .ans{font-size:15px;line-height:1.6}.os1h-root .compare .ans .ac{color:var(--accent);font-weight:600}
.os1h-root .compare .ans.meh{color:var(--muted)}
.os1h-root .tagrow{margin-top:18px;display:flex;gap:8px;flex-wrap:wrap}
.os1h-root .pill{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;padding:5px 10px;border:1px solid var(--line);color:var(--faint)}
.os1h-root .pill.good{color:var(--accent);border-color:rgba(200,75,49,.45)}
.os1h-root .why{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:46px}
.os1h-root .wc{border:1px solid var(--line);padding:26px 22px;background:var(--surface);transition:.3s}.os1h-root .wc:hover{border-color:rgba(200,75,49,.4);background:#131110}
.os1h-root .wc .n{font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:.2em}.os1h-root .wc h4{font-family:var(--brand);font-weight:700;font-size:18px;margin:12px 0 8px}
.os1h-root .wc p{font-size:13px;color:var(--muted);line-height:1.6}.os1h-root .wc .vs{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
/* what only jarvis os1 does — forks showcase */
.os1h-root .forks{margin-top:30px;border:1px solid var(--line);background:#0c0c0c}
.os1h-root .forks .ftabs{display:flex;border-bottom:1px solid var(--line)}
.os1h-root .forks .ftab{flex:1;padding:15px 10px;font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;text-align:center;cursor:pointer;color:var(--faint);background:transparent;border:none;transition:.25s}
.os1h-root .forks .ftab:hover{color:var(--muted)}.os1h-root .forks .ftab.on{color:var(--cream);background:#141110;box-shadow:inset 0 -2px 0 var(--accent)}
.os1h-root .forks .ftab small{display:block;font-size:9px;letter-spacing:.04em;color:var(--faint);margin-top:4px;text-transform:none}
.os1h-root .fpanel{display:none;padding:20px}.os1h-root .fpanel.on{display:block}
.os1h-root .fbar{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px}.os1h-root .fbar i{color:var(--faint);font-style:normal}.os1h-root .fbar b{color:var(--cream);font-weight:500}.os1h-root .fbar b.hot{color:var(--accent)}
.os1h-root .dotlive{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:os1hpulse 1.6s infinite}@keyframes os1hpulse{0%{box-shadow:0 0 0 0 rgba(200,75,49,.5)}70%{box-shadow:0 0 0 7px rgba(200,75,49,0)}100%{box-shadow:0 0 0 0 rgba(200,75,49,0)}}
.os1h-root .wlchip{font-family:var(--mono);font-size:10px;color:var(--accent);border:1px solid rgba(200,75,49,.45);padding:2px 7px;letter-spacing:.08em}
.os1h-root .leadwrap{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}
.os1h-root .map{position:relative;height:344px;border:1px solid var(--line);background:#070707;overflow:hidden}
.os1h-root .map::before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg,transparent 0 33px,rgba(243,234,217,.035) 33px 34px),repeating-linear-gradient(90deg,transparent 0 33px,rgba(243,234,217,.035) 33px 34px)}
.os1h-root .map .road{position:absolute;background:rgba(243,234,217,.10);z-index:1}.os1h-root .map .road.h{left:0;right:0;height:3px}.os1h-root .map .road.v{top:0;bottom:0;width:3px}
.os1h-root .pin{position:absolute;transform:translate(-50%,-50%) scale(.2);opacity:0;transition:.55s cubic-bezier(.2,1.3,.3,1);text-align:center;z-index:3}
.os1h-root .run .pin{transform:translate(-50%,-50%) scale(1);opacity:1}
.os1h-root .pin em{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);font-family:var(--mono);font-size:11px;font-style:normal;font-weight:600;color:#0a0a0a;margin:0 auto}
.os1h-root .pin em b{transform:rotate(45deg)}
.os1h-root .pin i{display:block;font-style:normal;font-family:var(--mono);font-size:9px;color:var(--cream);margin-top:5px;white-space:nowrap;background:rgba(8,8,8,.78);padding:1px 5px;border:1px solid var(--line)}
.os1h-root .pin.a em{background:var(--accent);box-shadow:0 0 16px rgba(200,75,49,.75)}.os1h-root .pin.b em{background:#d8a657}.os1h-root .pin.c em{background:rgba(243,234,217,.55)}
.os1h-root .scan{position:absolute;left:0;right:0;height:64px;top:-64px;background:linear-gradient(180deg,transparent,rgba(200,75,49,.20),transparent);z-index:2;pointer-events:none}.os1h-root .run .scan{animation:os1hsweep 2s ease-in-out 1}@keyframes os1hsweep{0%{top:-64px}100%{top:344px}}
.os1h-root .leadlist{display:flex;flex-direction:column;gap:8px}
.os1h-root .lrow{border:1px solid var(--line);background:var(--surface);padding:11px 13px;display:flex;justify-content:space-between;align-items:center;gap:12px;opacity:0;transform:translateY(8px);transition:.45s}.os1h-root .run .lrow{opacity:1;transform:none}
.os1h-root .lname{font-size:13.5px;color:var(--cream);font-weight:500}.os1h-root .lname span{display:block;font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:3px;font-weight:400;letter-spacing:.02em}
.os1h-root .lscore{text-align:right;min-width:104px}.os1h-root .bar{display:block;height:5px;background:rgba(243,234,217,.1);position:relative;margin-bottom:7px}.os1h-root .bar b{position:absolute;left:0;top:0;bottom:0;width:0;background:var(--accent);transition:width 1.1s cubic-bezier(.3,1,.4,1) .25s}.os1h-root .run .bar b{width:var(--w)}
.os1h-root .ltier{font-family:var(--mono);font-size:10px;letter-spacing:.08em;padding:2px 6px;border:1px solid var(--line)}.os1h-root .ltier.a{color:var(--accent);border-color:rgba(200,75,49,.5)}.os1h-root .ltier.b{color:#d8a657;border-color:rgba(216,166,87,.4)}.os1h-root .ltier.c{color:var(--faint)}
.os1h-root .board{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.os1h-root .col{border:1px solid var(--line);background:#080808;padding:10px;min-height:210px}
.os1h-root .ch{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);display:flex;justify-content:space-between;margin-bottom:10px;border-bottom:1px solid var(--line);padding-bottom:8px}.os1h-root .ch span{color:var(--accent)}
.os1h-root .card{border:1px solid var(--line);background:var(--surface);padding:11px;margin-bottom:8px;opacity:0;transform:translateY(8px);transition:.45s}.os1h-root .run .card{opacity:1;transform:none}.os1h-root .card.win{border-color:rgba(200,75,49,.45)}
.os1h-root .card h5{font-family:var(--brand);font-size:13px;font-weight:600;color:var(--cream);margin-bottom:6px}
.os1h-root .card .svc{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.os1h-root .card .val{font-family:var(--word);font-weight:700;font-size:15px;color:var(--cream);margin-top:8px}
.os1h-root .pdfchip{margin-top:9px;font-family:var(--mono);font-size:9.5px;color:var(--accent);border:1px solid rgba(200,75,49,.4);padding:3px 7px;display:inline-block}
.os1h-root .crmtoast{margin-top:14px;font-family:var(--mono);font-size:11.5px;color:var(--cream);border:1px solid rgba(200,75,49,.4);background:rgba(200,75,49,.08);padding:11px 13px;opacity:0;transition:.5s .6s}.os1h-root .run .crmtoast{opacity:1}.os1h-root .crmtoast::before{content:"\\2713 ";color:var(--accent)}
.os1h-root .socwrap{display:grid;grid-template-columns:1.5fr 1fr;gap:16px}
.os1h-root .week{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.os1h-root .day{border:1px solid var(--line);background:#080808;min-height:158px;padding:6px}
.os1h-root .day .dh{font-family:var(--mono);font-size:9px;color:var(--faint);text-transform:uppercase;letter-spacing:.05em;margin-bottom:7px;text-align:center;border-bottom:1px solid var(--line);padding-bottom:5px}
.os1h-root .post{border:1px solid var(--line);background:var(--surface);padding:6px 7px;margin-bottom:6px;opacity:0;transform:translateY(6px);transition:.4s}.os1h-root .run .post{opacity:1;transform:none}
.os1h-root .post .pf{font-family:var(--mono);font-size:8.5px;letter-spacing:.04em;color:var(--accent);display:flex;justify-content:space-between;align-items:center}
.os1h-root .post .pf u{color:var(--faint);text-decoration:none}
.os1h-root .post .cap{font-size:9.5px;color:var(--muted);margin-top:4px;line-height:1.35}
.os1h-root .post .st{font-family:var(--mono);font-size:8px;color:var(--faint);margin-top:5px;text-transform:uppercase;letter-spacing:.06em}.os1h-root .post .st b{color:var(--accent);font-weight:400}
.os1h-root .compose{border:1px solid var(--line);background:#080808;padding:15px}
.os1h-root .compose .ct{font-family:var(--mono);font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:.1em;margin-bottom:11px}
.os1h-root .pvtags{display:flex;gap:6px;margin-bottom:11px}.os1h-root .pvtag{font-family:var(--mono);font-size:9px;color:var(--muted);border:1px solid var(--line);padding:3px 7px}
.os1h-root .pvcap{font-size:13px;color:var(--cream);line-height:1.5}.os1h-root .pvcap b{color:var(--accent)}
.os1h-root .acts{display:flex;gap:8px;margin-top:15px}
.os1h-root .abtn{flex:1;text-align:center;font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;padding:10px;border:1px solid var(--line);color:var(--cream);cursor:pointer}.os1h-root .abtn.pri{background:var(--accent);border-color:var(--accent);color:#0a0a0a}
.os1h-root .billtoggle{display:flex;align-items:center;gap:12px;margin:4px 0 26px;font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.os1h-root .billtoggle button{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;padding:7px 14px;border:1px solid var(--line);background:transparent;color:var(--faint);cursor:pointer;transition:.25s}
.os1h-root .billtoggle button.on{color:#0a0a0a;background:var(--cream);border-color:var(--cream)}
.os1h-root .billtoggle .save{color:var(--accent);border:1px solid rgba(200,75,49,.4);padding:4px 9px}
.os1h-root .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:6px;align-items:stretch}
.os1h-root .tier{border:1px solid var(--line);background:var(--surface);padding:30px 26px 32px;position:relative;display:flex;flex-direction:column;transition:.35s}
.os1h-root .tier:hover{border-color:rgba(200,75,49,.45)}.os1h-root .tier.feat{border-color:var(--accent);background:#120f0e}
.os1h-root .tier.feat::after{content:"\\25E2 most chosen";position:absolute;top:14px;right:16px;font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
.os1h-root .corner{position:absolute;width:13px;height:13px;border-color:var(--accent);opacity:0;transition:.35s}
.os1h-root .tier:hover .corner,.os1h-root .tier.feat .corner{opacity:1}
.os1h-root .corner.tl{top:-1px;left:-1px;border-top:2px solid;border-left:2px solid}.os1h-root .corner.br{bottom:-1px;right:-1px;border-bottom:2px solid;border-right:2px solid}
.os1h-root .tier .tag{font-family:var(--mono);font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--faint)}
.os1h-root .tier h3{font-family:var(--brand);font-size:36px;font-weight:800;letter-spacing:-.02em;margin:8px 0 4px}
.os1h-root .tier .promise{font-size:13px;color:var(--muted);min-height:34px}
.os1h-root .price{display:flex;align-items:baseline;gap:8px;margin:22px 0 4px}
.os1h-root .price .amt{font-family:var(--word);font-size:54px;font-weight:900;line-height:1;letter-spacing:-.03em}
.os1h-root .price .per{font-family:var(--mono);font-size:12px;color:var(--faint)}.os1h-root .price.talk .amt{font-size:38px;color:var(--accent)}
.os1h-root .billed{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.1em}
.os1h-root .sep{border:none;border-top:1px solid var(--line);margin:22px 0}
.os1h-root .feats{list-style:none;display:flex;flex-direction:column;gap:12px;flex:1}
.os1h-root .feats li{font-size:12.5px;color:var(--cream);display:flex;gap:10px;line-height:1.5}.os1h-root .feats li::before{content:"\\203A";color:var(--accent);font-weight:700}
.os1h-root .feats .head{color:var(--faint);font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase}.os1h-root .feats .head::before{content:""}
.os1h-root .feats .more{color:var(--accent);font-family:var(--mono);font-size:11.5px;letter-spacing:.08em}.os1h-root .feats .more::before{content:"+ "}
.os1h-root .btn{margin-top:24px;display:block;width:100%;text-align:center;padding:14px;border:1px solid var(--line);background:transparent;color:var(--cream);
  font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;cursor:pointer;transition:.3s}
.os1h-root .btn:hover{background:var(--cream);color:#0a0a0a}.os1h-root .btn:disabled{opacity:.6;cursor:default}
.os1h-root .btn.primary{background:var(--accent);border-color:var(--accent);color:#0a0a0a;font-weight:500}.os1h-root .btn.primary:hover{background:#e0572f}
.os1h-root .perr{color:var(--accent);font-family:var(--mono);font-size:12px;text-align:center;margin-top:22px}
.os1h-root .marquee{border-top:1px solid var(--line);border-bottom:1px solid var(--line);overflow:hidden;white-space:nowrap;padding:15px 0;margin-top:40px}
.os1h-root .marquee div{display:inline-block;animation:os1hscroll 28s linear infinite;font-family:var(--mono);font-size:13px;letter-spacing:.18em;color:var(--faint)}
.os1h-root .marquee span{margin:0 26px}.os1h-root .marquee b{color:var(--accent);font-weight:400}@keyframes os1hscroll{to{transform:translateX(-50%)}}
.os1h-root .signoff{padding:118px 0 86px;text-align:center;background:rgba(8,8,8,.6)}
.os1h-root .signoff .lockup{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:32px}
.os1h-root .signoff .lockup canvas{width:60px;height:60px}.os1h-root .signoff .lockup .jl{font-family:var(--arcade);font-size:13px;letter-spacing:.06em;color:var(--muted)}
.os1h-root .megabrand{font-family:var(--word);font-weight:900;font-size:clamp(70px,15vw,210px);line-height:.9;letter-spacing:-.04em;color:var(--cream);opacity:.92}
.os1h-root .megabrand sup{font-size:.17em;vertical-align:super;font-weight:400;color:var(--faint)}.os1h-root .megabrand .amp{color:var(--accent)}
.os1h-root .signoff .tech{font-family:var(--word);font-weight:400;letter-spacing:.3em;font-size:clamp(11px,1.5vw,15px);color:var(--faint);text-transform:uppercase;margin-top:26px;padding-left:.3em}
.os1h-root .signoff .foot{font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:rgba(243,234,217,.25);margin-top:36px}.os1h-root .signoff .foot span{margin:0 10px;color:rgba(243,234,217,.12)}
@media(prefers-reduced-motion:reduce){
  .os1h-root .logobox .glow,.os1h-root .marquee div,.os1h-root .blink,.os1h-root .dotlive{animation:none}
  .os1h-root .pin,.os1h-root .lrow,.os1h-root .card,.os1h-root .post,.os1h-root .bar b,.os1h-root .crmtoast{transition:none}
  .os1h-root .run .scan{animation:none}.os1h-root .scan{display:none}
}
@media(max-width:880px){
  .os1h-root .grid,.os1h-root .why{grid-template-columns:1fr}.os1h-root .intro{flex-direction:column;text-align:center}
  .os1h-root .leadwrap,.os1h-root .socwrap{grid-template-columns:1fr}.os1h-root .board{grid-template-columns:repeat(2,1fr)}.os1h-root .week{grid-template-columns:repeat(4,1fr)}
  .os1h-root .forks .ftabs{flex-direction:column}.os1h-root .forks .ftab{border-bottom:1px solid var(--line)}.os1h-root .map{height:280px}
}
`

export default function OS1HermesBody() {
  const router = useRouter()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [isYearly, setIsYearly] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const resumedRef = useRef(false)

  // ---- real checkout engine (identical behaviour to OS1Pricing) ----
  async function goCheckout(plan: HermesPlan, interval: "month" | "year") {
    setError(null)
    if (!supabase) return
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user) {
      try {
        localStorage.setItem("os1_intent", JSON.stringify({ plan: plan.id, interval }))
      } catch {}
      stashAuthNext("/os1")
      await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${authRedirectBase()}/auth/callback?next=${encodeURIComponent("/os1")}` },
      })
      return
    }
    setBusyId(plan.id)
    const userId = jarvisUserId(session.user.id)
    const email = session.user.email || ""
    try {
      const status = await getOS1Status(userId, email)
      if (status?.has_access) {
        try { await setJarvisMode(userId, "business") } catch {}
        window.location.href = "/business/chat"
        return
      }
      const res = await startCheckout({ userId, email, plan: plan.id, interval, trial: true })
      if (res?.ok && res.url) {
        window.location.href = res.url
        return
      }
      setError(res?.error || "Could not start checkout. Please try again.")
    } catch {
      setError("Something went wrong starting checkout. Please try again.")
    } finally {
      setBusyId(null)
    }
  }

  function onSelect(plan: HermesPlan) {
    if (plan.action === "contact") {
      router.push("/contact")
      return
    }
    goCheckout(plan, isYearly ? "year" : "month")
  }

  // Resume checkout after returning from Google login (os1_intent).
  useEffect(() => {
    if (resumedRef.current || !supabase) return
    let raw: string | null = null
    try { raw = localStorage.getItem("os1_intent") } catch {}
    if (!raw) return
    resumedRef.current = true
    try { localStorage.removeItem("os1_intent") } catch {}
    let intent: { plan: string; interval: "month" | "year" }
    try { intent = JSON.parse(raw) } catch { return }
    const plan = PLANS.find((p) => p.id === intent.plan)
    if (plan && plan.action === "checkout") {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user) goCheckout(plan, intent.interval)
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- canvases + compare toggle (imperative, scoped to root) ----
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const cleanups: (() => void)[] = []
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches

    function asciiLogo(c: HTMLCanvasElement) {
      const x = c.getContext("2d")!
      const CW = 5, CH = 7, fs = 8
      const ramp = " .:-=+*oxOX#%@".split("")
      let W = 1, H = 1, cols = 1, rows = 1, t = Math.random() * 9, mx = -999, my = -999
      function sz() {
        const r = c.getBoundingClientRect()
        W = c.width = Math.max(1, r.width); H = c.height = Math.max(1, r.height)
        cols = Math.ceil(W / CW); rows = Math.ceil(H / CH)
      }
      sz()
      function frame() {
        x.clearRect(0, 0, W, H)
        x.font = fs + "px monospace"; x.textBaseline = "top"
        const p = 0.84 + 0.16 * Math.sin(t * 1.4), sc = 1 + 0.04 * Math.sin(t * 1.4)
        for (let gy = 0; gy < rows; gy++) for (let gx = 0; gx < cols; gx++) {
          const u = ((gx + 0.5) / cols - 0.5) / sc + 0.5, v = ((gy + 0.5) / rows - 0.5) / sc + 0.5
          if (u < 0 || u >= 1 || v < 0 || v >= 1) continue
          let b = (MASK[Math.floor(v * 100)].charCodeAt(Math.floor(u * 100)) - 48) / 9
          if (b <= 0.02) continue
          b = b * p + 0.10 * Math.sin((gx * 0.5 + gy * 0.4) - t * 2.0)
          const px = gx * CW, py = gy * CH
          if (mx > -900) { const dx = px - mx, dy = py - my, d = Math.sqrt(dx * dx + dy * dy); if (d < 90) b += (1 - d / 90) * 0.55 }
          b = Math.max(0, Math.min(1, b))
          const ch = ramp[Math.floor(b * (ramp.length - 1))]
          if (ch === " ") continue
          const m = Math.min(1, b * 1.1)
          x.fillStyle = "rgba(" + Math.round(200 + m * 55) + "," + Math.round(80 + m * 60) + "," + Math.round(60 + m * 50) + "," + (0.5 + b * 0.5) + ")"
          x.fillText(ch, px, py)
        }
      }
      if (reduce) {
        frame()
        const ro = new ResizeObserver(() => { sz(); frame() }); ro.observe(c)
        return () => ro.disconnect()
      }
      const ro = new ResizeObserver(sz); ro.observe(c)
      const onMove = (e: MouseEvent) => { const r = c.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top }
      const onLeave = () => { mx = -999 }
      c.addEventListener("mousemove", onMove); c.addEventListener("mouseleave", onLeave)
      let rafId: number | null = null, running = true
      const f = () => { if (!running) { rafId = null; return } t += 0.018; frame(); rafId = requestAnimationFrame(f) }
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { running = e.isIntersecting; if (running && rafId === null) rafId = requestAnimationFrame(f) })
      }, { threshold: 0 })
      io.observe(c)
      rafId = requestAnimationFrame(f)
      return () => {
        running = false; if (rafId) cancelAnimationFrame(rafId)
        io.disconnect(); ro.disconnect()
        c.removeEventListener("mousemove", onMove); c.removeEventListener("mouseleave", onLeave)
      }
    }

    function waveField(c: HTMLCanvasElement, cw: number, ch: number) {
      const x = c.getContext("2d")!
      const chars = " .,:-=+*#".split("")
      let W = 1, H = 1, cols = 1, rows = 1, t = 0
      function sz() {
        const r = c.getBoundingClientRect()
        W = c.width = Math.max(1, r.width); H = c.height = Math.max(1, r.height)
        cols = Math.ceil(W / cw); rows = Math.ceil(H / ch)
      }
      sz()
      function frame() {
        x.clearRect(0, 0, W, H)
        x.font = "13px monospace"; x.textBaseline = "top"
        for (let y = 0; y < rows; y++) for (let k = 0; k < cols; k++) {
          const val = Math.sin(k * 0.16 + t) + Math.sin(y * 0.21 - t * 0.8) + Math.sin((k + y) * 0.09 + t * 0.6)
          const n = (val + 3) / 6
          const c2 = chars[Math.max(0, Math.min(chars.length - 1, Math.floor(n * (chars.length - 1))))]
          if (c2 === " ") continue
          x.fillStyle = n > 0.85 ? "rgba(200,75,49," + (0.4 + n * 0.5) + ")" : "rgba(243,234,217," + (0.12 + n * 0.4) + ")"
          x.fillText(c2, k * cw, y * ch)
        }
      }
      const ro = new ResizeObserver(sz); ro.observe(c)
      if (reduce) {
        frame()
        return () => ro.disconnect()
      }
      let rafId: number | null = null, running = true
      const f = () => { if (!running) { rafId = null; return } t += 0.02; frame(); rafId = requestAnimationFrame(f) }
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { running = e.isIntersecting; if (running && rafId === null) rafId = requestAnimationFrame(f) })
      }, { threshold: 0 })
      io.observe(c)
      rafId = requestAnimationFrame(f)
      return () => { running = false; if (rafId) cancelAnimationFrame(rafId); io.disconnect(); ro.disconnect() }
    }

    const bg = root.querySelector<HTMLCanvasElement>("canvas.bgfield")
    if (bg) { const cl = waveField(bg, 11, 15); if (cl) cleanups.push(cl) }
    root.querySelectorAll<HTMLCanvasElement>("canvas.alogo").forEach((c) => { const cl = asciiLogo(c); if (cl) cleanups.push(cl) })
    root.querySelectorAll<HTMLCanvasElement>("canvas.bandfx").forEach((c) => { const cl = waveField(c, 10, 14); if (cl) cleanups.push(cl) })

    // compare toggle + typing reveal
    const cmp = root.querySelector<HTMLElement>(".compare")
    if (cmp) {
      const ans = cmp.querySelector<HTMLElement>(".ans")!
      const tags = cmp.querySelector<HTMLElement>(".tagrow")!
      let typeTimer: ReturnType<typeof setTimeout> | null = null
      const render = (k: "jarvis" | "other") => {
        const d = COMPARE[k]
        ans.className = "ans" + (d.cls ? " " + d.cls : "")
        if (typeTimer) clearTimeout(typeTimer)
        if (reduce) { ans.innerHTML = d.html }
        else {
          const raw = d.html; let i = 0
          const tk = () => {
            if (i <= raw.length) { ans.innerHTML = raw.slice(0, i) + '<span class="blink">▌</span>'; i += 3; typeTimer = setTimeout(tk, 8) }
            else ans.innerHTML = raw
          }
          tk()
        }
        tags.innerHTML = (d.tags || []).map((tg) => '<span class="pill ' + (tg[1] || "") + '">' + tg[0] + "</span>").join("")
      }
      const tabEls = cmp.querySelectorAll<HTMLElement>(".tab")
      const handlers: { el: HTMLElement; fn: () => void }[] = []
      tabEls.forEach((b) => {
        const fn = () => {
          tabEls.forEach((z) => z.classList.remove("on"))
          b.classList.add("on")
          render((b.dataset.k as "jarvis" | "other") || "jarvis")
        }
        b.addEventListener("click", fn)
        handlers.push({ el: b, fn })
      })
      let seen = false
      const io = new IntersectionObserver((es) => {
        es.forEach((e) => { if (e.isIntersecting && !seen) { seen = true; render("jarvis") } })
      }, { threshold: 0.4 })
      io.observe(cmp)
      cleanups.push(() => {
        io.disconnect()
        handlers.forEach((h) => h.el.removeEventListener("click", h.fn))
        if (typeTimer) clearTimeout(typeTimer)
      })
    }

    // "what only jarvis os1 does" — fork tabs + one-shot .run animations (CSS-only, no rAF).
    const frk = root.querySelector<HTMLElement>(".forks")
    if (frk) {
      const frun = (p: HTMLElement | null) => {
        if (!p) return
        if (reduce) { p.classList.add("run"); return } // static final state
        p.classList.remove("run"); void p.offsetWidth; p.classList.add("run")
      }
      const ftabs = frk.querySelectorAll<HTMLElement>(".ftab")
      const fhandlers: { el: HTMLElement; fn: () => void }[] = []
      ftabs.forEach((b) => {
        const fn = () => {
          ftabs.forEach((z) => z.classList.remove("on"))
          b.classList.add("on")
          frk.querySelectorAll<HTMLElement>(".fpanel").forEach((z) => z.classList.remove("on"))
          const pan = frk.querySelector<HTMLElement>('.fpanel[data-k="' + b.dataset.k + '"]')
          if (pan) { pan.classList.add("on"); frun(pan) }
        }
        b.addEventListener("click", fn)
        fhandlers.push({ el: b, fn })
      })
      let fseen = false
      const fio = new IntersectionObserver((es) => {
        es.forEach((e) => { if (e.isIntersecting && !fseen) { fseen = true; frun(frk.querySelector<HTMLElement>(".fpanel.on")) } })
      }, { threshold: 0.3 })
      fio.observe(frk)
      cleanups.push(() => {
        fio.disconnect()
        fhandlers.forEach((h) => h.el.removeEventListener("click", h.fn))
      })
    }

    return () => cleanups.forEach((fn) => { try { fn() } catch {} })
  }, [])

  return (
    <div className="os1h-root" ref={rootRef}>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <canvas className="bgfield" />
      <div className="os1h-content">
        <div className="statusbar">
          <span>RUE<b>://</b>os1</span>
          <span>choose your operator <span className="blink">▎</span></span>
        </div>

        {/* intro */}
        <section>
          <div className="wrap intro">
            <div className="logobox"><div className="glow" /><canvas className="alogo" /></div>
            <div>
              <div className="bigword">One operator.<br /><em>Three altitudes.</em></div>
              <div className="tagline"><span className="pr">jarvis os1 //</span> your autonomous business operator — it remembers, it acts, it sells</div>
            </div>
          </div>
        </section>

        {/* what is jarvis os1 */}
        <section>
          <div className="wrap">
            <div className="kick">what is jarvis os1</div>
            <div className="asciiband">
              <canvas className="bandfx" />
              <span className="cb tl" /><span className="cb tr" /><span className="cb bl" /><span className="cb br" />
              <div className="bandtext">
                <p className="leadsans">An AI <b>operator</b> for your business — not a chatbot you re-explain yourself to every time. It <span className="ac">remembers how you work</span>, <span className="ac">does the work</span> across your tools, and <span className="ac">goes out and finds you customers</span>.</p>
                <p className="subp">Most AI answers a question and forgets you. Rue runs your back office while you run your business. See the difference ↓</p>
              </div>
            </div>
            <div className="compare">
              <div className="tabs">
                <button className="tab" data-k="other">A generic AI assistant</button>
                <button className="tab on" data-k="jarvis">Rue OS1</button>
              </div>
              <div className="stage">
                <div className="q"><b>you ›</b> &quot;send my usual follow-up to the 3 leads from yesterday and book the dentist one in.&quot;</div>
                <div className="ans" />
                <div className="tagrow" />
              </div>
            </div>
          </div>
        </section>

        {/* why it lands differently */}
        <section>
          <div className="wrap">
            <div className="kick">why it lands differently</div>
            <div className="why">
              <div className="wc"><div className="n">01</div><h4>It remembers</h4><p>Your brand, your customers, your last 1,000 conversations — kept, not reset.</p><div className="vs">others: start from zero each chat</div></div>
              <div className="wc"><div className="n">02</div><h4>It acts</h4><p>Connects your apps and actually does it — emails sent, posts queued, records updated.</p><div className="vs">others: hand you text to copy-paste</div></div>
              <div className="wc"><div className="n">03</div><h4>It hunts</h4><p>Goes out, finds local businesses to sell to, scores them, hands you who to call.</p><div className="vs">others: can’t touch the real world</div></div>
            </div>
          </div>
        </section>

        {/* what only jarvis os1 does — tabbed visual showcase (additive insertion) */}
        <section dangerouslySetInnerHTML={{ __html: FORKS_HTML }} />

        {/* pick your altitude — REAL pricing engine */}
        <section id="pricing" style={{ borderBottom: "none" }}>
          <div className="wrap">
            <div className="kick">pick your altitude</div>
            <div className="billtoggle">
              <button className={isYearly ? "" : "on"} onClick={() => setIsYearly(false)}>Monthly</button>
              <button className={isYearly ? "on" : ""} onClick={() => setIsYearly(true)}>Annual</button>
              <span className="save">2 months free</span>
            </div>
            <div className="grid">
              {PLANS.map((plan) => (
                <div key={plan.id} className={"tier" + (plan.feat ? " feat" : "")}>
                  <span className="corner tl" /><span className="corner br" />
                  <div className="tag">{plan.tier}</div>
                  <h3>{plan.name}</h3>
                  <div className="promise">{plan.promise}</div>
                  <div className={"price" + (plan.talk ? " talk" : "")}>
                    <span className="amt">{plan.talk ? plan.monthly : isYearly ? plan.yearly : plan.monthly}</span>
                    {!plan.talk && <span className="per">{isYearly ? plan.perYearly : plan.perMonthly}</span>}
                  </div>
                  <div className="billed">{isYearly ? plan.billedYearly : plan.billedMonthly}</div>
                  <hr className="sep" />
                  <ul className="feats">
                    {plan.headFeature && <li className="head">{plan.headFeature}</li>}
                    {plan.features.map((f, i) => (
                      <li key={i} dangerouslySetInnerHTML={{ __html: f.html }} />
                    ))}
                    <li className="more">{plan.more}</li>
                  </ul>
                  <button
                    className={"btn" + (plan.primary ? " primary" : "")}
                    disabled={busyId === plan.id}
                    onClick={() => onSelect(plan)}
                  >
                    {busyId === plan.id ? "Working…" : plan.cta}
                  </button>
                </div>
              ))}
            </div>
            {error && <p className="perr">{error}</p>}
          </div>
        </section>

        {/* marquee */}
        <div className="marquee"><div>
          <span>◦ remembers everything</span><span>◦ <b>acts across your tools</b></span><span>◦ builds on command</span><span>◦ <b>hunts your next clients</b></span><span>◦ white-label ready</span><span>◦ cancel anytime</span>
          <span>◦ remembers everything</span><span>◦ <b>acts across your tools</b></span><span>◦ builds on command</span><span>◦ <b>hunts your next clients</b></span><span>◦ white-label ready</span><span>◦ cancel anytime</span>
        </div></div>

        {/* signoff */}
        <div className="signoff">
          <div className="lockup"><canvas className="alogo" /><span className="jl">RUE OS1</span></div>
          <div className="megabrand">MG<span className="amp">&amp;</span>CO<sup>™</sup></div>
          <div className="tech">Technologies Inc.</div>
          <div className="foot">mgcotechnologies.com <span>·</span> Based in Toronto, Canada <span>·</span> © 2026 MG&amp;CO Technologies Inc.</div>
        </div>
      </div>
    </div>
  )
}
