🍎 **Emoji Extractor** by Alek Borisov

A command-line tool that extracts every color emoji glyph from the system font into individual PNG files, with a beautiful, orange-themed user interface—without ever touching your global Python installation or Xcode setup.

---

## 📦 What It Does

1. **Creates an isolated virtual environment** in a temporary folder (`Emojis - temp/`), so no dependencies leak into your system or IDE.  
2. **Installs all required libraries** (`Pillow`, `fonttools`, `pillow-heif`, `pyliblzfse`, `rich`, `pyfiglet`) inside that venv.  
3. **Runs** `emoji-extractor.py` to parse the color–emoji font, decompress every bitmap (PNG, TIFF, HEIC, EMJC), and save each glyph as a PNG.  
4. **Cleans up** by deactivating and deleting the venv—leaving only your output files behind.

---

## ⚙️ Installation & Usage

```bash
git clone https://github.com/<your-username>/emoji-extractor.git
cd emoji-extractor
bash run-extract.txt
```

- **Virtual environment** will appear as `Emojis - temp/` next to the script.  
- **Output emojis** will be in `Emojis/` with subfolders by resolution (e.g. `64x64/🧊 Ice Cube.png`).  
- **Cleanup**: `Emojis - temp/` is automatically removed at the end.  

---

## 🚀 How It Works

1. **Font Loading**  
   - The script reads the installed color-emoji font (TrueType Collection).  
2. **Glyph Extraction**  
   - For each bitmap strike (size), all glyphs are decoded—handling compression and mirrored (“flip”) variants.  
3. **Name Resolution**  
   - Filenames use human-friendly labels drawn from the system’s own emoji name database (with fallback to Unicode’s CLDR and built-in names), so you get “Ice Cube.png” instead of a raw codepoint.  
4. **Parallel Processing**  
   - Extraction runs across all CPU cores for maximum speed, with a live, gradient-orange progress bar and spinner.  

---

## 📂 Output Layout

    emoji-extractor/
    ├─ Emojis/
    │  ├─ 64x64/
    │  │  ├─ 🧊 Ice Cube.png
    │  │  ├─ 😊 Smiling Face.png
    │  │  └─ …
    │  └─ 128x128/
    │     └─ …
    └─ run-extract.txt

---

## ⚖️ Legal & Usage Notes

- This tool reads your system’s proprietary color-emoji font. **You must comply with your operating system’s Terms of Service and font licensing**—this script makes no representation or warranty.  
- **Do not** redistribute any extracted glyphs beyond personal or internal use without verifying you have the rights to do so.  
- All emoji names and bitmaps remain the intellectual property of their respective copyright holders.

---

## 🚫 Restrictions

By running or distributing this tool, you agree **not** to:

- Modify or fork the extraction logic itself.  
- Embed or integrate the code into other software products.  
- Use the extracted assets for large-scale redistribution, resale, or in AI training datasets.  

All rights reserved by the author. For any other uses, **seek written permission**.

---

## 📜 License

**All Rights Reserved** – see [LICENSE](LICENSE).  
Permission is granted to **use** and **share** this tool unmodified for personal or internal purposes only. 
