#!/usr/bin/env python3
"""
OZListings YouTube Clip Agent
==============================
Phase 1 CLI -- Video ingest + transcription pipeline.

Usage:
    python agent.py --url "https://youtube.com/watch?v=..."
    python agent.py --url "https://youtube.com/watch?v=..." --model small
"""

import argparse
import json
import sys
import time
import io
import os
import shutil
from pathlib import Path

# Fix Windows terminal encoding so Unicode characters display correctly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure ffmpeg is in PATH for both yt-dlp and whisper
def _add_ffmpeg_to_path():
    if shutil.which("ffmpeg"):
        return
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for p in winget_dir.rglob("ffmpeg.exe"):
                ffmpeg_dir = str(p.parent)
                os.environ["PATH"] += os.pathsep + ffmpeg_dir
                return

_add_ffmpeg_to_path()

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="OZListings YouTube Clip Agent — Phase 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Whisper model sizes (speed vs accuracy trade-off):
  tiny   -- fastest, ~75 MB,  lower accuracy
  base   -- fast,   ~145 MB, good accuracy       <- default
  small  -- slower, ~460 MB, better accuracy
  medium -- slow,   ~1.5 GB, high accuracy
  large  -- slowest,~2.9 GB, best accuracy (recommended for final demo)

Examples:
  python agent.py --url "https://youtube.com/watch?v=abc123"
  python agent.py --url "https://youtube.com/watch?v=abc123" --model small
        """,
    )
    parser.add_argument(
        "--url", required=True, help="YouTube video URL to process"
    )
    args = parser.parse_args()

    # ── Banner ───────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]OZListings YouTube Clip Agent[/bold cyan]\n"
            "[dim]Phase 1 — Transcript Pipeline[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    start_time = time.time()

    # ── Node 1: Video Ingest ─────────────────────────────────────────────────
    try:
        from nodes.video_ingest import ingest_video
        video_data = ingest_video(args.url, console)
    except Exception as e:
        console.print(f"\n[bold red]✗ Video ingest failed:[/bold red] {e}")
        sys.exit(1)

    # ── Output dir + transcript cache ────────────────────────────────────────
    output_dir = Path("oz_clips") / video_data["safe_title"]
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = output_dir / "transcript.json"

    force_transcribe = os.getenv("OZ_FORCE_TRANSCRIBE", "").strip().lower() in {"1", "true", "yes", "y"}
    segments = None
    if transcript_path.exists() and not force_transcribe:
        try:
            cached = json.loads(transcript_path.read_text(encoding="utf-8"))
            cached_segments = cached.get("segments", [])
            if isinstance(cached_segments, list) and len(cached_segments) > 0:
                segments = cached_segments
                console.print("\n[bold blue]┌─ Step 2/2 — Transcribe Audio (cached)[/bold blue]")
                console.print(f"[dim]   Using cached transcript: {transcript_path}[/dim]")
        except Exception:
            segments = None

    # ── Node 2: Transcribe Audio ─────────────────────────────────────────────
    if segments is None:
        try:
            from nodes.transcribe_audio import transcribe
            segments = transcribe(video_data["audio_path"], args.model, console)
        except Exception as e:
            console.print(f"\n[bold red]✗ Transcription failed:[/bold red] {e}")
            sys.exit(1)

        transcript_data = {
            "source_url": args.url,
            "title": video_data["title"],
            "duration_seconds": video_data["duration_seconds"],
            "segments": segments,
        }
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

    # ── Node 3: LLM Scoring Agent ────────────────────────────────────────────
    try:
        from nodes.score_segments import score_transcript
        scoring_result = score_transcript(transcript_path, console)
        clips = scoring_result.get("clips", [])
        if not clips:
            console.print("\n[yellow]Pipeline finished: No clips met the scoring criteria.[/yellow]")
            sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]✗ Scoring failed:[/bold red] {e}")
        sys.exit(1)

    # ── Node 4: Extract Clips ────────────────────────────────────────────────
    try:
        from nodes.extract_clips import extract_segments
        output_mp4s = extract_segments(video_data["video_path"], transcript_path, clips, output_dir, console)
    except Exception as e:
        console.print(f"\n[bold red]✗ Clip extraction failed:[/bold red] {e}")
        sys.exit(1)

    # ── Node 5: Deliver Manifest ─────────────────────────────────────────────
    try:
        from nodes.deliver_manifest import generate_manifest
        video_data["url"] = args.url
        generate_manifest(video_data, clips, output_dir, console)
    except Exception as e:
        console.print(f"\n[bold red]✗ Manifest generation failed:[/bold red] {e}")
        sys.exit(1)

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = round(time.time() - start_time, 1)
    console.print()
    console.print(Rule(style="green"))
    console.print(
        f"\n[bold green]🎉 FULL PIPELINE COMPLETE[/bold green] in [cyan]{elapsed}s[/cyan]\n"
    )
    console.print(f"  [bold]Video:[/bold] {video_data['title']}")
    console.print(f"  [bold]Clips generated:[/bold] {len(clips)}")
    console.print(f"  [bold]Output folder:[/bold] {output_dir.absolute()}\n")
    
    for i, clip in enumerate(clips, 1):
        avg = clip.get('average_score', 0)
        console.print(f"  [bold cyan]▶ Clip {i:02d}.mp4[/bold cyan] [dim]({avg}/10)[/dim] — {clip.get('caption_hook', '')}")

    console.print("\n[bold]Ready to post![/bold]\n")

if __name__ == "__main__":
    main()
