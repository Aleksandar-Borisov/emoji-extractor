#!/usr/bin/env python3
"""🍎 Emoji Extractor by Alek Borisov"""

import sys, io, re, hashlib, codecs, unicodedata, signal, urllib.request, warnings, argparse, plistlib
from pathlib          import Path
from typing           import Dict, Tuple, Optional, Set

import pyfiglet
from rich.console     import Console, Group
from rich.panel       import Panel
from rich.progress    import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TextColumn
from rich.text        import Text
from rich.style       import Style
from rich.markdown    import Markdown
from rich             import box

from PIL              import Image, ImageFile, ImageOps
from fontTools.ttLib  import TTCollection

for m in ("lzfse", "liblzfse", "pyliblzfse"):
    try:
        LZFSE = __import__(m)
        break
    except ModuleNotFoundError:
        LZFSE = None
if LZFSE is None:
    sys.exit("❌ Install pyliblzfse for .emjc support")

from pillow_heif import register_heif_opener
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pillow_heif")
register_heif_opener()

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--theme", choices=["orange","mono","high-contrast"], default="orange")
parser.add_argument("-h", "--help", action="store_true")
args, _ = parser.parse_known_args()
if args.help:
    Console().print(Markdown(__doc__))
    sys.exit()

PALETTES = {
    "orange":        ["#FFB74D","#FF9800","#FB8C00","#F57C00","#EF6C00"],  # light→dark orange
    "mono":          ["white"],
    "high-contrast": ["white","bright_white"],
}
palette      = PALETTES["orange"]
rainbow_iter = iter(lambda: palette.append(palette.pop(0)) or palette[0], None)

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
    except:
        APPLE_NAMES.clear()

def cldr(seq: str) -> str:
    if seq in APPLE_NAMES:
        return APPLE_NAMES[seq]
    norm = normalize_seq(seq)
    if norm in APPLE_NAMES:
        return APPLE_NAMES[norm]
    parts = [unicodedata.name(ch,"") for ch in norm]
    return " ".join(p.title() for p in parts if p).strip() or "Unnamed"

ESCAPE_RE = re.compile(r"([0-9A-Fa-f]{4,8})")
LZHD       = b"bvx0"
ImageFile.LOAD_TRUNCATED_IMAGES = True

def esc(h: str) -> str:
    return f"\\U{int(h,16):08X}"

def safe(text: str, limit=140) -> str:
    cleaned = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if c.isprintable() and c not in '/\\:*?"<>|'
    ).strip()
    return (cleaned or "unnamed")[:limit]

def uniq(path: Path, blob: bytes) -> Path:
    if not path.exists():
        return path
    h = hashlib.sha1(blob).hexdigest()[:8]
    base = path.with_name(f"{path.stem}-{h}{path.suffix}")
    i = 1
    while base.exists():
        base = path.with_name(f"{path.stem}-{h}_{i}{path.suffix}")
        i += 1
    return base

def dec_emjc(blob: bytes) -> bytes:
    if not blob.startswith(LZHD):
        raise RuntimeError
    return LZFSE.decompress(blob)

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

class GradientBar(BarColumn):
    def render(self, task):
        self.style = Style(color=next(rainbow_iter))
        return super().render(task)

def extract_glyph(strike, gid, cache: Dict[int,Tuple[bytes,Image.Image]], unknown: Set[str]):
    if gid in cache:
        return cache[gid]
    glyph = strike.glyphs[gid]
    tg    = glyph.graphicType
    if tg in DECODERS:
        data = DECODERS[tg](glyph.imageData)
        img  = Image.open(io.BytesIO(data)); img.load()
    elif tg in ("dupe","flip"):
        ref = glyph.referenceGlyphName
        ref_gid = next(i for i,g in strike.glyphs.items() if g.glyphName==ref)
        result = extract_glyph(strike, ref_gid, cache, unknown)
        if not result:
            return None
        data, img = result
        if tg=="flip":
            img = ImageOps.mirror(img)
            buf = io.BytesIO(); img.save(buf,"PNG"); data = buf.getvalue()
    else:
        try:
            raw = glyph.imageData
            img = Image.open(io.BytesIO(raw)); img.load()
            data = raw
        except:
            if tg is not None:
                unknown.add(tg)
            return None
    cache[gid] = (data, img)
    return cache[gid]

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
              border_style=Style(color=palette[1]), box=box.DOUBLE, padding=(0,1)),
        border_style=Style(color=palette[2]), box=box.ROUNDED, padding=(1,2),
    )

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
    strikes   = font["sbix"].strikes

    total = sum(len(s.glyphs) for s in strikes.values())
    progress = Progress(
        SpinnerColumn(style=Style(color=palette[0])),
        TextColumn("[bold]{task.description}", style=Style(color=palette[0])),
        GradientBar(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task("Extracting…", total=total)
    unknown = set()

    with progress:
        for size, strike in strikes.items():
            folder = OUT / f"{size}x{size}"
            folder.mkdir(exist_ok=True)
            cache: Dict[int,Tuple[bytes,Image.Image]] = {}
            for gid in strike.glyphs:
                res = extract_glyph(strike, gid, cache, unknown)
                if not res:
                    progress.advance(task_id)
                    continue
                data, img = res
                seq = codecs.decode("".join(esc(c) for c in ESCAPE_RE.findall(strike.glyphs[gid].glyphName)), "unicode_escape")
                name = cldr(seq)
                dst  = uniq(folder / f"{safe(name)}.png", data)
                dst.write_bytes(data)
                progress.advance(task_id)

    console.print(Panel(f"☑  Done – extracted {total} PNGs → {OUT}", border_style=Style(color=palette[1])))

    unknown.discard(None)
    if unknown:
        console.print(Panel(
            Text.assemble(("⚠️ Unknown graphicTypes:\n", Style(color=palette[3])),
                          *[(f" • {t}\n", Style(color=palette[0])) for t in sorted(unknown)]),
            title="Unrecognized SBIX Variants",
            border_style=Style(color=palette[3]),
        ))

signal.signal(signal.SIGINT, lambda *_: sys.exit("\nInterrupted."))
if __name__ == "__main__":
    main()
