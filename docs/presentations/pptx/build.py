#!/usr/bin/env python3
"""PFSM multi-part presentation. Regenerate: see README.md in this dir."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import os, random

_R = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "images"))
_A = os.path.join(os.path.dirname(__file__), "assets")   # pre-cropped screenshot regions, see assets/README
_MAP = {
    "hero.jpg":        os.path.join(_R, "readme", "PiFinder.jpg"),
    "cc_full.png":     os.path.join(_R, "readme", "cc_full_page.png"),
    "cc_coupling.png": os.path.join(_R, "readme", "cc_mount_bridge_coupling.png"),
    "lx200_cp.png":    os.path.join(_A, "lx200_onset.png"),
    "sim_mount.png":   os.path.join(_A, "sim_mount_c.png"),
    "sim_pf.png":      os.path.join(_A, "sim_pf_c.png"),
    "kstars_both.png": os.path.join(_A, "kstars_both_c.png"),
    "cc_map.png":      os.path.join(_A, "cc_map.png"),
    "mb_diagram.png":  os.path.join(_R, "readme", "badge_mb_diagram.png"),
    "wordmark_neg.png":os.path.join(_R, "logo",   "PiFinder-Stellarmate_Wortmarke_Negativ_fuer-dunklen-hg.png"),
    "heyapos.png":     os.path.join(_R, "readme", "HeyApos_Wortmarke_logo_thumb.png"),
    "avvp_neg.png":    os.path.join(_R, "readme", "avvp_2019_logo_wortmarke_neg.png"),
}

DARK  = RGBColor(0x0B, 0x10, 0x26)
DARK2 = RGBColor(0x16, 0x20, 0x40)
LIGHT = RGBColor(0xF7, 0xF9, 0xFC)
NAVY  = RGBColor(0x1B, 0x2A, 0x4A)
BLUE  = RGBColor(0x4E, 0xA8, 0xDE)
AMBER = RGBColor(0xFF, 0xB7, 0x03)
INK   = RGBColor(0x18, 0x20, 0x30)
PAPER = RGBColor(0xEA, 0xEF, 0xF8)
MUTE  = RGBColor(0x5C, 0x67, 0x7B)
MOD   = RGBColor(0x9A, 0xA6, 0xC2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LINE  = RGBColor(0xD8, 0xE0, 0xEC)
GREEN = RGBColor(0x2E, 0x9E, 0x5B)
RED   = RGBColor(0xC6, 0x45, 0x3A)
CARD  = RGBColor(0xFF, 0xFF, 0xFF)
FONT  = "Calibri"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = 13.333, 7.5
M = 0.7

# type scale (roughly 2x the previous body sizes)
T_TITLE=40; T_KICK=15; T_H2=26; T_BODY=25; T_BODYSM=21; T_CAP=15
T_SECNUM=96; T_SECT=52; T_SECSUB=22

def slide(bg=LIGHT):
    s = prs.slides.add_slide(BLANK)
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    r.fill.solid(); r.fill.fore_color.rgb = bg; r.line.fill.background(); r.shadow.inherit = False
    return s

def _run(r, t, sz, b, c, it=False):
    r.text=t; r.font.size=Pt(sz); r.font.bold=b; r.font.italic=it; r.font.name=FONT; r.font.color.rgb=c

def text(s,x,y,w,h,paras,align=PP_ALIGN.LEFT,anchor=MSO_ANCHOR.TOP,ls=1.0,sa=4,wrap=True):
    tb=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
    tf=tb.text_frame; tf.word_wrap=wrap; tf.vertical_anchor=anchor
    tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
    for i,p in enumerate(paras):
        par=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        par.alignment=align; par.line_spacing=ls; par.space_after=Pt(sa); par.space_before=Pt(0)
        for tup in p:
            it=tup[4] if len(tup)>4 else False
            _run(par.add_run(),tup[0],tup[1],tup[2],tup[3],it)
    return tb

def bullets(s,x,y,w,h,items,sz=T_BODY,color=INK,gap=16,marker=BLUE,ls=1.12,anchor=MSO_ANCHOR.TOP):
    tb=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
    tf=tb.text_frame; tf.word_wrap=True; tf.vertical_anchor=anchor
    tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
    for i,it in enumerate(items):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        p.line_spacing=ls; p.space_after=Pt(gap); p.space_before=Pt(0)
        pPr=p._p.get_or_add_pPr()
        pPr.set('marL',str(int(0.42*914400))); pPr.set('indent',str(-int(0.42*914400)))
        _run(p.add_run(),"▸  ",sz,True,marker)
        if isinstance(it,tuple):
            _run(p.add_run(),it[0],sz,True,color)
            if it[1]: _run(p.add_run(),it[1],sz,False,color)
        else:
            _run(p.add_run(),it,sz,False,color)
    return tb

def circle(s,x,y,d,fill,glyph=None,gc=WHITE,gs=20):
    c=s.shapes.add_shape(MSO_SHAPE.OVAL,Inches(x),Inches(y),Inches(d),Inches(d))
    c.fill.solid(); c.fill.fore_color.rgb=fill; c.line.fill.background(); c.shadow.inherit=False
    if glyph is not None:
        tf=c.text_frame; tf.word_wrap=False
        tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
        p=tf.paragraphs[0]; p.alignment=PP_ALIGN.CENTER
        _run(p.add_run(),glyph,gs,True,gc)
    return c

def pic(s,path,x,y,w,h=None,border=LINE,shadow=True):
    p=s.shapes.add_picture(_MAP[path],Inches(x),Inches(y),Inches(w),Inches(h) if h else None)
    if border is not None: p.line.color.rgb=border; p.line.width=Pt(1)
    if shadow:
        sp=p._element.spPr
        el=sp.makeelement(qn('a:effectLst'),{})
        sh=el.makeelement(qn('a:outerShdw'),{'blurRad':'90000','dist':'34000','dir':'5400000','rotWithShape':'0'})
        clr=sh.makeelement(qn('a:srgbClr'),{'val':'0B1026'})
        clr.append(clr.makeelement(qn('a:alpha'),{'val':'20000'}))
        sh.append(clr); el.append(sh); sp.append(el)
    return p

def card(s,x,y,w,h,fill=CARD,line=LINE):
    r=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    r.adjustments[0]=0.045
    r.fill.solid(); r.fill.fore_color.rgb=fill; r.line.color.rgb=line; r.line.width=Pt(1); r.shadow.inherit=False
    return r

def head(s,kick,title,tc=INK):
    circle(s,M,0.62,0.17,AMBER)
    text(s,M+0.32,0.58,SW-2*M-0.32,0.34,[[(kick.upper(),T_KICK,True,BLUE)]])
    text(s,M,0.98,SW-2*M,1.0,[[(title,T_TITLE,True,tc)]],ls=1.02)

def footer(s,txt,dark=False):
    text(s,M,SH-0.5,SW-2*M,0.3,[[(txt,12,False,MOD if dark else MUTE)]])

def scrim(s,x,y,w,h,color,opacity):
    """opacity 0-100 (0 = invisible)."""
    r=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    r.fill.solid(); r.fill.fore_color.rgb=color; r.line.fill.background(); r.shadow.inherit=False
    sf=r.fill._xPr.find(qn('a:solidFill')); srgb=sf.find(qn('a:srgbClr'))
    srgb.append(srgb.makeelement(qn('a:alpha'),{'val':str(int(opacity*1000))}))
    return r

def grad(s,x,y,w,h,stops,ang_deg):
    """Smooth linear gradient rectangle. stops: (pos 0-100, 'RRGGBB', alpha 0-100).
    ang_deg: 0 = left->right, 90 = top->bottom."""
    r=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    r.line.fill.background(); r.shadow.inherit=False
    sp=r._element.spPr
    for tag in ('a:solidFill','a:noFill','a:gradFill','a:blipFill','a:pattFill'):
        e=sp.find(qn(tag))
        if e is not None: sp.remove(e)
    g=sp.makeelement(qn('a:gradFill'),{})
    lst=g.makeelement(qn('a:gsLst'),{})
    for pos,rgb,alpha in stops:
        gs=lst.makeelement(qn('a:gs'),{'pos':str(int(pos*1000))})
        cc=gs.makeelement(qn('a:srgbClr'),{'val':rgb})
        cc.append(cc.makeelement(qn('a:alpha'),{'val':str(int(alpha*1000))}))
        gs.append(cc); lst.append(gs)
    g.append(lst)
    g.append(g.makeelement(qn('a:lin'),{'ang':str(int(ang_deg*60000)),'scaled':'1'}))
    sp.find(qn('a:prstGeom')).addnext(g)
    return r

def cover(s,path,img_w_px,img_h_px):
    """full-bleed background image, aspect preserved, centered (edges cropped)."""
    ar=img_w_px/img_h_px
    if ar >= SW/SH:
        w=SH*ar; h=SH; x=(SW-w)/2; y=0.0
    else:
        w=SW; h=SW/ar; x=0.0; y=(SH-h)/2
    return s.shapes.add_picture(_MAP[path],Inches(x),Inches(y),Inches(w),Inches(h))

def stars(s,n,seed):
    random.seed(seed)
    for _ in range(n):
        dx=random.uniform(0.15,SW-0.15); dy=random.uniform(0.15,SH-0.15)
        dd=random.choice([0.02,0.03,0.045])
        o=s.shapes.add_shape(MSO_SHAPE.OVAL,Inches(dx),Inches(dy),Inches(dd),Inches(dd))
        o.fill.solid(); o.fill.fore_color.rgb=RGBColor(0x3A,0x4A,0x78); o.line.fill.background(); o.shadow.inherit=False

def section(num,kick,title,sub=None):
    s=slide(DARK); stars(s,44,sum(ord(c) for c in num)+len(prs.slides._sldIdLst))
    text(s,M,2.1,3.0,1.7,[[(num,T_SECNUM,True,AMBER)]])
    text(s,M,3.66,SW-2*M,0.4,[[(kick.upper(),T_KICK+1,True,BLUE)]])
    text(s,M,4.06,SW-2*M,1.4,[[(title,T_SECT,True,WHITE)]],ls=1.02)
    if sub: text(s,M,5.3,SW-2*M-1.0,1.2,[[(sub,T_SECSUB,False,MOD)]],ls=1.3)
    return s

# ============================================================

# 1 TITLE — full-bleed hero kept bright, navy edge bar, baked-in wordmark left as shot
s=slide(DARK)
_hw=SH*(1400/719)
s.shapes.add_picture(_MAP["hero.jpg"],Inches((SW-_hw)/2),0,Inches(_hw),Inches(SH))
BAR=0.85
_b=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(SW-BAR),0,Inches(BAR),Inches(SH))
_b.fill.solid(); _b.fill.fore_color.rgb=DARK; _b.line.fill.background(); _b.shadow.inherit=False
text(s,M,0.7,8.6,2.3,[[("Plate-solving push-to,",42,True,WHITE)],
                       [("on a full imaging rig.",42,True,WHITE)]],ls=1.12)
text(s,M,2.75,7.7,1.5,[[("One Raspberry Pi. PiFinder answers “where am I pointing”, "
    "StellarMate drives everything else — joined over INDI.",20,False,PAPER)]],ls=1.35)
text(s,SW-BAR-7.0,SH-0.95,6.8,0.34,[[("github.com/apos/PiFinder_Stellarmate",15,True,BLUE)]],align=PP_ALIGN.RIGHT)
text(s,SW-BAR-7.6,SH-0.6,7.4,0.3,[[("Community project — not affiliated with PiFinder or StellarMate",12,False,RGBColor(0xC2,0xCB,0xDB))]],align=PP_ALIGN.RIGHT)

# 2 AGENDA
s=slide(LIGHT); head(s,"Agenda","What this deck covers")
parts=[("1","Project summary & focus"),("2","PFSM Control Center"),
       ("3","PF LX200 & PF Mount Bridge"),("4","PF Simulator")]
for i,(n,t) in enumerate(parts):
    yy=2.05+i*0.92
    circle(s,M,yy,0.58,NAVY,n,WHITE,23)
    text(s,M+0.92,yy+0.02,11.0,0.5,[[(t,T_H2,True,INK)]])
text(s,M,SH-1.45,SW-2*M,1.0,[[("Then two takeaways — ",T_BODYSM,False,MUTE),
    ("PiFinder",T_BODYSM,True,INK),(": where to send PRs.  ",T_BODYSM,False,MUTE),
    ("StellarMate",T_BODYSM,True,INK),(": how the SMOS app could drive PFSM.",T_BODYSM,False,MUTE)]],ls=1.3)

# 3 DUMMIES 1
s=slide(LIGHT); head(s,"For dummies · 1 / 3","Two problems, one telescope")
card(s,M,2.05,6.0,4.2)
circle(s,M+0.4,2.4,0.5,AMBER,"?",DARK,22)
text(s,M+1.1,2.5,4.6,0.5,[[("Where am I\npointing?",T_H2,True,INK)]],ls=1.05)
text(s,M+0.4,3.7,5.2,2.3,[[("A Dobson or push-to EQ has no encoders — the software "
    "has no idea where the tube looks.",T_BODYSM,False,MUTE)]],ls=1.28)
card(s,6.9,2.05,6.0,4.2)
circle(s,7.3,2.4,0.5,BLUE,"★",WHITE,19)
text(s,8.0,2.5,4.6,0.5,[[("Drive the\nwhole rig",T_H2,True,INK)]],ls=1.05)
text(s,7.3,3.7,5.2,2.3,[[("Camera, mount, guiding, focus — all need one coordinated "
    "control layer: INDI, KStars/Ekos, an app.",T_BODYSM,False,MUTE)]],ls=1.28)
footer(s,"For dummies")

# 4 DUMMIES 2
s=slide(LIGHT); head(s,"For dummies · 2 / 3","Each project owns one half")
card(s,M,2.05,6.0,4.2)
text(s,M+0.45,2.35,5.0,0.5,[[("PiFinder",T_H2,True,BLUE)]])
bullets(s,M+0.45,3.15,5.2,3.0,[
    "Global-shutter camera + plate-solver.",
    "Live sky position + push-to arrows.",
    "Python, open hardware & software.",
],sz=T_BODYSM,gap=14)
card(s,6.9,2.05,6.0,4.2)
text(s,7.35,2.35,5.0,0.5,[[("StellarMate",T_H2,True,AMBER)]])
bullets(s,7.35,3.15,5.2,3.0,[
    "INDI — the device-driver standard.",
    "KStars / Ekos — capture & automation.",
    "The StellarMate phone/tablet app.",
],sz=T_BODYSM,gap=14,marker=AMBER)
footer(s,"For dummies")

# 5 DUMMIES 3
s=slide(DARK); stars(s,34,5)
text(s,M,0.62,3.0,0.35,[[("FOR DUMMIES · 3 / 3",T_KICK,True,BLUE)]])
text(s,M,1.0,11.6,1.0,[[("PFSM is the wiring. INDI is the connector.",T_TITLE-2,True,WHITE)]],ls=1.05)
bx=[(M,"PiFinder","exposes its solved\nposition as an\nINDI telescope",BLUE),
    (4.98,"Mount Bridge","couples that to\nany INDI mount\n(optional)",AMBER),
    (8.96,"Your rig","KStars / Ekos, the\nmount, the app —\nunchanged",RGBColor(0x8C,0xD8,0xB0))]
for x,t,d,c in bx:
    card(s,x,2.6,3.6,2.75,fill=DARK2,line=RGBColor(0x2C,0x3A,0x66))
    circle(s,x+0.34,2.94,0.18,c)
    text(s,x+0.66,2.82,2.9,0.4,[[(t,T_H2-4,True,WHITE)]])
    text(s,x+0.34,3.5,3.1,1.7,[[(ln,15,False,MOD)] for ln in d.split("\n")],ls=1.25)
for ax in (4.66,8.64):
    a=s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,Inches(ax),Inches(3.55),Inches(0.42),Inches(0.55))
    a.fill.solid(); a.fill.fore_color.rgb=RGBColor(0x3A,0x4A,0x78); a.line.fill.background(); a.shadow.inherit=False
text(s,M,5.75,11.9,1.0,[[("PiFinder is patched in place, never forked. The mount side is generic INDI.",
    T_BODYSM-2,False,MOD)]],ls=1.3)
footer(s,"For dummies",dark=True)

# 6 SECTION 01
section("01","Part one","Project summary & focus")

# 7 WHAT PFSM IS
s=slide(LIGHT); head(s,"Scope","What PFSM is")
bullets(s,M,2.2,12.0,4.4,[
    ("A setup script ","— installs & patches PiFinder onto StellarMate OS."),
    ("diffs/*.diff patches ","— applied to a stock checkout via patch(1)."),
    ("Three INDI drivers ","— LX200, Mount Bridge, Simulator."),
    ("A web Control Center ","— stdlib-only, port 8765."),
],sz=T_BODY,gap=20)
footer(s,"Part 1 · Summary")

# 8 WHAT PFSM IS NOT
s=slide(LIGHT); head(s,"Scope","What PFSM is not")
bullets(s,M,2.2,12.0,4.4,[
    ("Not a fork of PiFinder ","— patches re-applied every update, kept minimal."),
    ("Not a fork of StellarMate ","— stock INDI, Web Manager, KStars."),
    ("Not a replacement for the INDI Control Panel ","— it stays for advanced work."),
    ("Not PiFinder-version-specific ","— talks only to the stable /api/*."),
],sz=T_BODY,gap=20,marker=RED)
footer(s,"Part 1 · Summary")

# 9 WHY INDI
s=slide(LIGHT); head(s,"The key decision","Why INDI")
text(s,M,2.4,12.0,1.6,[[("Both sides already speak it.",T_TITLE-4,True,NAVY)]],ls=1.05)
bullets(s,M,4.0,12.0,2.6,[
    "PiFinder exposes its position as an INDI telescope.",
    "The Mount Bridge couples that to any INDI mount — no per-mount code.",
],sz=T_BODY,gap=16)
footer(s,"Part 1 · Summary")

# 10 TESTED
s=slide(LIGHT); head(s,"Tested against","Versions & platforms")
rows=[("PiFinder 2.6.3  ·  SMOS 2.3.0","Pi 4  ✓   Pi 5  ✓   UTM x86  ✓ (install, CC, Mount Bridge vs. the Simulator)")]
text(s,M,2.5,12.0,1.0,[[("PiFinder 2.6.3   ·   StellarMate OS 2.3.0",T_H2,True,INK)]])
bullets(s,M,3.4,12.0,2.4,[
    ("Pi 4 ","— fully tested."),("Pi 5 ","— fully tested."),
    ("UTM x86 ","— install + Control Center + Mount Bridge vs. the Simulator (no real solving)."),
],sz=T_BODYSM,gap=14)
text(s,M,SH-1.3,12.0,0.9,[[("Pinned to a fixed release tag, not the upstream ",T_CAP+1,False,MUTE),
    ("release",T_CAP+1,True,INK),(" branch. The README table is the single source of truth.",T_CAP+1,False,MUTE)]],ls=1.3)
footer(s,"Part 1 · Summary")

# 10b PREREQUISITES
s=slide(LIGHT); head(s,"Before you start","Prerequisites")
bullets(s,M,2.4,12.0,3.0,[
    ("A current StellarMate OS (SMOS) installation ","— the only supported base."),
    ("Not supported: a stock PiFinder OS image. ","Doesn't make sense either — PFSM's entire "
     "premise is the StellarMate integration (INDI, KStars/Ekos, the Web Manager, the app), and a "
     "stock PiFinder OS has none of that to integrate with."),
],sz=T_BODY,gap=20)
footer(s,"Part 1 · Summary")

# 11 SECTION 02
section("02","Part two","PFSM Control Center","Install, mode-switching, hardware checks and the Mount Bridge — one web page, no SSH.")

# 12 CC WHY
CCW=5.55; CCH=CCW/(2400/3030); CCX=SW-0.35-CCW; CCY=(SH-CCH)/2
s=slide(LIGHT); head(s,"Motivation","Why a Control Center")
bullets(s,M,2.35,6.5,4.2,[
    "Watch an install from a phone at the scope.",
    "Switch Fake Mode ⟷ the real service.",
    "Check camera / IMU / GPS are really detected.",
    "Reboot the Pi without SSH.",
],sz=T_BODY,gap=20)
pic(s,"cc_full.png",CCX,CCY,CCW,CCH)
footer(s,"Part 2 · Control Center")

# 13 CC STDLIB
s=slide(LIGHT); head(s,"Architecture","Stdlib only — by necessity")
text(s,M,2.4,6.5,3.0,[[("It bootstraps the very venv that PiFinder needs, "
    "so it can’t depend on one.",T_H2,True,INK)]],ls=1.2)
bullets(s,M,5.0,6.5,2.0,[
    "http.server on :8765, polled every 1–2 s.",
    "HTTP Basic auth against the system account (PAM).",
],sz=T_BODYSM,gap=14)
pic(s,"cc_full.png",CCX,CCY,CCW,CCH)
footer(s,"Part 2 · Control Center")

# 14 BADGES
s=slide(LIGHT); head(s,"Status language","Traffic-light badges")
rows=[("White","not applicable yet",RGBColor(0xC4,0xCE,0xDC)),
      ("Green","verified functional",GREEN),
      ("Yellow","degraded / estimate",AMBER),
      ("Red","broken or wrong",RED)]
yy=2.4
for t,d,c in rows:
    circle(s,M,yy+0.02,0.34,c)
    text(s,M+0.6,yy-0.05,11.0,0.5,[[(t+"  ",T_BODY,True,INK),(d,T_BODY,False,MUTE)]])
    yy+=0.78
text(s,M,SH-1.35,12.0,0.9,[[("The rule: verify real state, never “the process is alive”.",T_CAP+2,False,MUTE)]],ls=1.3)
footer(s,"Part 2 · Control Center")

# 15 CC COUPLING
CPH=5.35; CPW=CPH*(1328/1030); CPX=SW-CPW; CPY=SH-0.05-CPH
s=slide(LIGHT); head(s,"Operating it","Coupling, without the INDI panel")
bullets(s,M,3.0,5.5,4.0,[
    "Quick Actions — one-shots",
    "Coupling presets — one click",
    "Settings — set once, hidden",
],sz=T_BODY,gap=34)
pic(s,"cc_coupling.png",CPX,CPY,CPW,CPH)
footer(s,"Part 2 · Control Center")

# 16 SECTION 03
section("03","Part three","PF LX200 & PF Mount Bridge","PiFinder as a telescope, plus a generic bridge to any INDI mount.")

# 17 THREE BLOCKS
s=slide(LIGHT); head(s,"The INDI layer","Three building blocks")
blk=[("PiFinder LX200","INDI telescope. Reports the solved position; a GoTo becomes a push-to. Required."),
     ("PiFinder Mount Bridge","Optional. Snoops PiFinder + the mount and couples them. Generic INDI only."),
     ("Your mount’s driver","Not ours — whatever your mount already uses. Only for a motorised mount.")]
yy=2.05
for i,(t,d) in enumerate(blk):
    text(s,M,yy,0.5,0.5,[[(str(i+1),T_H2-2,True,MOD)]])
    text(s,M+0.55,yy-0.02,12.0,0.5,[[(t,T_H2-3,True,INK)]])
    text(s,M+0.55,yy+0.46,11.4,0.8,[[(d,T_BODYSM-3,False,MUTE)]],ls=1.15)
    yy+=1.12
text(s,M,SH-2.05,SW-2*M,0.3,[[("The Mount Bridge status row — the three, wired together:",T_CAP,False,MUTE)]])
card(s,0,SH-1.72,SW,1.72,fill=DARK,line=DARK)
_dw=10.6
pic(s,"mb_diagram.png",(SW-_dw)/2,SH-1.5,_dw,border=None,shadow=False)   # AR 8.22 -> h ~1.29

# 18 LX200 DRIVER
s=slide(LIGHT); head(s,"The telescope driver","PiFinder LX200")
bullets(s,M,2.0,12.4,2.2,[
    ("Talks LX200 ","to PiFinder’s pos_server.py (TCP 4030)."),
    ("Reports the solved position ","each poll; a GoTo is only a push-to."),
    ("No Sync ","— PiFinder measures the truth every frame."),
],sz=T_BODYSM,gap=9)
LXW=11.3; LXX=(SW-LXW)/2; LXY=3.5
pic(s,"lx200_cp.png",LXX,LXY,LXW)   # cropped INDI CP — On Set: Track / Slew, no Sync
footer(s,"Part 3 · INDI Control Panel — On Set: Track / Slew, no Sync")

# 19 COUPLING DIAL
s=slide(LIGHT); head(s,"One property, four positions","The Coupling Dial")
modes=[("Off","pure push-to"),
       ("Verify / Alert only","warn only, hands off"),
       ("Auto-correct on drift","Sync past threshold"),
       ("Goto-Forward","real slew, then refine")]
yy=2.5
for i,(t,d) in enumerate(modes):
    text(s,M,yy,0.5,0.5,[[(str(i+1),T_H2-2,True,MOD)]])
    text(s,M+0.5,yy,3.8,0.6,[[(t,T_BODY-4,True,INK)]],ls=1.03)
    text(s,M+0.5,yy+0.44,3.9,0.5,[[(d,T_BODYSM-3,False,MUTE)]])
    yy+=1.15
CDAR=2.162
CDW=8.15; CDX=SW-CDW; CDY=2.4
pic(s,"cc_map.png",CDX,CDY,CDW)
text(s,CDX,CDY+CDW/CDAR+0.12,CDW,0.3,[[("The dial in the Control Center — ",T_CAP,False,MUTE),("Decouple + the three presets.",T_CAP,True,INK)]])
footer(s,"Part 3 · Auto-correct → Sync (any mount); Goto-Forward → Goto / Track")

# 20 GENERIC
s=slide(LIGHT); head(s,"Works with any mount","Generic INDI, nothing mount-specific")
text(s,M,2.0,12.3,0.6,[[("Only ",T_H2-3,False,INK),("EQUATORIAL_EOD_COORD",T_H2-3,True,NAVY),
    (" + ",T_H2-3,False,INK),("ON_COORD_SET",T_H2-3,True,NAVY),(" — never a mount command.",T_H2-3,False,INK)]])
text(s,M,2.72,12.4,0.5,[[("Multi-Point Alignment (#191)",T_BODYSM,True,INK),("    ·    ",T_BODYSM,False,MUTE),
    ("Reposition detection",T_BODYSM,True,INK),("    ·    ",T_BODYSM,False,MUTE),
    ("Shadow Sync",T_BODYSM,True,INK)]])
KBW=9.0; KBX=(SW-KBW)/2; KBY=3.28
pic(s,"kstars_both.png",KBX,KBY,KBW)
footer(s,"Part 3 · PiFinder + the mount, co-located on the KStars sky map — right-click either")

# 21 SECTION 04
section("04","Part four","PF Simulator","Test the Mount Bridge with no real mount and no clear sky.")

# 22 SIM SETUP
s=slide(LIGHT); head(s,"Hardware-free testing","A mount side and a PiFinder side")
_c1x,_c2x,_cw=0.35,6.75,6.25
card(s,_c1x,1.95,_cw,5.0)
text(s,_c1x+0.35,2.15,5.4,0.5,[[("Mount side",T_H2,True,INK)]])
text(s,_c1x+0.35,2.78,5.6,0.8,[[("Stock INDI Telescope Simulator — Sync or GoTo like a real mount.",
    T_BODYSM,False,MUTE)]],ls=1.2)
pic(s,"sim_mount.png",_c1x+0.3,3.9,_cw-0.6)   # AR 2.286 -> h 2.47
card(s,_c2x,1.95,_cw,5.0)
text(s,_c2x+0.35,2.15,5.2,0.5,[[("PiFinder side",T_H2,True,INK)]])
bullets(s,_c2x+0.35,2.78,5.5,0.9,[
    ("Simulator ","— holds a settable RA/Dec."),
    ("Truth Injector ","— POSTs to /api/fake_solve."),
],sz=T_BODYSM,gap=6)
pic(s,"sim_pf.png",_c2x+0.3,3.9,_cw-0.6)      # AR 2.116 -> h 2.67
footer(s,"Part 4 · Simulator")

# 23 SIM DETAILS
s=slide(LIGHT); head(s,"Behaviour & next","Simulator details")
bullets(s,M,2.3,12.0,3.6,[
    ("Sync == Goto ","— no motion to model; the RA/Dec just becomes the held value."),
    ("Inject every cycle ","— keeps PiFinder’s solve timestamp fresh."),
    ("FOLLOW_MOUNT_DEVICE ","(#239) — optionally dead-reckon along a mount’s slews."),
],sz=T_BODY,gap=18)
text(s,M,SH-1.5,12.0,1.0,[[("Next (v3.x): ",T_CAP+3,True,INK),
    ("render a GSC star field and run PiFinder’s real solver on it — issue #344.",T_CAP+3,False,MUTE)]],ls=1.3)
footer(s,"Part 4 · Simulator")

# 24 SECTION -> takeaway 1
section("→","Takeaway one · for PiFinder devs","Where PFSM could send PRs")

# 25 UPSTREAM
s=slide(LIGHT); head(s,"docs/upstream_patch_inventory.md","Patches that aren’t PFSM-specific")
bullets(s,M,2.2,12.2,4.2,[
    ("Test Mode toggle + status readback ","— a reliable API trigger (keypress sim was flaky)."),
    ("Camera-process resilience ","— fall back to the debug camera instead of crashing."),
    ("all_ips() ","— show every network address, not just the default route."),
    ("LX200 “no position yet” ","— return None, not a parseable fake coordinate."),
    ("Near-pole /api/fake_solve RA ","— filed as brickbots/PiFinder#645."),
],sz=T_BODYSM,gap=13)
text(s,M,SH-0.9,12.0,0.5,[[("Ready-to-file PR text: docs/upstream_pr_templates.md",T_CAP,False,MUTE)]])
footer(s,"Takeaway 1 · PiFinder PRs")

# 26 HOW TO HELP
s=slide(LIGHT); head(s,"Concretely","How to help — PiFinder")
bullets(s,M,2.3,12.0,4.0,[
    ("Pick one from the inventory ","— each is already triaged."),
    ("PR text is written ","in docs/upstream_pr_templates.md, in dependency order."),
    ("Mind the caveats ","— debug_solve needs an upstream regression fixed first."),
],sz=T_BODY,gap=18)
footer(s,"Takeaway 1 · PiFinder PRs")

# 27 SECTION -> takeaway 2
section("→","Takeaway two · for StellarMate devs","Extending the SMOS app for PFSM")

# 28 SMOS SCOPE
s=slide(LIGHT); head(s,"Basic usage in the app","What a thin integration needs")
bullets(s,M,2.2,12.0,4.0,[
    "Start / stop the selected INDI profile.",
    "Add / remove just the PiFinder drivers.",
    "Pick “the mount” from the loaded drivers.",
    "Three Coupling presets, in PiFinder’s words.",
],sz=T_BODY,gap=16)
text(s,M,SH-1.15,12.0,0.7,[[("The coupling logic is already framework-agnostic Python — a thin adapter ports it.",
    T_CAP+1,False,MUTE)]],ls=1.3)
footer(s,"Takeaway 2 · SMOS app")

# 29 SCREEN MAP
s=slide(LIGHT); head(s,"Mapping","CC feature → app screen")
pairs=[("Status badges","a read-only status card"),
       ("Coupling presets","a segmented control"),
       ("Quick Actions","buttons on that card")]
yy=2.35
for a,b in pairs:
    text(s,M,yy,0.5,0.5,[[(str(pairs.index((a,b))+1),T_H2-2,True,MOD)]])
    text(s,M+0.5,yy,3.8,0.5,[[(a,T_BODY-3,True,INK)]])
    text(s,M+0.5,yy+0.46,3.9,0.5,[[(b,T_BODYSM-3,False,MUTE)]])
    yy+=1.2
text(s,M,SH-0.8,4.6,0.5,[[("APIs: /api/mount_bridge_*, or INDI.",T_CAP,False,MUTE)]])
CMAR=2.162
CMW=8.15; CMX=SW-CMW; CMY=2.35
pic(s,"cc_map.png",CMX,CMY,CMW)
text(s,CMX,CMY+CMW/CMAR+0.12,CMW,0.3,[[("Where each maps from, in the Control Center",T_CAP,False,MUTE)]])
footer(s,"Takeaway 2 · SMOS app")

# 30 ROADMAP
s=slide(DARK); stars(s,44,9)
text(s,M,0.7,11.6,0.8,[[("Roadmap & where to jump in",T_TITLE-2,True,WHITE)]])
card(s,M,1.95,6.0,4.3,fill=DARK2,line=RGBColor(0x2C,0x3A,0x66))
text(s,M+0.45,2.25,5.2,0.4,[[("v2.x — consolidate",T_H2-2,True,BLUE)]])
bullets(s,M+0.45,2.95,5.2,3.2,[
    "Harden & test what exists.",
    "Send selected patches upstream.",
    "A guiding watcher.",
],sz=T_BODYSM-2,gap=14,color=PAPER,marker=BLUE)
card(s,6.9,1.95,6.0,4.3,fill=DARK2,line=RGBColor(0x2C,0x3A,0x66))
text(s,7.35,2.25,5.2,0.4,[[("v3.x — integrate",T_H2-2,True,AMBER)]])
bullets(s,7.35,2.95,5.3,3.2,[
    "Deeper SMOS integration (#35, #36).",
    "PFSM actions in the PiFinder app (#43).",
    "A “real” GSC-solving simulator (#344).",
],sz=T_BODYSM-2,gap=14,color=PAPER,marker=AMBER)
text(s,M,6.55,12.0,0.4,[[("github.com/apos/PiFinder_Stellarmate",16,True,BLUE),
    ("   ·   GitHub Project #15   ·   CHANGELOG.md",14,False,MOD)]])

# 31 CLOSING — mirrors the README.md footer
s=slide(DARK); stars(s,52,31)
_ww=6.8
s.shapes.add_picture(_MAP["wordmark_neg.png"],Inches((SW-_ww)/2),Inches(2.15),Inches(_ww))   # 950x179 -> h 1.28
text(s,M,3.95,SW-2*M,0.4,[[("© github.com/apos 2026",T_BODYSM,False,MOD)]],align=PP_ALIGN.CENTER)
text(s,M,4.45,SW-2*M,0.4,[[("Unofficial community project — not affiliated with StellarMate or PiFinder.",
    T_CAP+1,False,MUTE)]],align=PP_ALIGN.CENTER)
_hh=1.15
s.shapes.add_picture(_MAP["heyapos.png"],Inches(SW/2-0.2-_hh*(416/234)),Inches(5.55),Inches(_hh*(416/234)))
_aw=2.3
s.shapes.add_picture(_MAP["avvp_neg.png"],Inches(SW/2+0.2),Inches(5.72),Inches(_aw))          # 2600x646 -> h 0.57
text(s,M,SH-0.55,SW-2*M,0.3,[[("youtube.com/heyapos   ·   avvp.de",T_CAP,False,MOD)]],align=PP_ALIGN.CENTER)

out=os.path.join(os.path.dirname(__file__),"PFSM_overview.pptx")
prs.save(out)
print("saved",out,"-",len(prs.slides._sldIdLst),"slides")
