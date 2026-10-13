# ruff: noqa: E501  (CSS template: one rule per line reads better than wrapped)
"""Terminal theme for /demo: dark, monospace, tabular numerals, dense rows.

Standalone on purpose — the A09 editorial sheet is not loaded here. Green and
red are reserved for P&L sign and run state; everything else is neutral.
"""

CSS = """
:root{color-scheme:dark;
--c-bg:#0a0d10;--c-panel:#0f1418;--c-raised:#151b21;--c-ink:#d6dde4;--c-muted:#7c8794;
--c-rule-faint:#1d252d;--c-rule-strong:#2b3540;--c-positive:#2ecc71;--c-negative:#ff5c5c;
--c-attention:#e0a33a;--c-focus:#5aa9ff;
--font-mono:ui-monospace,"JetBrains Mono","SFMono-Regular",Menlo,Consolas,"Liberation Mono",monospace;
--rule:1px solid var(--c-rule-faint);--rule-strong:1px solid var(--c-rule-strong);--row:26px}
*{box-sizing:border-box}
html,body{margin:0;background:var(--c-bg);color:var(--c-ink)}
body{font:12.5px/1.45 var(--font-mono);font-variant-numeric:tabular-nums lining-nums;overflow-x:hidden}
a{color:var(--c-focus)} :focus-visible{outline:2px solid var(--c-focus);outline-offset:1px}
.sr-only{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.num{font-variant-numeric:tabular-nums lining-nums;white-space:nowrap}
.meta{color:var(--c-muted)} .ccy{color:var(--c-muted);font-size:.85em}
.pos{color:var(--c-positive)} .neg{color:var(--c-negative)}
.chrome{position:sticky;top:0;z-index:2;background:var(--c-bg)}
.statusbar{display:flex;flex-wrap:wrap;align-items:center;gap:0;min-height:var(--row);border-bottom:var(--rule-strong);background:var(--c-panel)}
.statusbar>*{padding:0 10px;border-right:var(--rule);line-height:var(--row);white-space:nowrap}
.statusbar .brand{font-weight:700;letter-spacing:.06em}
.statusbar .spacer{flex:1 1 auto;border-right:0}
.disclosure{display:flex;flex-wrap:wrap;gap:0 14px;padding:2px 10px;border-bottom:var(--rule);color:var(--c-muted);font-size:11.5px}
.disclosure strong{color:var(--c-ink);letter-spacing:.06em}
.democard{border-bottom:var(--rule);background:var(--c-panel)}
.democard>summary{cursor:pointer;list-style-position:inside;height:var(--row);line-height:var(--row);padding:0 10px;font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--c-attention);user-select:none}
.democard>summary::-webkit-details-marker{margin-right:6px}
.democard ol.steps{margin:0;padding:2px 10px 6px 34px;display:grid;gap:2px}
.democard ol.steps li strong{margin-right:8px}
.democard ol.steps li span{color:var(--c-muted)}
.democard code{color:var(--c-focus)}
.democard[open] ol.steps{padding-bottom:8px}
.badge{font-weight:700;letter-spacing:.08em;padding:0 4px;border:1px solid currentColor}
.badge.env-paper{color:var(--c-focus)}
main{padding:8px;display:grid;gap:8px}
.strip{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:var(--rule-strong);background:var(--c-panel)}
.metric{padding:4px 8px;border-right:var(--rule);min-width:0}
.metric:last-child{border-right:0}
.metric .label{font-size:10.5px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.05em}
.metric .value{font-size:17px;line-height:1.3;white-space:nowrap}
.metric .meta{font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.grid{display:grid;gap:8px;align-items:start;grid-template-columns:repeat(2,minmax(0,1fr))}
.panel{border:var(--rule-strong);background:var(--c-panel);min-width:0}
.panel>header{display:flex;gap:8px;align-items:center;justify-content:space-between;height:var(--row);padding:0 8px;border-bottom:var(--rule-strong);background:var(--c-raised)}
.panel>header h2{margin:0;font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.panel .body{padding:0 6px 4px;overflow-x:auto}
.panel h3{font-size:11px;font-weight:700;color:var(--c-muted);text-transform:uppercase;letter-spacing:.05em;margin:6px 0 2px}
.panel p{margin:4px 0}
.demo-tag{font-size:10px;letter-spacing:.06em;color:var(--c-muted);white-space:nowrap}
.empty{color:var(--c-muted);padding:6px 0}
table.data{width:100%;border-collapse:collapse;font-size:12px}
table.data th{height:var(--row);text-align:left;font-weight:500;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--c-muted);border-bottom:var(--rule-strong);padding:0 4px;white-space:nowrap}
table.data td{height:var(--row);padding:0 4px;border-bottom:var(--rule);vertical-align:middle;white-space:nowrap}
table.data td.n,table.data th.n{text-align:right}
table.data td[data-label=Reason]{width:45%;max-width:0;overflow:hidden;text-overflow:ellipsis}
table.data tbody tr:hover{background:var(--c-raised)}
.status{display:inline-flex;gap:4px;align-items:baseline;font-weight:600;white-space:nowrap}
.status.ok{color:var(--c-positive)} .status.bad{color:var(--c-negative)}
.status.warn,.status.info,.status.neutral{color:var(--c-muted)}
.reflections{list-style:none;margin:0;padding:0} .reflections li{padding:4px 0;border-bottom:var(--rule)} .reflections a{color:inherit}
.risk-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:4px 0}
.actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.actions .field input{font:inherit;background:var(--c-bg);color:var(--c-ink);border:var(--rule-strong);padding:0 6px;height:24px;width:180px;max-width:100%}
.action{display:inline-flex;gap:8px;align-items:center;height:24px;font:inherit;font-weight:700;color:var(--c-ink);background:var(--c-raised);border:var(--rule-strong);padding:0 10px;cursor:pointer}
.action .ctx{font-weight:400;color:var(--c-muted)}
.ticket fieldset{border:var(--rule-strong);margin:0 0 8px;padding:4px 8px} .ticket .leg{display:block;padding:2px 0} .ticket .why{color:var(--c-muted)}
.ticket select{font:inherit;background:var(--c-bg);color:var(--c-ink);border:var(--rule-strong);height:24px} .ticket input[type=number]{width:70px}
form.inline{display:inline-block;margin:0 4px 2px 0} form.inline .action .ctx{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.bar{display:inline-block;vertical-align:middle;width:32px;height:6px;margin-right:4px;background:var(--c-rule-strong)}
.bar>span{display:block;height:100%;background:var(--c-muted)}
.halt-note{color:var(--c-ink)} .halt-note strong{color:var(--c-negative)}
.chart-d{max-width:960px} .chart-m{display:none} svg text{font-family:var(--font-mono)}
@media (min-width:701px){table.data td .ccy{display:none}}  /* every amount is USD; the status bar says so */
.full{grid-column:1/-1}
.ctxbar strong{color:var(--c-focus)}
.stateline{margin:0;padding:2px 8px;border:var(--rule-strong);background:var(--c-panel);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.accounts tr.arow td:first-child a{color:inherit}
table.accounts tr.sel{background:var(--c-raised);box-shadow:inset 3px 0 0 var(--c-focus)}
table.accounts tr.sel td:first-child a{color:var(--c-focus);font-weight:700}
@media (min-width:701px){table.data td.n+td:not(.n),table.data th.n+th:not(.n){padding-left:14px}}
.panel[aria-label=Risk] td[data-label=State]{white-space:normal}
.panel[aria-label=Risk] td[data-label=State] .status{white-space:normal}
.filters{display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:4px 0}
.filters .filt{color:var(--c-muted);text-decoration:none;border:var(--rule-strong);padding:0 6px;line-height:20px;text-transform:uppercase;font-size:10.5px;letter-spacing:.04em}
.filters .filt.on{color:var(--c-ink);border-color:var(--c-focus)}
.filters .meta{margin-left:auto;font-size:10.5px}
.rticket fieldset{border:0;border-bottom:var(--rule);margin:0;padding:4px 0;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
.rticket legend{float:left;width:100%;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--c-muted)}
.rticket input,.rticket select,.rticket textarea{font:inherit;background:var(--c-bg);color:var(--c-ink);border:var(--rule-strong);padding:0 4px}
.rticket textarea{width:100%;max-width:100%;box-sizing:border-box}
.rticket .actions{padding:6px 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center} .rticket .actions .status{white-space:normal}
.rticket-msg{color:var(--c-ink);border-left:3px solid var(--c-focus);padding-left:6px}
@media (max-width:1100px){.strip{grid-template-columns:repeat(4,minmax(0,1fr))}.grid{grid-template-columns:minmax(0,1fr)}}
@media (max-width:700px){
.wide{display:none}
.strip{grid-template-columns:repeat(2,minmax(0,1fr))}
.metric:nth-child(2n){border-right:0} .metric{border-bottom:var(--rule)}
.chart-d{display:none} .chart-m{display:block}
.statusbar>*{padding:0 6px}
.action{height:auto;min-height:24px;flex-wrap:wrap;gap:0 8px;text-align:left}
table.data.stack thead{display:none}
table.data.stack,table.data.stack tbody,table.data.stack tr{display:block;width:100%}
table.data.stack tr{border-bottom:var(--rule-strong);padding:2px 0}
table.data.stack td{display:flex;justify-content:space-between;gap:12px;height:auto;min-height:22px;align-items:center;padding:0;border:0;text-align:right;white-space:normal}
table.data.stack td::before{content:attr(data-label);color:var(--c-muted);text-align:left;flex:none}
table.data.stack td:empty,table.data.stack td:has(>.nil:only-child){display:none} table.data.stack td .status{white-space:normal;text-align:right;min-width:0}
table.data.stack td[data-label=Reason]{display:block;text-align:left;width:auto;max-width:none}
table.data.stack td[data-label=Reason]::before{display:block}}
/* strategy studio (ALG-3256) */
.chk{white-space:nowrap}
.kv{display:inline-block;margin-right:8px;white-space:nowrap}
table.data td[data-label=Parameters],table.data td[data-label="Frozen params"]{white-space:normal;line-height:1.3;padding-top:2px;padding-bottom:2px}
@media (max-width:700px){table.data.stack td[data-label=Parameters],table.data.stack td[data-label="Frozen params"]{display:block;text-align:left}table.data.stack td[data-label=Parameters]::before,table.data.stack td[data-label="Frozen params"]::before{display:block}.chk{white-space:normal}.studio-form select{max-width:100%}}
.studio-form{display:grid;gap:4px;padding:4px 0}
.studio-form .row{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;border:0;margin:0;padding:0}
.studio-form legend{float:left;margin-right:8px}
.studio-form select,.studio-form input:not([type]),.studio-form input[name]{font:inherit;background:var(--c-bg);color:var(--c-ink);border:var(--rule-strong);padding:0 4px;height:22px}
.studio-form input[type=checkbox],.studio-form input[type=radio]{height:auto}
.flash{border:var(--rule-strong);padding:4px 8px} .flash.err{color:var(--c-negative)}
code{font-family:var(--font-mono)}
/* NoFX-pattern dashboard (ALG-3288): one overview screen, cards, tabs for drill-ins */
.dash{--font-sans:Inter,"Segoe UI",system-ui,-apple-system,Roboto,sans-serif;--s-laya:#3987e5;--s-jev:#d95926;--s-coin:#9085e9}
body.dash{font:14px/1.5 var(--font-sans)}
.dash .num,.dash .statusbar,.dash table.data,.dash .stateline{font-family:var(--font-mono)}
.dash main{padding:16px;gap:16px;max-width:1280px;margin:0 auto;width:100%}
.dash .panel{border-radius:10px;overflow:hidden}
.dash .panel>header{height:36px;padding:0 14px}
.dash .panel .body{padding:4px 14px 12px}
.dash .stateline{border-radius:8px}
.switcher{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.switcher .acct{color:var(--c-muted);text-decoration:none;border:var(--rule-strong);border-radius:999px;padding:2px 12px;font-size:13px}
.switcher .acct.sel{color:var(--c-ink);border-color:var(--c-focus);background:var(--c-raised);font-weight:600}
.switcher .acct:focus-visible{outline:2px solid var(--c-focus);outline-offset:2px}
.tabs{display:flex;flex-wrap:wrap;gap:2px;border-bottom:var(--rule-strong)}
.tabs a{color:var(--c-muted);text-decoration:none;padding:8px 14px;border-bottom:2px solid transparent;margin-bottom:-1px;font-size:13.5px}
.tabs a.on{color:var(--c-ink);border-bottom-color:var(--c-focus);font-weight:600}
.tabs a .count{display:inline-block;margin-left:6px;padding:0 6px;border-radius:999px;background:var(--c-attention);color:#111;font-size:11px;font-weight:700}
.hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,2fr);gap:16px;align-items:stretch}
.hero .lede{background:var(--c-panel);border:var(--rule-strong);border-radius:10px;padding:16px 18px}
.hero .lede h2{margin:0 0 6px;font-size:13px;font-weight:600;color:var(--c-muted);text-transform:uppercase;letter-spacing:.06em}
.hero .lede p{margin:0 0 10px;font-size:15px;line-height:1.55}
.hero .lede ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.hero .lede li{display:flex;gap:8px;align-items:baseline}
.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.tile{background:var(--c-panel);border:var(--rule-strong);border-radius:10px;padding:14px 16px;min-width:0}
.tile .label{font-size:12px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.05em}
.tile .value{font-size:28px;line-height:1.25;font-family:var(--font-mono);white-space:nowrap}
.tile .meta{font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{display:grid;gap:8px;color:var(--c-ink);text-decoration:none;background:var(--c-panel);border:var(--rule-strong);border-radius:10px;padding:14px 16px;box-shadow:inset 4px 0 0 var(--series,var(--c-muted))}
.card:hover{background:var(--c-raised)} .card.sel{border-color:var(--c-focus)}
.card .top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.card .name{font-weight:600;font-size:15px}
.card .eq{font-family:var(--font-mono);font-size:24px}
.card .facts{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--c-muted)}
.card .facts strong{color:var(--c-ink);font-weight:600}
.card .open{font-size:12.5px;color:var(--c-focus)}
.spark{width:100%;height:48px;display:block}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
.feed{list-style:none;margin:0;padding:0}
.feed li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;padding:7px 0;border-bottom:var(--rule);align-items:baseline}
.feed li:last-child{border-bottom:0}
.feed .what{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:var(--c-muted);margin:4px 0}
.legend i{display:inline-block;width:18px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.chartbox{position:relative}
.tip{position:absolute;pointer-events:none;background:var(--c-raised);border:var(--rule-strong);border-radius:6px;padding:6px 8px;font:12px/1.4 var(--font-mono);white-space:nowrap;display:none;z-index:1}
.more{font-size:13px}
@media (max-width:1100px){.hero{grid-template-columns:minmax(0,1fr)}.pair{grid-template-columns:minmax(0,1fr)}}
@media (max-width:700px){.dash main{padding:10px;gap:12px}.tile .value{font-size:22px}.tabs{flex-wrap:nowrap;overflow-x:auto}.tabs a{white-space:nowrap;padding:8px 10px}}
"""

# Ticks the status-bar UTC clock; the server-rendered value stands if JS is off.
CLOCK = """
(function(){var el=document.getElementById("utc");if(!el)return;
function t(){el.textContent=new Date().toISOString().slice(11,19)+"Z";}t();setInterval(t,1000);})();
"""

# Account switcher: ←/→ (or ↑/↓) moves between pills, Enter (or a click) sets
# ?account=. Switching blanks the view first (state line -> LOADING) so the
# prior account's rows are never on screen while the next context loads.
KEYS = """
(function(){var rows=[].slice.call(document.querySelectorAll(".acct[data-href]"));if(!rows.length)return;
function go(r){var s=document.getElementById("state");if(s){s.dataset.state="loading";s.textContent="LOADING · "+r.dataset.account;}
[].forEach.call(document.querySelectorAll(".view"),function(n){n.hidden=true;});location.href=r.dataset.href;}
rows.forEach(function(r,i){r.addEventListener("click",function(ev){ev.preventDefault();go(r);});
r.addEventListener("keydown",function(ev){var k=ev.key;if(k==="Enter"){ev.preventDefault();go(r);}
else if(/^Arrow(Down|Up|Left|Right)$/.test(k)){ev.preventDefault();var f=k==="ArrowDown"||k==="ArrowRight";rows[(i+(f?1:rows.length-1))%rows.length].focus();}});});
var sel=document.querySelector(".acct.sel");if(sel&&location.hash!=="#nofocus")sel.focus({preventScroll:true});})();
"""

# Equity chart hover: vertical crosshair + tooltip with every series at the
# nearest interval. Points live in data-pts as [x, label, [name, value]...].
HOVER = """
(function(){[].forEach.call(document.querySelectorAll(".chartbox"),function(box){
var svg=box.querySelector("svg[data-pts]");if(!svg)return;var pts=JSON.parse(svg.dataset.pts),tip=box.querySelector(".tip"),ln=svg.querySelector(".xhair");
function hide(){tip.style.display="none";ln.setAttribute("visibility","hidden");}
svg.addEventListener("mouseleave",hide);svg.addEventListener("mousemove",function(ev){var p=svg.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;
var x=p.matrixTransform(svg.getScreenCTM().inverse()).x,best=pts[0];pts.forEach(function(q){if(Math.abs(q[0]-x)<Math.abs(best[0]-x))best=q;});
ln.setAttribute("x1",best[0]);ln.setAttribute("x2",best[0]);ln.setAttribute("visibility","visible");
tip.textContent="";var h=document.createElement("div");h.textContent=best[1];h.className="meta";tip.appendChild(h);
best.slice(2).forEach(function(s){var d=document.createElement("div");d.textContent=s[0]+"  "+s[1]+" USD";tip.appendChild(d);});
var r=box.getBoundingClientRect();tip.style.display="block";var left=ev.clientX-r.left+12;if(left+tip.offsetWidth>r.width)left=ev.clientX-r.left-tip.offsetWidth-12;
tip.style.left=left+"px";tip.style.top="8px";});});})();
"""
