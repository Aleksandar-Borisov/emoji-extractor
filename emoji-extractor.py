#!/usr/bin/env python3
"""🍎 Emoji Extractor by Alek Borisov"""

import sys, io, re, hashlib, codecs, unicodedata, signal, urllib.request, warnings, argparse, plistlib
from pathlib            import Path
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

# ── Optional LZFSE support ───────────────────────────────────────────────
for m in ("lzfse","liblzfse","pyliblzfse"):
    try:
        LZFSE = __import__(m)
        break
    except ModuleNotFoundError:
        LZFSE = None
if LZFSE is None:
    sys.exit("❌ Install pyliblzfse for .emjc support")

# ── HEIC/HEIF support ────────────────────────────────────────────────────
from pillow_heif import register_heif_opener
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pillow_heif")
register_heif_opener()

# ── CLI & Theming ──────────────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--theme", choices=["orange","mono","high-contrast"], default="orange")
parser.add_argument("-h","--help", action="store_true")
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

# ── Load Apple’s CLDR names ───────────────────────────────────────────────
APPLE_NAMES: Dict[str,str] = {}
strings_path = Path(
    "/System/Library/PrivateFrameworks/CoreEmoji.framework/"
    "Versions/A/Resources/en.lproj/AppleName.strings"
)
def normalize_seq(s: str) -> str:
    return s.replace("\uFE0E","").replace("\uFE0F","").replace("\u200D","").replace("\u20E3","")

if strings_path.exists():
    try:
        raw = plistlib.load(strings_path.open("rb"))
        for k,v in raw.items():
            name = v.decode() if isinstance(v,bytes) else v
            APPLE_NAMES[k] = name
            APPLE_NAMES[normalize_seq(k)] = name
    except Exception:
        APPLE_NAMES.clear()

def cldr(seq: str) -> str:
    if seq in APPLE_NAMES:
        return APPLE_NAMES[seq]
    norm = normalize_seq(seq)
    if norm in APPLE_NAMES:
        return APPLE_NAMES[norm]
    parts = [unicodedata.name(ch,"") for ch in norm]
    return " ".join(parts).title() if any(parts) else "Unnamed"

# ── Helpers & Constants ─────────────────────────────────────────────────
HEX    = re.compile(r"([0-9A-Fa-f]{4,8})")
LZHD   = b"bvx0"
ImageFile.LOAD_TRUNCATED_IMAGES = True

def esc(h: str) -> str:
    return f"\\U{int(h,16):08X}"

def safe(txt: str, lim=140) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", txt)
                if c.isprintable() and c not in '/\\:*?"<>|').strip()
    return (s or "unnamed")[:lim]

def uniq(dst: Path, blob: bytes) -> Path:
    if not dst.exists():
        return dst
    h = hashlib.sha1(blob).hexdigest()[:8]
    base = dst.with_name(f"{dst.stem}-{h}{dst.suffix}")
    i = 1
    while base.exists():
        base = dst.with_name(f"{dst.stem}-{h}_{i}{dst.suffix}")
        i += 1
    return base

def dec_emjc(b: bytes) -> bytes:
    if not b.startswith(LZHD):
        raise RuntimeError("Not an emjc blob")
    return LZFSE.decompress(b)

# ── Extraction logic ─────────────────────────────────────────────────────
def extract_glyph(strike, gid, cache) -> Optional[Tuple[bytes, Image.Image]]:
    """
    Recursively extract image data + PIL image for a glyph:
    - direct types via DECODERS
    - dupe: same as reference
    - flip: mirror of reference
    """
    if gid in cache:
        return cache[gid]

    glyph = strike.glyphs[gid]
    tg    = glyph.graphicType
    # Direct decoders
    if tg in DECODERS:
        data = DECODERS[tg](glyph.imageData)
        img  = Image.open(io.BytesIO(data)); img.load()
    elif tg in ("dupe","flip"):
        # find the reference gid by name
        ref_name = glyph.referenceGlyphName
        ref_gid = next(k for k,g in strike.glyphs.items() if g.glyphName==ref_name)
        ref = extract_glyph(strike, ref_gid, cache)
        if not ref:
            return None
        data, img = ref
        if tg=="flip":
            img = ImageOps.mirror(img)
            buf = io.BytesIO(); img.save(buf,"PNG"); data = buf.getvalue()
    else:
        return None

    cache[gid] = (data, img)
    return cache[gid]

# ── DECODER MAP ─────────────────────────────────────────────────────────
DECODERS = {
    "png ": lambda b: b,
    "jpg ": lambda b: b,
    "tiff": lambda b: b,
    "heic": lambda b: b,
    "avif": lambda b: b,
    "pdf ": lambda b: b,
    "mask": lambda b: b,
    "emjc": dec_emjc,
}

# ── Banner ───────────────────────────────────────────────────────────────
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
    return Panel(
        Panel(render_ascii("Emoji Extractor"),
              border_style=next(rainbow_iter),
              box=box.DOUBLE,
              padding=(0,1)),
        border_style=Style(dim=True),
        box=box.ROUNDED,
        padding=(1,2),
    )

# ── Main ─────────────────────────────────────────────────────────────────
def main():
    TTC = Path("/System/Library/Fonts/Apple Color Emoji.ttc")
    if not TTC.exists():
        sys.exit("Emoji font not found")
    OUT = Path.cwd() / "Emojis"
    OUT.mkdir(exist_ok=True)

    console = Console()
    console.print(banner())

    ttc_bytes = TTC.read_bytes()
    font      = TTCollection(io.BytesIO(ttc_bytes)).fonts[0]
    strikes   = font["sbix"].strikes      # {size: Strike}

    total = sum(len(strike.glyphs) for strike in strikes.values())
    progress = Progress(
        SpinnerColumn(style=palette[0]),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task("Extracting…", total=total)

    with progress:
        for size, strike in strikes.items():
            folder = OUT / f"{size}x{size}"
            folder.mkdir(exist_ok=True)
            cache: Dict[int,Tuple[bytes,Image.Image]] = {}
            for gid in strike.glyphs:
                result = extract_glyph(strike, gid, cache)
                if not result:
                    progress.advance(task_id)
                    continue
                data, img = result
                # build filename
                seq = codecs.decode("".join(esc(c) for c in HEX.findall(strike.glyphs[gid].glyphName)), "unicode_escape")
                name = cldr(seq)
                filename = safe(name) + ".png"
                dst = uniq(folder/filename, data)
                dst.write_bytes(data)
                progress.advance(task_id)

    console.print(Panel(f"☑  Done – wrote {total} PNGs → {OUT}",
                        style=Style(color=palette[0])))

signal.signal(signal.SIGINT, lambda *_: sys.exit("\nInterrupted."))
if __name__=="__main__":
    main()
