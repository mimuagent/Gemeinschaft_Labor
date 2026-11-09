#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build-Skript für die lokale Website des Projekts
„Labor für neue menschliche Gemeinschaften“.

Aufruf (im Ordner dieses Skripts):   python build.py
Liest alle Unterordner von laeufe/ und schreibt website.html neu.
Nur Python-Standardbibliothek. Läuft unter Linux und Windows.

Die Website zeigt ausschließlich, was in den Dateien steht. Fehlende oder
fehlerhafte Dateien werden als Hinweis auf der Seite angezeigt; der Build
bricht deswegen nicht ab.
"""
import datetime
import json
import os
import re
import sys
import urllib.parse

HIER = os.path.dirname(os.path.abspath(__file__))
LAEUFE = os.path.join(HIER, "laeufe")
AUSGABE = os.path.join(HIER, "website.html")
VIS_REL = "lib/vis-network.min.js"

MD_REIHENFOLGE = ["1-analytiker.md", "2-format.md", "3-katalog.md", "4-emotionen.md",
                  "5-simulation.md", "6-gesamtdokument.md", "summary.md", "bilder.md"]
MD_ROLLEN = {
    "1-analytiker.md": "Interessen-Analytiker",
    "2-format.md": "Format-Entwerfer",
    "3-katalog.md": "Beziehungs-Architekt",
    "4-emotionen.md": "Emotions-Kurator",
    "5-simulation.md": "Simulations-Choreograph",
    "6-gesamtdokument.md": "Master-Koordinator (Gesamtdokument)",
    "summary.md": "Master-Koordinator (Summary)",
    "bilder.md": "Bildliste aller Bots",
}
JSON_DATEIEN = ["lauf.json", "katalog.json", "klick.json", "phasen.json"]
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp")

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def lies_text(pfad, hinweise, anzeige):
    """Liest eine Textdatei. Gibt None zurück, wenn sie nicht lesbar ist."""
    try:
        with open(pfad, "rb") as f:
            roh = f.read()
    except Exception as e:
        hinweise.append(f"{anzeige}: konnte nicht gelesen werden ({e}).")
        return None
    try:
        return roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        hinweise.append(f"{anzeige}: ist nicht UTF-8-kodiert, wurde als Windows-1252 gelesen.")
        return roh.decode("cp1252", errors="replace")


def lies_json(pfad, hinweise, anzeige):
    text = lies_text(pfad, hinweise, anzeige)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception as e:
        hinweise.append(f"{anzeige}: ist kein gültiges JSON ({e}). Inhalt wird nicht ausgewertet.")
        return None


def parse_zeit(wert):
    """Versucht, eine Zeitangabe zu lesen. Gibt ISO-String (UTC) oder None zurück."""
    if wert is None:
        return None
    if isinstance(wert, (int, float)):
        try:
            ts = wert / 1000 if wert > 1e11 else wert
            return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()
        except Exception:
            return None
    s = str(wert).strip()
    if not s:
        return None
    s0 = re.sub(r"\s*\(.*?\)\s*$", "", s)
    kandidaten = [s, s0, s.replace("Z", "+00:00"), s.replace(" ", "T", 1)]
    for k in kandidaten:
        try:
            dt = datetime.datetime.fromisoformat(k)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
            return dt.astimezone(datetime.timezone.utc).isoformat()
        except Exception:
            pass
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\D+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        try:
            dt = datetime.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                                   int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0),
                                   tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
            return dt.astimezone(datetime.timezone.utc).isoformat()
        except Exception:
            pass
    return None


def finde_feld(d, muster):
    """Erster Wert, dessen Schlüssel (ohne Groß/Klein) einem der Muster entspricht."""
    if not isinstance(d, dict):
        return None
    for m in muster:
        for k, v in d.items():
            if re.fullmatch(m, str(k), flags=re.I):
                return v
    return None


def rel_url(*teile):
    return "/".join(urllib.parse.quote(t) for t in teile)


# ---------- bilder.md tolerant lesen ----------
FELD_SCHLUESSEL = {
    "datei": r"(datei(name)?|bild|file(name)?|name)",
    "rolle": r"(rolle(nname)?|bot|von|autor)",
    "begruendung": r"(begr(ü|ue)ndung|grund|warum|zweck|beschreibung)",
    "quelle": r"(quelle|source|herkunft|url|link)",
}


def parse_bilder_md(text, bilddateien):
    eintraege = []
    namen_lc = {b.lower(): b for b in bilddateien}
    for zeile in text.splitlines():
        roh = zeile.strip()
        if not roh or roh.startswith("#"):
            continue
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", roh):
            continue  # Tabellen-Trennzeile
        z = re.sub(r"^([-*+]|\d+[.)])\s+", "", roh)
        if "|" in z:
            zellen = [c.strip() for c in z.strip().strip("|").split("|")]
        else:
            zellen = None
            for trenner in ["\t", " ; ", ";", " – ", " — ", " - ", ", "]:
                if trenner in z:
                    zellen = [c.strip() for c in z.split(trenner)]
                    break
            if zellen is None:
                zellen = [z]
        zellen = [c for c in zellen if c != ""]
        # Kopfzeile einer Tabelle überspringen
        if all(re.fullmatch(r"\W*" + "|".join(FELD_SCHLUESSEL.values()) + r"\W*", c, flags=re.I)
               for c in zellen if c) and len(zellen) >= 2:
            continue
        e = {"datei": None, "rolle": None, "begruendung": None, "quelle": None, "roh": roh}
        rest = []
        for c in zellen:
            m = re.match(r"\**\s*([A-Za-zÄÖÜäöüß]+)\s*\**\s*[:=]\s*(.*)$", c)
            gesetzt = False
            if m:
                for feld, rx in FELD_SCHLUESSEL.items():
                    if re.fullmatch(rx, m.group(1), flags=re.I) and e[feld] is None:
                        e[feld] = m.group(2).strip().strip("*`").strip()
                        gesetzt = True
                        break
            if not gesetzt:
                rest.append(c)
        # Dateiname: Zelle mit Bild-Endung oder bekanntem Namen
        if e["datei"] is None:
            for i, c in enumerate(rest):
                c2 = c.strip("`*[]() ")
                basis = c2.replace("\\", "/").split("/")[-1]
                if basis.lower() in namen_lc or basis.lower().endswith(BILD_ENDUNGEN):
                    e["datei"] = basis
                    rest.pop(i)
                    break
        else:
            e["datei"] = e["datei"].strip("`*[]() ").replace("\\", "/").split("/")[-1]
        if e["datei"] is None:
            # Name irgendwo in der Zeile?
            for b in bilddateien:
                if b.lower() in roh.lower():
                    e["datei"] = b
                    break
        if e["datei"] is None and not rest:
            continue
        for feld in ["rolle", "begruendung", "quelle"]:
            if e[feld] is None and rest:
                e[feld] = rest.pop(0)
        if rest:
            e["quelle"] = " | ".join([e["quelle"]] + rest) if e["quelle"] else " | ".join(rest)
        if e["datei"] and e["datei"].lower() in namen_lc:
            e["datei"] = namen_lc[e["datei"].lower()]
        eintraege.append(e)
    return eintraege


def lies_lauf(name):
    ordner = os.path.join(LAEUFE, name)
    hinweise = []
    lauf = {"ordner": name, "hinweise": hinweise, "json": {}, "md": [], "bilder": [],
            "bilder_md": None, "fehlend": []}
    try:
        inhalt = sorted(os.listdir(ordner))
    except Exception as e:
        hinweise.append(f"Ordner konnte nicht gelesen werden ({e}).")
        inhalt = []
    for jd in JSON_DATEIEN:
        p = os.path.join(ordner, jd)
        if os.path.isfile(p):
            lauf["json"][jd] = lies_json(p, hinweise, jd)
            if lauf["json"][jd] is None:
                lauf["json"][jd + "_fehler"] = True
        else:
            lauf["json"][jd] = None
            lauf["fehlend"].append(jd)
    md_dateien = [f for f in inhalt if f.lower().endswith(".md") and os.path.isfile(os.path.join(ordner, f))]
    reihenfolge = [f for f in MD_REIHENFOLGE] + sorted(f for f in md_dateien if f not in MD_REIHENFOLGE)
    for f in reihenfolge:
        p = os.path.join(ordner, f)
        if f in md_dateien:
            text = lies_text(p, hinweise, f)
            lauf["md"].append({"datei": f, "rolle": MD_ROLLEN.get(f, ""), "text": text,
                               "geliefert": text is not None})
        else:
            lauf["md"].append({"datei": f, "rolle": MD_ROLLEN.get(f, ""), "text": None, "geliefert": False})
            lauf["fehlend"].append(f)
    # Bilder
    bordner = os.path.join(ordner, "bilder")
    bilddateien = []
    if os.path.isdir(bordner):
        try:
            bilddateien = sorted(f for f in os.listdir(bordner)
                                 if f.lower().endswith(BILD_ENDUNGEN) and os.path.isfile(os.path.join(bordner, f)))
            andere = sorted(f for f in os.listdir(bordner) if f not in bilddateien)
            if andere:
                hinweise.append("bilder/: Dateien ohne Bild-Endung werden nicht angezeigt: " + ", ".join(andere))
        except Exception as e:
            hinweise.append(f"bilder/: konnte nicht gelesen werden ({e}).")
    else:
        lauf["fehlend"].append("bilder/")
    eintraege = []
    bmd = next((m for m in lauf["md"] if m["datei"] == "bilder.md"), None)
    if bmd and bmd["text"] is not None:
        try:
            eintraege = parse_bilder_md(bmd["text"], bilddateien)
        except Exception as e:
            hinweise.append(f"bilder.md: konnte nicht ausgewertet werden ({e}).")
    benutzt = set()
    for b in bilddateien:
        passend = [e for e in eintraege if e["datei"] == b]
        for e in passend:
            benutzt.add(id(e))
        lauf["bilder"].append({"datei": b, "src": rel_url("laeufe", name, "bilder", b),
                               "angaben": passend})
    lauf["bilder_ohne_datei"] = [e for e in eintraege if id(e) not in benutzt]
    lauf["bilder_md_geliefert"] = bool(bmd and bmd["geliefert"])
    # Start-Zeit
    lj = lauf["json"].get("lauf.json")
    startwert = finde_feld(lj, [r"start", r"start.?zeit", r"startzeit", r"beginn", r"started?_?at", r"start.*"])
    lauf["start_iso"] = parse_zeit(startwert)
    if startwert is not None and lauf["start_iso"] is None:
        hinweise.append(f"lauf.json: Start-Zeit „{startwert}“ konnte nicht gelesen werden; sortiert wird nach Ordnername.")
    titel = finde_feld(lj, [r"laufname", r"lauf.?name", r"name", r"titel"])
    lauf["titel"] = str(titel) if titel not in (None, "") else name
    lauf["hinweis_beispiel"] = finde_feld(lj, [r"hinweis"])
    return lauf


def main():
    laeufe = []
    globale_hinweise = []
    if not os.path.isdir(LAEUFE):
        globale_hinweise.append("Der Ordner laeufe/ wurde nicht gefunden.")
    else:
        for name in sorted(os.listdir(LAEUFE)):
            if os.path.isdir(os.path.join(LAEUFE, name)) and not name.startswith("."):
                try:
                    laeufe.append(lies_lauf(name))
                except Exception as e:
                    laeufe.append({"ordner": name, "titel": name, "hinweise": [f"Unerwarteter Fehler beim Lesen: {e}"],
                                   "json": {}, "md": [], "bilder": [], "bilder_ohne_datei": [], "fehlend": [],
                                   "start_iso": None, "bilder_md_geliefert": False, "hinweis_beispiel": None})
    # neuester zuerst: zuerst Läufe mit Start-Zeit (absteigend), dann übrige nach Ordnername absteigend
    mit = sorted([l for l in laeufe if l.get("start_iso")], key=lambda l: (l["start_iso"], l["ordner"]), reverse=True)
    ohne = sorted([l for l in laeufe if not l.get("start_iso")], key=lambda l: l["ordner"], reverse=True)
    laeufe = mit + ohne

    daten = {"laeufe": laeufe, "hinweise": globale_hinweise,
             "erzeugt": datetime.datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M (%Z)"),
             "vis_vorhanden": os.path.isfile(os.path.join(HIER, *VIS_REL.split("/")))}
    if not daten["vis_vorhanden"]:
        globale_hinweise.append(f"{VIS_REL} fehlt: Landkarte und Simulation können nicht gezeichnet werden.")
    js = json.dumps(daten, ensure_ascii=False, indent=None)
    js = js.replace("</", "<\\/").replace("<!--", "<\\!--")
    html = VORLAGE.replace("__VIS__", VIS_REL).replace("__DATEN__", js)
    tmp = AUSGABE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    os.replace(tmp, AUSGABE)
    print(f"website.html geschrieben: {len(laeufe)} Lauf/Läufe.")
    for l in laeufe:
        print(f"  - {l['ordner']}: {len(l['hinweise'])} Hinweis(e), fehlend: {', '.join(l['fehlend']) or 'nichts'}")
    for h in globale_hinweise:
        print("  Hinweis:", h)


VORLAGE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Labor für neue menschliche Gemeinschaften</title>
<script src="__VIS__"></script>
<style>
 *{box-sizing:border-box}
 body{font-family:system-ui,"Segoe UI",sans-serif;margin:0;color:#222;background:#fafafa;line-height:1.5}
 .wrap{max-width:1150px;margin:0 auto;padding:0 1rem}
 header{background:#fff;border-bottom:1px solid #ddd;padding:.9rem 0}
 h1{font-size:1.35rem;margin:0}
 .meta{color:#666;font-size:.88rem}
 .leiste{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin-top:.5rem}
 select,button{font:inherit;padding:.35rem .7rem}
 button{background:#2b4c7e;color:#fff;border:none;border-radius:4px;cursor:pointer}
 button:disabled{background:#999;cursor:default}
 button.hell{background:#e4e9f2;color:#222}
 nav{background:#2b4c7e}
 nav .wrap{display:flex;flex-wrap:wrap}
 nav a{color:#fff;padding:.65rem 1rem;cursor:pointer;text-decoration:none}
 nav a.active{background:#fafafa;color:#2b4c7e;font-weight:600}
 section{display:none;padding:1rem 0 3rem}
 section.active{display:block}
 .karte{background:#fff;border:1px solid #ddd;border-radius:6px;padding:1rem;margin:.8rem 0}
 .karte h3{margin:.1rem 0 .6rem;font-size:1.05rem}
 .fehlt{color:#9a3a00;background:#fff4e5;border:1px solid #f0c48a;border-radius:6px;padding:.6rem .8rem;margin:.6rem 0}
 .hinweis{color:#7a5b00;background:#fffbe6;border:1px solid #e6d58a;border-radius:6px;padding:.6rem .8rem;margin:.6rem 0}
 .beispiel{background:#ffe9e9;border:1px solid #e3a0a0;color:#7a1f1f;border-radius:6px;padding:.6rem .8rem;margin:.6rem 0;font-weight:600}
 .note{color:#666;font-size:.9rem}
 table.felder{border-collapse:collapse;width:100%}
 table.felder td,table.felder th{border-top:1px solid #eee;padding:.35rem .5rem;vertical-align:top;text-align:left}
 table.felder th{width:28%;color:#444;font-weight:600}
 .netz{width:100%;height:520px;border:1px solid #ddd;border-radius:6px;background:#fff}
 .zweispaltig{display:grid;grid-template-columns:2fr 1fr;gap:1rem}
 @media(max-width:850px){.zweispaltig{grid-template-columns:1fr}}
 .legende span{display:inline-block;margin:.15rem .5rem .15rem 0;cursor:pointer}
 .punkt{display:inline-block;width:.8rem;height:.8rem;border-radius:50%;vertical-align:middle;margin-right:.3rem}
 .klick{border-left:4px solid #2b4c7e;padding:.3rem .7rem;margin:.6rem 0;background:#f4f6fa}
 .phasen li{cursor:pointer;padding:.2rem .3rem;border-radius:4px}
 .phasen li.aktiv{background:#e4e9f2;font-weight:600}
 .galerie{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:1rem}
 .galerie figure{margin:0;background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden}
 .galerie img{width:100%;height:190px;object-fit:cover;display:block;cursor:zoom-in;background:#eee}
 .galerie figcaption{padding:.6rem .7rem;font-size:.9rem;overflow-wrap:anywhere}
 .md,.karte{overflow-wrap:anywhere}
 #gross{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:100;align-items:center;justify-content:center;flex-direction:column;cursor:zoom-out}
 #gross img{max-width:94vw;max-height:86vh;background:#fff}
 #gross div{color:#fff;margin-top:.6rem;font-size:.95rem;max-width:90vw;text-align:center}
 .md h1{font-size:1.3rem}.md h2{font-size:1.15rem}.md h3{font-size:1.05rem}
 .md pre{background:#f3f3f3;padding:.6rem;overflow:auto}
 .md code{background:#f3f3f3;padding:0 .2rem}
 .md blockquote{border-left:4px solid #ccc;margin:.5rem 0;padding:.1rem .8rem;color:#555}
 .md table{border-collapse:collapse}.md td,.md th{border:1px solid #ddd;padding:.3rem .5rem}
 .md img{max-width:100%}
 a{color:#1f5fbf}
 .inhalt a{margin-right:.8rem}
 .ok{color:#2a7a2a}.nein{color:#9a3a00}
</style>
</head>
<body>
<header><div class="wrap">
 <h1>Labor für neue menschliche Gemeinschaften</h1>
 <div class="leiste">
  <label>Lauf: <select id="laufwahl"></select></label>
  <span class="meta" id="erzeugt"></span>
 </div>
 <div class="meta">Diese Seite zeigt nur, was in den Dateien des Laufordners steht. Fehlende Dateien sind als „nicht geliefert“ markiert.</div>
</div></header>
<nav><div class="wrap">
 <a data-tab="uebersicht">Übersicht</a>
 <a data-tab="karte">Landkarte</a>
 <a data-tab="simulation">Simulation</a>
 <a data-tab="bilder">Bilder</a>
 <a data-tab="ausgaben">Bot-Ausgaben</a>
</div></nav>
<main class="wrap">
 <div id="global"></div>
 <section id="uebersicht"></section>
 <section id="karte"></section>
 <section id="simulation"></section>
 <section id="bilder"></section>
 <section id="ausgaben"></section>
</main>
<div id="gross"><img alt=""><div></div></div>
<script>
const DATEN = __DATEN__;
</script>
<script>
"use strict";
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const FARBEN=["#e8a33d","#5aa469","#4f86c6","#c45b8e","#8e6cc4","#d0603f","#3fa7a3","#a3a33f","#7a7a7a","#c4a35b"];
const NEUTRAL="#c9c9c9";
let lauf=null, tab="uebersicht", netz=null, simNetz=null, simTimer=null, simIndex=0, simPos={};

/* ---------- Mini-Markdown ---------- */
function urlFuer(u){
  u=u.trim();
  if(/^(https?:|mailto:|file:|#|data:image\/)/i.test(u)) return u;
  if(/^javascript:/i.test(u)) return "#";
  if(/^[a-z]:[\\/]/i.test(u)||u.startsWith("/")) return u;
  return "laeufe/"+encodeURIComponent(lauf.ordner)+"/"+u.split("/").map(encodeURIComponent).join("/");
}
function inline(t){
  let s=esc(t), codes=[];
  s=s.replace(/`([^`]+)`/g,(m,c)=>{codes.push(c);return "\u0000"+(codes.length-1)+"\u0000";});
  s=s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,(m,a,u)=>{const x=urlFuer(u.replace(/&amp;/g,"&"));
    return /^https?:/i.test(x)?`<a href="${esc(x)}" target="_blank" rel="noopener">[externes Bild${a?": "+a:""}]</a>`:`<img alt="${a}" src="${esc(x)}">`;});
  s=s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^)]*&quot;)?\)/g,(m,a,u)=>`<a href="${esc(urlFuer(u.replace(/&amp;/g,"&")))}" target="_blank" rel="noopener">${a}</a>`);
  s=s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,;:!?„“"])/g,(m,p,u)=>`${p}<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
  s=s.replace(/&lt;(https?:\/\/[^\s&]+)&gt;/g,(m,u)=>`<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
  s=s.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>").replace(/__([^_]+)__/g,"<strong>$1</strong>");
  s=s.replace(/(^|[^*\w])\*([^*\s][^*]*)\*/g,"$1<em>$2</em>");
  s=s.replace(/~~([^~]+)~~/g,"<del>$1</del>");
  s=s.replace(/\u0000(\d+)\u0000/g,(m,i)=>`<code>${codes[+i]}</code>`);
  return s;
}
function markdown(text){
  const z=String(text).replace(/\r\n?/g,"\n").split("\n"); let out=[], i=0;
  const istTabZeile=l=>/^\s*\|.*\|\s*$/.test(l)||(/\|/.test(l)&&/^\s*\|?\s*:?-{2,}/.test(l));
  while(i<z.length){
    let l=z[i];
    if(/^\s*```/.test(l)){let b=[];i++;while(i<z.length&&!/^\s*```/.test(z[i]))b.push(z[i++]);i++;out.push(`<pre><code>${esc(b.join("\n"))}</code></pre>`);continue;}
    if(/^\s*$/.test(l)){i++;continue;}
    let m;
    if(m=l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/)){const n=Math.min(m[1].length+1,6);out.push(`<h${n}>${inline(m[2])}</h${n}>`);i++;continue;}
    if(/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)){out.push("<hr>");i++;continue;}
    if(/^\s*>/.test(l)){let b=[];while(i<z.length&&/^\s*>/.test(z[i]))b.push(z[i++].replace(/^\s*>\s?/,""));out.push(`<blockquote>${markdown(b.join("\n"))}</blockquote>`);continue;}
    if(/\|/.test(l)&&i+1<z.length&&/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(z[i+1])){
      const zellen=r=>r.trim().replace(/^\|/,"").replace(/\|$/,"").split("|").map(c=>inline(c.trim()));
      let h=zellen(l);i+=2;let rows=[];
      while(i<z.length&&/\|/.test(z[i])&&!/^\s*$/.test(z[i]))rows.push(zellen(z[i++]));
      out.push(`<table><thead><tr>${h.map(c=>`<th>${c}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`);continue;}
    if(/^\s*([-*+]|\d+[.)])\s+/.test(l)){
      const geordnet=/^\s*\d+[.)]/.test(l);let items=[];
      while(i<z.length&&(/^\s*([-*+]|\d+[.)])\s+/.test(z[i])||(/^\s{2,}\S/.test(z[i])&&items.length))){
        if(/^\s*([-*+]|\d+[.)])\s+/.test(z[i]))items.push(z[i].replace(/^\s*([-*+]|\d+[.)])\s+/,""));else items[items.length-1]+="\n"+z[i].trim();i++;}
      const tag=geordnet?"ol":"ul";
      out.push(`<${tag}>${items.map(t=>`<li>${inline(t).replace(/\n/g,"<br>")}</li>`).join("")}</${tag}>`);continue;}
    let b=[];
    while(i<z.length&&!/^\s*$/.test(z[i])&&!/^(#{1,6})\s/.test(z[i])&&!/^\s*```/.test(z[i])&&!/^\s*>/.test(z[i])&&!(b.length&&/^\s*([-*+]|\d+[.)])\s+/.test(z[i])))b.push(z[i++]);
    out.push(`<p>${b.map(inline).join("<br>")}</p>`);
  }
  return out.join("\n");
}

/* ---------- Hilfen ---------- */
const nichtGeliefert=d=>`<div class="fehlt"><strong>${esc(d)}</strong>: nicht geliefert.</div>`;
const fehlerhaft=d=>`<div class="fehlt"><strong>${esc(d)}</strong>: geliefert, aber fehlerhaft (siehe Hinweise in der Übersicht).</div>`;
function jsonStatus(name){const j=lauf.json||{};if(j[name+"_fehler"])return "fehler";if(j[name]==null)return "fehlt";return "ok";}
function arr(o,...keys){if(!o||typeof o!=="object")return [];for(const k of keys){if(Array.isArray(o[k]))return o[k];}return [];}
function feld(o,...keys){if(!o||typeof o!=="object")return undefined;for(const k of keys){if(o[k]!=null)return o[k];}return undefined;}
function wertHtml(v){
  if(v==null)return '<span class="note">leer</span>';
  if(Array.isArray(v))return v.length&&v.every(x=>typeof x!=="object")?esc(v.join(", ")):`<pre>${esc(JSON.stringify(v,null,2))}</pre>`;
  if(typeof v==="object")return `<table class="felder">${Object.entries(v).map(([k,x])=>`<tr><th>${esc(k)}</th><td>${wertHtml(x)}</td></tr>`).join("")}</table>`;
  return inline(String(v));
}
function katalog(){
  const k=(lauf.json||{})["katalog.json"];
  const knoten=arr(k,"knoten","nodes"), kanten=arr(k,"kanten","edges"), cluster=arr(k,"cluster","clusters");
  return {knoten,kanten,cluster};
}
function klickDaten(){const k=(lauf.json||{})["klick.json"];return {klick:arr(k,"klick","klickinhalte","clicks"),stimmung:feld(k,"stimmung","Stimmung")};}
function phasenDaten(){const p=(lauf.json||{})["phasen.json"];return {phasen:arr(p,"phasen","phases"),hinweis:feld(p,"hinweis","Hinweis")};}
function clusterVon(id,cluster){return cluster.filter(c=>arr(c,"knoten","nodes","ids").map(String).includes(String(id)));}
function clusterFarbe(cid,cluster){const i=cluster.findIndex(c=>String(c.id)===String(cid));return i<0?NEUTRAL:FARBEN[i%FARBEN.length];}

/* ---------- Übersicht ---------- */
function zeigeUebersicht(){
  const lj=lauf.json["lauf.json"]; let h="";
  if(lauf.hinweis_beispiel)h+=`<div class="beispiel">Hinweis: ${esc(lauf.hinweis_beispiel)}</div>`;
  h+=`<div class="karte"><h3>Laufdaten (lauf.json)</h3>`;
  const st=jsonStatus("lauf.json");
  h+= st==="ok"? (typeof lj==="object"&&!Array.isArray(lj)?`<table class="felder">${Object.entries(lj).map(([k,v])=>`<tr><th>${esc(k)}</th><td>${wertHtml(v)}</td></tr>`).join("")}</table>`:wertHtml(lj)) : (st==="fehlt"?nichtGeliefert("lauf.json"):fehlerhaft("lauf.json"));
  h+=`<p class="note">Ordner: laeufe/${esc(lauf.ordner)}</p></div>`;
  const s=lauf.md.find(m=>m.datei==="summary.md");
  h+=`<div class="karte"><h3>Summary (summary.md)</h3>${s&&s.geliefert?`<div class="md">${markdown(s.text)}</div>`:nichtGeliefert("summary.md")}</div>`;
  const alle=["lauf.json","katalog.json","klick.json","phasen.json"].map(d=>[d,jsonStatus(d)]).concat(lauf.md.map(m=>[m.datei,m.geliefert?"ok":"fehlt"])).concat([["bilder/",lauf.fehlend.includes("bilder/")?"fehlt":"ok"]]);
  h+=`<div class="karte"><h3>Dateien im Laufordner</h3><table class="felder">${alle.map(([d,s])=>`<tr><th>${esc(d)}</th><td class="${s==="ok"?"ok":"nein"}">${s==="ok"?"geliefert":s==="fehler"?"fehlerhaft":"nicht geliefert"}</td></tr>`).join("")}</table></div>`;
  const hw=pruefHinweise();
  h+=`<div class="karte"><h3>Hinweise</h3>${hw.length?hw.map(x=>`<div class="hinweis">${esc(x)}</div>`).join(""):'<p class="note">Keine Hinweise.</p>'}</div>`;
  $("#uebersicht").innerHTML=h;
}
function pruefHinweise(){
  const h=[...(lauf.hinweise||[])];
  const {knoten,kanten,cluster}=katalog(); const ids=new Set([...knoten,...kanten,...cluster].map(x=>String(x.id)));
  const knIds=new Set(knoten.map(n=>String(n.id)));
  kanten.forEach(e=>{if(!knIds.has(String(e.from))||!knIds.has(String(e.to)))h.push(`katalog.json: Kante ${e.id} verweist auf einen unbekannten Knoten (${e.from} → ${e.to}).`);});
  cluster.forEach(c=>arr(c,"knoten","nodes","ids").forEach(n=>{if(!knIds.has(String(n)))h.push(`katalog.json: Cluster ${c.id} nennt unbekannten Knoten ${n}.`);}));
  if(jsonStatus("katalog.json")==="ok"){
    klickDaten().klick.forEach(c=>arr(c,"ids").forEach(x=>{if(!ids.has(String(x)))h.push(`klick.json: ${c.id} nennt unbekannte ID ${x}.`);}));
    phasenDaten().phasen.forEach(p=>arr(p,"sichtbar","ids").forEach(x=>{if(!ids.has(String(x)))h.push(`phasen.json: ${p.id} nennt unbekannte ID ${x}.`);}));
  }
  return h;
}

/* ---------- Landkarte ---------- */
const OPTS={nodes:{shape:"dot",size:22,font:{size:15},borderWidth:2},edges:{arrows:"to",font:{size:12,align:"middle"},color:{color:"#888"},smooth:{type:"dynamic"}},physics:{solver:"barnesHut",barnesHut:{gravitationalConstant:-6000,springLength:220,avoidOverlap:0.5},stabilization:{iterations:400}},layout:{randomSeed:7},interaction:{hover:true}};
function knotenFuerNetz(knoten,cluster,sichtbareCluster){
  return knoten.map(n=>{const cs=clusterVon(n.id,cluster);let c=cs.length?cs[0]:null;
    if(sichtbareCluster&&c&&!sichtbareCluster.has(String(c.id)))c=null;
    const f=c?clusterFarbe(c.id,cluster):NEUTRAL;
    return {id:String(n.id),label:`${n.id} ${n.label==null?"":n.label}`,color:{background:f,border:"#555",highlight:{background:f,border:"#000"}}};});
}
function kantenFuerNetz(kanten){return kanten.map(e=>({id:String(e.id),from:String(e.from),to:String(e.to),label:String(e.id)}));}
function klickFuer(id){
  const {cluster}=katalog(); const ziele=new Set([String(id),...clusterVon(id,cluster).map(c=>String(c.id))]);
  return klickDaten().klick.filter(c=>arr(c,"ids").some(x=>ziele.has(String(x))));
}
function klickHtml(id){
  if(jsonStatus("klick.json")!=="ok")return `<p class="note">Klickinhalte: ${jsonStatus("klick.json")==="fehlt"?"klick.json nicht geliefert":"klick.json fehlerhaft"}.</p>`;
  const l=klickFuer(id); if(!l.length)return '<p class="note">Keine Klickinhalte zu diesem Element in klick.json.</p>';
  return l.map(c=>`<div class="klick"><strong>${esc(c.id)} „${esc(c.titel)}“</strong> (${esc(arr(c,"ids").join(", "))})<br>Eindruck: ${inline(c.eindruck??"")}<br><span class="note">Beleg: ${inline(c.beleg??"–")}<br>Prüfung: ${inline(c.pruefung??c["prüfung"]??"–")}</span></div>`).join("");
}
function stimmungHtml(){
  const st=jsonStatus("klick.json"); if(st!=="ok")return `<p class="note">Stimmung: ${st==="fehlt"?"klick.json nicht geliefert":"klick.json fehlerhaft"}.</p>`;
  const s=klickDaten().stimmung; return s?`<p><strong>Stimmung:</strong> ${inline(s)}</p>`:'<p class="note">Stimmung: in klick.json nicht angegeben.</p>';
}
function zeigeElement(id){
  const {knoten,kanten,cluster}=katalog(); const info=$("#info"); let h="";
  const n=knoten.find(x=>String(x.id)===String(id)), e=kanten.find(x=>String(x.id)===String(id)), c=cluster.find(x=>String(x.id)===String(id));
  if(n){const cs=clusterVon(n.id,cluster);
    h=`<h3>${esc(n.id)} ${esc(n.label)}</h3>${cs.length?`<p class="note">Cluster: ${cs.map(c=>`${esc(c.id)} „${esc(c.label)}“`).join(", ")}</p>`:""}
    <p>${inline(n.text??"")}</p><p><strong>Beleg:</strong> ${inline(n.beleg??"–")}</p><p><strong>Gegenargument:</strong> ${inline(n.gegen??"–")}</p>`;}
  else if(e){h=`<h3>${esc(e.id)}: ${esc(e.from)} → ${esc(e.to)}</h3><p>${inline(e.text??"")}</p>${e.beleg?`<p><strong>Beleg:</strong> ${inline(e.beleg)}</p>`:""}${e.gegen?`<p><strong>Gegenargument:</strong> ${inline(e.gegen)}</p>`:""}`;}
  else if(c){h=`<h3>Cluster ${esc(c.id)} „${esc(c.label)}“</h3><p>Knoten: ${esc(arr(c,"knoten","nodes","ids").join(", "))}</p>${c.text?`<p>${inline(c.text)}</p>`:""}`;}
  if(!h){info.innerHTML=`<p class="note">Klicke auf einen Knoten, eine Kante oder einen Cluster in der Legende.</p>`+stimmungHtml();return;}
  info.innerHTML=h+"<h3>Klickinhalte</h3>"+klickHtml(id)+stimmungHtml();
}
function zeigeKarte(){
  const sec=$("#karte"); const st=jsonStatus("katalog.json");
  if(netz){netz.destroy();netz=null;}
  if(st!=="ok"){sec.innerHTML=(st==="fehlt"?nichtGeliefert("katalog.json"):fehlerhaft("katalog.json"))+stimmungHtml();return;}
  const {knoten,kanten,cluster}=katalog();
  sec.innerHTML=`<div class="zweispaltig"><div><div id="netz" class="netz"></div>
   <div class="legende karte"><strong>Cluster:</strong> ${cluster.length?cluster.map(c=>`<span data-id="${esc(c.id)}"><i class="punkt" style="background:${clusterFarbe(c.id,cluster)}"></i>${esc(c.id)} ${esc(c.label)}</span>`).join(""):'<span class="note">keine Cluster in katalog.json</span>'}
   <span><i class="punkt" style="background:${NEUTRAL}"></i>ohne Cluster</span></div></div>
   <div id="info" class="karte"></div></div>`;
  const kh=pruefHinweise().filter(x=>/^(katalog|klick)\.json/.test(x));
  if(kh.length)sec.insertAdjacentHTML("afterbegin",kh.map(x=>`<div class="hinweis">${esc(x)}</div>`).join(""));
  sec.querySelectorAll(".legende span[data-id]").forEach(s=>s.onclick=()=>zeigeElement(s.dataset.id));
  zeigeElement(null);
  if(!knoten.length){$("#netz").innerHTML='<p class="fehlt" style="margin:1rem">katalog.json enthält keine Knoten.</p>';return;}
  if(typeof vis==="undefined"){$("#netz").innerHTML='<p class="fehlt" style="margin:1rem">lib/vis-network.min.js wurde nicht geladen. Die Karte kann nicht gezeichnet werden.</p>';return;}
  netz=new vis.Network($("#netz"),{nodes:new vis.DataSet(knotenFuerNetz(knoten,cluster)),edges:new vis.DataSet(kantenFuerNetz(kanten.filter(e=>knoten.some(n=>String(n.id)===String(e.from))&&knoten.some(n=>String(n.id)===String(e.to)))))},OPTS);
  netz.on("click",p=>zeigeElement(p.nodes.length?p.nodes[0]:p.edges.length?p.edges[0]:null));
}

/* ---------- Simulation ---------- */
function stopSim(){if(simTimer){clearInterval(simTimer);simTimer=null;}const b=$("#simPlay");if(b)b.textContent="Abspielen";}
function zeigePhase(i){
  const {phasen,hinweis}=phasenDaten(); const {knoten,kanten,cluster}=katalog();
  if(!phasen.length)return; simIndex=Math.max(0,Math.min(i,phasen.length-1)); const ph=phasen[simIndex];
  const sicht=new Set(arr(ph,"sichtbar","ids").map(String));
  const sc=new Set(cluster.filter(c=>sicht.has(String(c.id))).map(c=>String(c.id)));
  const kn=knoten.filter(n=>sicht.has(String(n.id))); const knIds=new Set(kn.map(n=>String(n.id)));
  const ka=kanten.filter(e=>sicht.has(String(e.id))&&knIds.has(String(e.from))&&knIds.has(String(e.to)));
  if(simNetz){const N=knotenFuerNetz(kn,cluster,sc).map(n=>Object.assign(n,simPos[n.id]||{})), E=kantenFuerNetz(ka);
    const nd=simNetz.body.data.nodes, ed=simNetz.body.data.edges;
    nd.remove(nd.getIds().filter(x=>!knIds.has(String(x)))); nd.update(N);
    ed.remove(ed.getIds().filter(x=>!ka.some(e=>String(e.id)===String(x)))); ed.update(E);
    simAnsicht();}
  document.querySelectorAll(".phasen li").forEach((li,j)=>li.classList.toggle("aktiv",j===simIndex));
  $("#simInfo").innerHTML=`<h3>${esc(ph.id)} ${esc(ph.titel)} <span class="note">(Phase ${simIndex+1} von ${phasen.length})</span></h3><p>${inline(ph.text??"")}</p>
   <p class="note">Sichtbar laut phasen.json: ${esc(arr(ph,"sichtbar","ids").join(", ")||"–")}${sc.size?` · Cluster farbig: ${esc([...sc].join(", "))}`:" · kein Cluster sichtbar, Knoten grau"}</p>`;
}
function simAnsicht(){
  const ps=Object.values(simPos); if(!ps.length||!simNetz)return; const el=$("#simNetz");
  const xs=ps.map(p=>p.x), ys=ps.map(p=>p.y); const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const scale=Math.min(1.2,el.clientWidth/(maxX-minX+260),el.clientHeight/(maxY-minY+160));
  simNetz.moveTo({position:{x:(minX+maxX)/2,y:(minY+maxY)/2},scale:scale,animation:false});
}
function zeigeSimulation(){
  const sec=$("#simulation"); stopSim(); if(simNetz){simNetz.destroy();simNetz=null;}
  const st=jsonStatus("phasen.json");
  if(st!=="ok"){sec.innerHTML=st==="fehlt"?nichtGeliefert("phasen.json"):fehlerhaft("phasen.json");return;}
  const {phasen,hinweis}=phasenDaten();
  let h="";
  if(jsonStatus("katalog.json")!=="ok")h+=`<div class="fehlt">katalog.json ${jsonStatus("katalog.json")==="fehlt"?"nicht geliefert":"fehlerhaft"}: Die Phasen können nur als Text gezeigt werden.</div>`;
  h+=`<div class="leiste"><button id="simPlay">Abspielen</button><button class="hell" id="simZur">◀ Zurück</button><button class="hell" id="simVor">Weiter ▶</button><span class="note">Abspielen wechselt alle 2,5 Sekunden zur nächsten Phase.</span></div>
   <div class="zweispaltig" style="margin-top:.8rem"><div><div id="simNetz" class="netz"></div></div>
   <div><div class="karte"><strong>Phasen</strong><ol class="phasen">${phasen.map((p,i)=>`<li data-i="${i}">${esc(p.id)} ${esc(p.titel)}</li>`).join("")}</ol></div>
   <div id="simInfo" class="karte"></div>
   <div class="karte"><strong>Hinweis (phasen.json):</strong> ${hinweis?inline(hinweis):'<span class="note">nicht angegeben</span>'}</div></div></div>`;
  sec.innerHTML=h;
  if(!phasen.length){$("#simInfo").innerHTML='<p class="fehlt">phasen.json enthält keine Phasen.</p>';return;}
  if(jsonStatus("katalog.json")==="ok"&&typeof vis!=="undefined"){
    // feste Positionen aus der vollständigen Landkarte, damit Knoten zwischen Phasen nicht springen
    const {knoten,kanten,cluster}=katalog(); const tmp=document.createElement("div");
    tmp.style.cssText="position:absolute;left:-5000px;top:0;width:700px;height:520px"; document.body.appendChild(tmp);
    const voll=new vis.Network(tmp,{nodes:new vis.DataSet(knotenFuerNetz(knoten,cluster)),edges:new vis.DataSet(kantenFuerNetz(kanten.filter(e=>knoten.some(n=>String(n.id)===String(e.from))&&knoten.some(n=>String(n.id)===String(e.to)))))},OPTS);
    simPos=voll.getPositions(); voll.destroy(); tmp.remove();
    simNetz=new vis.Network($("#simNetz"),{nodes:new vis.DataSet([]),edges:new vis.DataSet([])},Object.assign({},OPTS,{physics:false}));
  }
  else $("#simNetz").innerHTML='<p class="note" style="margin:1rem">Keine Grafik möglich.</p>';
  sec.querySelectorAll(".phasen li").forEach(li=>li.onclick=()=>{stopSim();zeigePhase(+li.dataset.i);});
  $("#simZur").onclick=()=>{stopSim();zeigePhase(simIndex-1);};
  $("#simVor").onclick=()=>{stopSim();zeigePhase(simIndex+1);};
  $("#simPlay").onclick=()=>{
    if(simTimer){stopSim();return;}
    zeigePhase(0); $("#simPlay").textContent="Stopp";
    simTimer=setInterval(()=>{if(simIndex>=phasen.length-1){stopSim();return;}zeigePhase(simIndex+1);},2500);
  };
  zeigePhase(0);
}

/* ---------- Bilder ---------- */
function angabeHtml(a){return `<div>${a.rolle?`<strong>${inline(a.rolle)}</strong><br>`:""}${a.begruendung?`Begründung: ${inline(a.begruendung)}<br>`:""}${a.quelle?`<span class="note">Quelle: ${inline(a.quelle)}</span>`:""}${!a.rolle&&!a.begruendung&&!a.quelle?`<span class="note">${inline(a.roh)}</span>`:""}</div>`;}
function zeigeBilder(){
  const sec=$("#bilder"); let h="";
  if(!lauf.bilder_md_geliefert)h+=nichtGeliefert("bilder.md");
  if(lauf.fehlend.includes("bilder/"))h+=nichtGeliefert("bilder/ (Ordner)");
  else if(!lauf.bilder.length)h+=`<div class="hinweis">Der Ordner bilder/ enthält keine Bilder.</div>`;
  if(lauf.bilder.length){
    h+=`<p class="note">${lauf.bilder.length} Bild(er). Klick auf ein Bild öffnet die Großansicht.</p><div class="galerie">${lauf.bilder.map((b,i)=>`<figure><img loading="lazy" src="${esc(b.src)}" alt="${esc(b.datei)}" data-i="${i}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'fehlt',textContent:'Bild konnte nicht geladen werden.'}))">
      <figcaption><code>${esc(b.datei)}</code>${b.angaben.length?b.angaben.map(angabeHtml).join("<hr>"):`<div class="note">Keine Angaben in bilder.md.</div>`}</figcaption></figure>`).join("")}</div>`;}
  if(lauf.bilder_ohne_datei&&lauf.bilder_ohne_datei.length)h+=`<div class="karte"><h3>Einträge in bilder.md ohne passende Datei in bilder/</h3>${lauf.bilder_ohne_datei.map(a=>`<div class="hinweis">${a.datei?`<code>${esc(a.datei)}</code>: `:""}${angabeHtml(a)}</div>`).join("")}</div>`;
  sec.innerHTML=h;
  sec.querySelectorAll(".galerie img").forEach(img=>img.onclick=()=>{const b=lauf.bilder[+img.dataset.i];
    const g=$("#gross");g.querySelector("img").src=b.src;g.querySelector("div").innerHTML=esc(b.datei)+(b.angaben.length?" · "+b.angaben.map(a=>esc([a.rolle,a.begruendung].filter(Boolean).join(": "))).join(" · "):"")+"<br><span style='opacity:.7'>Klick oder Esc schließt</span>";g.style.display="flex";});
}
$("#gross").onclick=()=>{$("#gross").style.display="none";};
document.addEventListener("keydown",e=>{if(e.key==="Escape")$("#gross").style.display="none";});

/* ---------- Bot-Ausgaben ---------- */
function zeigeAusgaben(){
  const sec=$("#ausgaben");
  let h=`<div class="karte inhalt"><strong>Dateien:</strong> ${lauf.md.map((m,i)=>`<a href="#" data-ziel="md${i}">${esc(m.datei)}</a>`).join("")}</div>`;
  h+=lauf.md.map((m,i)=>`<div class="karte" id="md${i}"><h3>${esc(m.datei)}${m.rolle?` <span class="note">· ${esc(m.rolle)}</span>`:""}</h3>${m.geliefert?`<div class="md">${markdown(m.text)}</div>`:nichtGeliefert(m.datei)}</div>`).join("");
  sec.innerHTML=h;
  sec.querySelectorAll("a[data-ziel]").forEach(a=>a.onclick=e=>{e.preventDefault();document.getElementById(a.dataset.ziel).scrollIntoView({behavior:"smooth"});});
}

/* ---------- Steuerung ---------- */
const TABS=["uebersicht","karte","simulation","bilder","ausgaben"];
function hashLesen(){const p=new URLSearchParams(location.hash.replace(/^#/,""));return {lauf:p.get("lauf"),tab:p.get("tab")};}
function hashSchreiben(){const p=new URLSearchParams();p.set("lauf",lauf?lauf.ordner:"");p.set("tab",tab);history.replaceState(null,"","#"+p.toString());}
function zeigeTab(t){
  tab=TABS.includes(t)?t:"uebersicht";
  document.querySelectorAll("nav a").forEach(a=>a.classList.toggle("active",a.dataset.tab===tab));
  document.querySelectorAll("main section").forEach(s=>s.classList.toggle("active",s.id===tab));
  if(tab!=="simulation")stopSim();
  if(lauf){({uebersicht:zeigeUebersicht,karte:zeigeKarte,simulation:zeigeSimulation,bilder:zeigeBilder,ausgaben:zeigeAusgaben})[tab]();}
  hashSchreiben();
}
function waehleLauf(ordner){lauf=DATEN.laeufe.find(l=>l.ordner===ordner)||DATEN.laeufe[0]||null;$("#laufwahl").value=lauf?lauf.ordner:"";zeigeTab(tab);}
function start(){
  $("#erzeugt").textContent="Seite erzeugt: "+DATEN.erzeugt;
  $("#global").innerHTML=(DATEN.hinweise||[]).map(x=>`<div class="hinweis">${esc(x)}</div>`).join("");
  const sel=$("#laufwahl");
  sel.innerHTML=DATEN.laeufe.map(l=>`<option value="${esc(l.ordner)}">${esc(l.ordner)}${l.titel&&l.titel!==l.ordner?" – "+esc(l.titel):""}${l.start_iso?" ("+new Date(l.start_iso).toLocaleString("de-DE",{dateStyle:"short",timeStyle:"short"})+")":""}</option>`).join("");
  if(!DATEN.laeufe.length){sel.innerHTML="<option>keine Läufe</option>";sel.disabled=true;
    $("#global").innerHTML+=`<div class="fehlt">In laeufe/ wurden keine Laufordner gefunden. Lege einen Lauf an und führe <code>python build.py</code> erneut aus.</div>`;}
  sel.onchange=()=>waehleLauf(sel.value);
  document.querySelectorAll("nav a").forEach(a=>a.onclick=()=>zeigeTab(a.dataset.tab));
  const h=hashLesen(); tab=h.tab||"uebersicht"; waehleLauf(h.lauf);
  window.addEventListener("hashchange",()=>{const h=hashLesen();if(h.tab&&h.tab!==tab)zeigeTab(h.tab);if(h.lauf&&lauf&&h.lauf!==lauf.ordner)waehleLauf(h.lauf);});
}
start();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
