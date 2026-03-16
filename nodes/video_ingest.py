import yt_dlp
import re
import os
import shutil
from pathlib import Path


def get_ffmpeg_dir():
    if shutil.which("ffmpeg"):
        return None
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for p in winget_dir.rglob("ffmpeg.exe"):
                return str(p.parent)
    return None


def ingest_video(url: str, console=None) -> dict:
    """
    Node 1 — video_ingest
    Downloads video and extracts audio from a YouTube URL.

    Returns:
        dict with keys: title, safe_title, video_path, audio_path,
                        duration_seconds, description
    """
    ffmpeg_dir = get_ffmpeg_dir()

    if console:
        console.print("\n[bold blue]┌─ Step 1/2 — Video Ingest[/bold blue]")
        console.print(f"[dim]   URL: {url}[/dim]")

    output_base = Path("oz_clips/_downloads")
    output_base.mkdir(parents=True, exist_ok=True)

    # ── Get video metadata ───────────────────────────────────────────────────
    ydl_opts_info = {"quiet": True, "no_warnings": True}
    if ffmpeg_dir:
        ydl_opts_info["ffmpeg_location"] = ffmpeg_dir
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "unknown_video")
    duration = info.get("duration", 0)
    description = info.get("description", "")
    safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:60]

    if console:
        mins, secs = divmod(duration, 60)
        console.print(f"[green]   ✓ Found:[/green] {title}")
        console.print(f"[dim]   Duration: {mins}m {secs}s[/dim]")

    video_path = output_base / f"{safe_title}.mp4"
    audio_path = output_base / f"{safe_title}.wav"

    # ── Download video ───────────────────────────────────────────────────────
    if video_path.exists():
        if console:
            console.print("[dim]   → Video already cached, skipping download[/dim]")
    else:
        if console:
            console.print("[yellow]   → Downloading video...[/yellow]")
        ydl_opts_video = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(video_path),
            "quiet": True,
            "no_warnings": True,
        }
        if ffmpeg_dir:
            ydl_opts_video["ffmpeg_location"] = ffmpeg_dir
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            ydl.download([url])

    # ── Extract audio as WAV ─────────────────────────────────────────────────
    if audio_path.exists():
        if console:
            console.print("[dim]   → Audio already cached, skipping extraction[/dim]")
    else:
        if console:
            console.print("[yellow]   → Extracting audio (WAV)...[/yellow]")
        ydl_opts_audio = {
            "format": "bestaudio/best",
            "outtmpl": str(output_base / safe_title),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }
        if ffmpeg_dir:
            ydl_opts_audio["ffmpeg_location"] = ffmpeg_dir
        with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
            ydl.download([url])

    if console:
        console.print("[bold green]   ✓ Ingest complete[/bold green]")

    return {
        "title": title,
        "safe_title": safe_title,
        "video_path": str(video_path),
        "audio_path": str(audio_path),
        "duration_seconds": duration,
        "description": description,
    }
