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
table.accounts tr.acct{cursor:pointer}
table.accounts tr.acct:focus-visible{outline:2px solid var(--c-focus);outline-offset:-2px}
.stateline{margin:0;padding:2px 8px;border:var(--rule-strong);background:var(--c-panel);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.accounts tr.acct td:first-child a{color:inherit;text-decoration:none}
table.accounts tr.sel{background:var(--c-raised);box-shadow:inset 3px 0 0 var(--c-focus)}
table.accounts tr.sel td:first-child a{color:var(--c-focus);font-weight:700}
@media (min-width:701px){table.data td.n+td:not(.n),table.data th.n+th:not(.n){padding-left:14px}}
.panel[aria-label=Risk] td[data-label=State]{white-space:normal}
.panel[aria-label=Risk] td[data-label=State] .status{white-space:normal}
.filters{display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:4px 0}
.filters .filt{color:var(--c-muted);text-decoration:none;border:var(--rule-strong);padding:0 6px;line-height:20px;text-transform:uppercase;font-size:10.5px;letter-spacing:.04em}
.filters .filt.on{color:var(--c-ink);border-color:var(--c-focus)}
.filters .meta{margin-left:auto;font-size:10.5px}
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
"""

# Ticks the status-bar UTC clock; the server-rendered value stands if JS is off.
CLOCK = """
(function(){var el=document.getElementById("utc");if(!el)return;
function t(){el.textContent=new Date().toISOString().slice(11,19)+"Z";}t();setInterval(t,1000);})();
"""

# Accounts pane: ↑/↓ moves between rows, Enter (or a click) sets ?account=.
# Switching blanks every pane first (state line -> LOADING) so the prior
# account's rows are never on screen while the next context loads.
KEYS = """
(function(){var rows=[].slice.call(document.querySelectorAll("tr.acct"));if(!rows.length)return;
function go(r){var s=document.getElementById("state");if(s){s.dataset.state="loading";s.textContent="LOADING · "+r.dataset.account;}
[].forEach.call(document.querySelectorAll(".grid,.strip"),function(n){n.hidden=true;});location.href=r.dataset.href;}
rows.forEach(function(r,i){r.addEventListener("click",function(ev){if(ev.target.closest("a"))return;go(r);});
r.addEventListener("keydown",function(ev){var k=ev.key;if(k==="Enter"){go(r);}
else if(k==="ArrowDown"||k==="ArrowUp"){ev.preventDefault();var n=rows[(i+(k==="ArrowDown"?1:rows.length-1))%rows.length];n.focus();}});});
var sel=document.querySelector("tr.acct.sel");if(sel&&location.hash!=="#nofocus")sel.focus({preventScroll:true});})();
"""
