#!/usr/bin/env python3
"""🍎 Emoji Extractor by Alek Borisov"""

import sys, io, re, hashlib, codecs, unicodedata, signal, urllib.request, warnings, argparse, plistlib
from pathlib            import Path
from multiprocessing     import Process, Queue, cpu_count
from typing             import Dict, Tuple, Optional

import pyfiglet
from rich.console       import Console, Group
from rich.panel         import Panel
from rich.progress      import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TextColumn
from rich.text          import Text
from rich.style         import Style
from rich.markdown      import Markdown
from rich               import box

from PIL                import Image, ImageFile, ImageOps
from fontTools.ttLib    import TTCollection

# ── Optional LZFSE‐compressed emoji support
for m in ("lzfse","liblzfse","pyliblzfse"):
    try: LZFSE = __import__(m); break
    except ModuleNotFoundError: LZFSE = None
if LZFSE is None:
    sys.exit("❌ Install pyliblzfse for .emjc support")

# ── HEIC/HEIF support
from pillow_heif import register_heif_opener
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pillow_heif")
register_heif_opener()

# ── CLI & Theming ──────────────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--theme", choices=["orange","mono","high-contrast"], default="orange")
parser.add_argument("-h","--help",    action="store_true")
args, _ = parser.parse_known_args()
if args.help:
    Console().print(Markdown(__doc__))
    sys.exit()

PALETTES = {
    "orange":        ["#FF9800","#FB8C00","#F57C00","#EF6C00","#E65100"],
    "mono":          ["white"],
    "high-contrast": ["white","bright_white"],
}
palette      = PALETTES[args.theme]
rainbow_iter = iter(lambda: palette.append(palette.pop(0)) or palette[0], None)

# ── Load Apple’s human-friendly emoji names
APPLE_NAMES: Dict[str,str] = {}
strings_path = Path(
    "/System/Library/PrivateFrameworks/CoreEmoji.framework/"
    "Versions/A/Resources/en.lproj/AppleName.strings"
)
def normalize_seq(s: str) -> str:
    for ch in ("\uFE0E","\uFE0F","\u200D","\u20E3"):
        s = s.replace(ch, "")
    return s

if strings_path.exists():
    try:
        raw = plistlib.load(strings_path.open("rb"))
        for k, v in raw.items():
            name = v.decode() if isinstance(v, bytes) else v
            APPLE_NAMES[k] = name
            APPLE_NAMES[normalize_seq(k)] = name
    except Exception:
        APPLE_NAMES.clear()

# ── Banner & Gradient ASCII ─────────────────────────────────────────────
def render_ascii(text: str) -> Group:
    art = pyfiglet.figlet_format(text, font="slant")
    rows = []
    for line in art.splitlines():
        row = Text()
        for ch in line:
            row.append(ch, style=Style(color=next(rainbow_iter), bold=True))
        rows.append(row)
    return Group(*rows)

def banner() -> Panel:
    inner = Panel(
        render_ascii("Emoji Extractor"),
        border_style=next(rainbow_iter),
        box=box.DOUBLE,
        padding=(0,1),
    )
    return Panel(
        inner,
        border_style=Style(dim=True),
        box=box.ROUNDED,
        padding=(1,2),
    )

# ── Custom Gradient Progress Bar ────────────────────────────────────────
class GradientBar(BarColumn):
    def render(self, task):
        self.style = Style(color=next(rainbow_iter))
        return super().render(task)

# ── Extraction Constants & Helpers ──────────────────────────────────────
TTC  = Path("/System/Library/Fonts/Apple Color Emoji.ttc")
OUT  = Path.cwd() / "Emojis"
CPU  = cpu_count() or 4
ImageFile.LOAD_TRUNCATED_IMAGES = True

HEX   = re.compile(r"([0-9A-Fa-f]{4,8})")
LZHD  = b"bvx0"
VS    = ("\uFE0E","\uFE0F")
SKIN  = tuple(chr(x) for x in range(0x1F3FB,0x1F400))
ZJW   = "\u200D"
STRIP = dict.fromkeys(ord(c) for c in VS + SKIN + (ZJW,))

LABEL: Dict[str,str] = {}
def cldr(seq: str) -> str:
    if seq in APPLE_NAMES:
        return APPLE_NAMES[seq]
    norm = normalize_seq(seq)
    if norm in APPLE_NAMES:
        return APPLE_NAMES[norm]
    if not LABEL:
        try:
            data = urllib.request.urlopen(
                "https://unicode.org/Public/emoji/latest/emoji-test.txt",
                timeout=10
            ).read().decode()
            for row in data.splitlines():
                if "; fully-qualified" not in row: continue
                cps  = row.split(";",1)[0].strip()
                name = row.split("#",1)[1].split(" E",1)[0].strip().title()
                LABEL["".join(chr(int(c,16)) for c in cps.split())] = name
        except Exception:
            LABEL.clear()
    if seq in LABEL:
        return LABEL[seq]
    if norm in LABEL:
        return LABEL[norm]
    parts = [unicodedata.name(ch, "") for ch in norm]
    return " ".join(parts).title() if parts else "Unnamed"

def esc(h: str) -> str:
    return f"\\U{int(h,16):08X}"

def safe(txt: str, lim=140) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFKD", txt)
        if c.isprintable() and c not in '/\\:*?"<>|'
    ).strip()
    return (s or "unnamed")[:lim]

def uniq(dst: Path, blob: bytes, force=False) -> Path:
    if not dst.exists() and not force:
        return dst
    h    = hashlib.sha1(blob).hexdigest()[:8]
    base = dst.with_name(f"{dst.stem} - {h}{dst.suffix}")
    i = 0
    while base.exists():
        i += 1
        base = base.with_name(f"{dst.stem} - {h}_{i}{dst.suffix}")
    return base

def gtag(raw) -> Optional[str]:
    return None if raw is None else (
        raw.decode() if isinstance(raw,(bytes,bytearray)) else raw
    )

def dec_emjc(b: bytes) -> bytes:
    if not b.startswith(LZHD):
        raise RuntimeError
    return LZFSE.decompress(b)

DEC = {k:(lambda b:b) for k in ("png ","jpg ","tiff","heic","avif","pdf ","mask")}
DEC["emjc"] = dec_emjc

# ── Worker & Orchestrator ───────────────────────────────────────────────
def worker(ttc_bytes: bytes, q: Queue, r: Queue):
    font    = TTCollection(io.BytesIO(ttc_bytes)).fonts[0]
    strikes = font["sbix"].strikes
    cache: Dict[int,Tuple[bytes,Image.Image]] = {}
    for job in iter(q.get, None):
        gid, sz = job
        glyph   = strikes[sz].glyphs[gid]
        tg      = gtag(glyph.graphicType)
        try:
            if tg in DEC:
                data = DEC[tg](glyph.imageData)
                img  = Image.open(io.BytesIO(data)); img.load()
            elif tg in ("dupe","flip"):
                ref_gid = next(k for k,g in strikes[sz].glyphs.items()
                              if g.glyphName==glyph.referenceGlyphName)
                data, img = cache[ref_gid]
                if tg=="flip":
                    img = ImageOps.mirror(img)
                    buf = io.BytesIO(); img.save(buf,"PNG"); data=buf.getvalue()
            else:
                raise RuntimeError
            cache[gid] = (data, img)
            r.put(("ok", tg, glyph.glyphName, data, img))
        except Exception as e:
            r.put(("skip", str(e)))
    r.put(("done",))

def main():
    if not TTC.exists():
        sys.exit("Emoji font not found")
    OUT.mkdir(exist_ok=True)
    console = Console()
    console.print(banner())

    ttc_bytes = TTC.read_bytes()
    strikes   = TTCollection(TTC).fonts[0]["sbix"].strikes
    tasks     = [(gid, sz) for sz, st in strikes.items() for gid in st.glyphs]

    q, r = Queue(8192), Queue()
    for _ in range(CPU := cpu_count() or 4):
        Process(target=worker, args=(ttc_bytes, q, r)).start()
    for t in tasks:      q.put(t)
    for _ in range(CPU): q.put(None)

    progress = Progress(
        SpinnerColumn(style=palette[0]),
        TextColumn("[bold]{task.description}", style=palette[0]),
        GradientBar(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    tid = progress.add_task("✨ Extracting…", total=len(tasks))
    written: Dict[str, Path] = {}
    done = 0

    with progress:
        while done < CPU:
            kind, *pl = r.get()
            if kind == "done":
                done += 1; continue
            progress.advance(tid)
            if kind == "ok":
                tg, gname, data, img = pl
                seq  = codecs.decode("".join(esc(c) for c in HEX.findall(gname)), "unicode_escape")
                # ── Only change here: drop the emoji itself, use just the name
                name = cldr(seq)
                if tg=="flip": name += " Mirror"
                dst = uniq(OUT/f"{img.width}x{img.height}"/f"{safe(name)}.png", data, tg=="flip")
                if gname not in written:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(data)
                    written[gname] = dst

    console.print(
        Panel(f"☑  Done – {len(written)} PNGs → {OUT}",
              style=Style(color=palette[0]))
    )

signal.signal(signal.SIGINT, lambda *_: sys.exit("\nInterrupted."))
if __name__=="__main__":
    main()
