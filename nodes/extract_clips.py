import json
import os
import shutil
import subprocess
from pathlib import Path


def _get_ffmpeg_path():
    """Finds ffmpeg specifically if installed via winget"""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for p in winget_dir.rglob("ffmpeg.exe"):
                return str(p)
    return "ffmpeg"


def extract_segments(video_path: str, transcript_path: str, scored_clips: list, output_dir: Path, console=None):
    """
    Node 4 — extract_clips
    Uses ffmpeg to cut clips. Now includes ONE SEGMENT LOOKBACK for context.
    """
    if console:
        console.print("\n[bold blue]┌─ Step 4/5 — Extracting Clips (with buffering)[/bold blue]")

    # Load the full transcript to find the "previous" segments for buffering
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    segments = transcript_data.get("segments", [])

    ffmpeg_exe = _get_ffmpeg_path()
    output_files = []

    for i, clip in enumerate(scored_clips, 1):
        target_start = clip["start_sec"]
        target_end = clip["end_sec"]
        
        # ── 1. Find the segment indices for the chosen timestamps ─────────────
        start_idx = 0
        end_idx = len(segments) - 1
        
        for idx, seg in enumerate(segments):
            if abs(seg["start_sec"] - target_start) < 0.1:
                start_idx = idx
            if abs(seg["end_sec"] - target_end) < 0.1:
                end_idx = idx

        # ── 2. Apply One-Segment Lookback (The "Buffer") ─────────────
        # We start one segment earlier so the clip doesn't feel abrupt
        buffered_start_idx = max(0, start_idx - 1)
        actual_start = segments[buffered_start_idx]["start_sec"]
        
        # ── 3. Add Precise Trailing Buffer for Smoother Endings ──────────────
        # We add a very small 0.2s buffer to the end to ensure we don't cut the last syllable,
        # but not enough to pull in the next sentence.
        actual_end = segments[end_idx]["end_sec"] + 0.2
        
        duration = actual_end - actual_start
        # Fade out over the last 0.1 seconds just to avoid audio pops
        fade_duration = 0.1
        fade_start = duration - fade_duration

        out_name = output_dir / f"clip_{i:02d}.mp4"
        output_files.append(str(out_name))
        
        if console:
            console.print(f"[dim]   → Clip {i}: {duration:.1f}s (Smooth Ending Applied)[/dim]")

        # Precise re-encoding with Audio/Video Fade Out
        cmd = [
            ffmpeg_exe,
            "-y",
            "-ss", str(actual_start),
            "-i", video_path,
            "-t", str(duration),
            "-filter_complex", f"[0:v]fade=t=out:st={fade_start}:d=0.5[v]; [0:a]afade=t=out:st={fade_start}:d=0.5[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-crf", "20",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_name)
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            if console:
                console.print(f"[red]   ✗ Failed to extract clip {i}[/red]")
            continue

    if console:
        console.print(f"[bold green]   ✓ Successfully extracted {len(output_files)} high-quality precise clips[/bold green]")
        
    return output_files
