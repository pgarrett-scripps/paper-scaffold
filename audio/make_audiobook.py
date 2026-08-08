#!/usr/bin/env python3
"""Build a chaptered audiobook (.m4b) of the manuscript.

Splits the prose at its section/subsection headings into chapters, narrates each
with Piper, then muxes them into one .m4b with embedded chapter markers (titles
+ timestamps) so a player can jump between sections.

    make_audiobook.py        -> paper.m4b     (main text)
    make_audiobook.py si     -> paper_si.m4b  (Supporting Information)

Titles, descriptions, voice, and pronunciations all come from config.py.
"""
import re
import subprocess
import sys
import wave
from pathlib import Path

import config
from extract_prose import (
    clean, extract_abstract, extract_body, report_unmapped, strip_balanced,
)

HERE = Path(__file__).resolve().parent
VOICE = HERE / "models" / f"{config.VOICE_NAME}.onnx"

# --- which document to narrate: `main` (default) or `si` ---------------------
DOC = "si" if (len(sys.argv) > 1 and sys.argv[1] == "si") else "main"
if DOC == "si":
    SRC = config.SI_TYP
    CHAPDIR = HERE / "chapters_si"
    OUT = HERE / "paper_si.m4b"
    COVER = HERE / "cover_si.png"
    TITLE = config.SI_TITLE
    DESC = config.SI_DESC
else:
    SRC = config.PAPER_TYP
    CHAPDIR = HERE / "chapters"
    OUT = HERE / "paper.m4b"
    COVER = HERE / "cover_main.png"
    TITLE = config.TITLE
    DESC = config.MAIN_DESC

SPOKEN_TITLE = config.speakable(TITLE)


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def build_chapters(raw):
    """Return [(title, spoken_text), ...] -- front matter first, then =/== sections."""
    chapters = []

    if DOC == "si":
        # front matter: the overview paragraph before the first "= " heading
        first = raw.find("\n= ")
        intro = clean(raw[:first])
        chapters.append(("Overview", f"{SPOKEN_TITLE}. Overview.\n\n{intro}"))
        body = raw[first:]
    else:
        # abstract (from config.typ), then the marked prose body
        abstract = extract_abstract()
        if not abstract:
            sys.exit("error: the abstract in config.typ is empty")
        chapters.append(("Abstract", f"{SPOKEN_TITLE}. Abstract.\n\n{abstract}"))
        body = extract_body(raw)

    body = strip_balanced(body, "#figure(")

    heading = re.compile(r"(?m)^(={1,3})\s+([^\n<]+?)(?:\s*<[^>]+>)?\s*$")
    marks = list(heading.finditer(body))
    for i, m in enumerate(marks):
        title = m.group(2).strip().rstrip(".")
        chunk = body[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(body))]
        text = clean(chunk)
        if text:
            chapters.append((title, f"{title}.\n\n{text}"))
    return chapters


def wav_seconds(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main():
    raw = SRC.read_text()
    chapters = build_chapters(raw)
    # Before spending the synthesis time on it: say what got dropped.
    report_unmapped()
    CHAPDIR.mkdir(exist_ok=True)

    # Piper is a library call, not a subprocess. It used to be a binary fetched
    # by curl, which is why this once needed an LD_LIBRARY_PATH and a process per
    # chapter. The ONNX model is loaded ONCE here rather than per chapter, which
    # is the whole saving: it was being re-read from disk for every section.
    if not VOICE.is_file():
        raise SystemExit(f"error: no voice at {VOICE}\n  fix: just audio-setup")
    from piper import PiperVoice
    voice = PiperVoice.load(VOICE)

    # 1. synthesize each chapter to its own WAV, record durations.
    #
    # Synthesis dominates the runtime -- minutes for a full manuscript -- and
    # used to run silent between chapter lines. The bar shows which chapter is
    # being spoken and how far along the book is; it is transient (gone when
    # done) and renders nothing when output is piped, so logs keep only the
    # per-chapter lines they always had.
    from rich.progress import (BarColumn, Progress, TextColumn,
                               TimeElapsedColumn)
    wavs, starts, cur = [], [], 0.0
    with Progress(
        TextColumn("  narrating"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TextColumn("[dim]{task.fields[title]}[/]"),
        transient=True,
    ) as prog:
        task = prog.add_task("", total=len(chapters), title="")
        for i, (title, text) in enumerate(chapters):
            prog.update(task, title=title)
            wav = CHAPDIR / f"{i:02d}.wav"
            with wave.open(str(wav), "wb") as wf:
                voice.synthesize_wav(text, wf)
            dur = wav_seconds(wav)
            starts.append(cur)
            cur += dur
            wavs.append(wav)
            prog.console.print(
                f"  ch{i:02d} {int(cur//60):3d}:{int(cur%60):02d}  {title}")
            prog.advance(task)
    total = cur

    # 2. ffmpeg concat list
    listf = CHAPDIR / "list.txt"
    listf.write_text("".join(f"file '{w.name}'\n" for w in wavs))

    # 3. FFMETADATA chapter file (times in milliseconds)
    meta = [";FFMETADATA1",
            f"title={TITLE}",
            f"artist={config.AUTHOR}",
            f"album_artist={config.AUTHOR}",
            f"album={TITLE}",
            f"composer=Piper TTS ({config.VOICE_NAME})",   # the "narrator"
            f"genre={config.GENRE}",
            f"date={config.YEAR}",
            f"comment={DESC}",
            f"description={DESC}"]
    for i, (title, _) in enumerate(chapters):
        start_ms = int(starts[i] * 1000)
        end_ms = int((starts[i + 1] if i + 1 < len(starts) else total) * 1000)
        safe = title.replace("=", "-").replace("\n", " ")
        meta += ["[CHAPTER]", "TIMEBASE=1/1000",
                 f"START={start_ms}", f"END={end_ms}", f"title={safe}"]
    metaf = CHAPDIR / "chapters.ffmeta"
    metaf.write_text("\n".join(meta) + "\n")

    # 4. ensure cover art exists (generated by make_cover.py)
    if not COVER.exists():
        subprocess.run([sys.executable, str(HERE / "make_cover.py")], check=False)

    # 5. mux to .m4b: AAC audio + chapters + embedded cover art
    ff = ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(listf),  # 0: audio
           "-i", str(metaf)]                                # 1: chapter metadata
    if COVER.exists():
        cmd += ["-i", str(COVER),                           # 2: cover
                "-map", "0:a", "-map", "2:v",
                "-map_metadata", "1",
                "-c:a", "aac", "-b:a", "64k",
                "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
    else:
        cmd += ["-map_metadata", "1", "-c:a", "aac", "-b:a", "64k"]
    cmd.append(str(OUT))
    subprocess.run(cmd, check=True)

    mb = OUT.stat().st_size / 1e6
    print(f"\nwrote {OUT.name}  ({len(chapters)} chapters, "
          f"{int(total//60)}:{int(total%60):02d}, {mb:.0f} MB)")


if __name__ == "__main__":
    main()
