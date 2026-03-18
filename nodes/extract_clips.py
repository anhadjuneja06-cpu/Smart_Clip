import json
import os
import shutil
import subprocess
from pathlib import Path


from datetime import timedelta


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


def _format_timestamp(seconds: float) -> str:
    """Formats seconds into SRT timestamp HH:MM:SS,mmm"""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    msecs = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{msecs:03}"


def _create_srt(segments: list, actual_start: float, actual_end: float, srt_path: Path):
    """Generates a fast-paced 'moving' SRT file (1-3 words at a time)."""
    with open(srt_path, "w", encoding="utf-8") as f:
        count = 1
        for seg in segments:
            # Check if segment overlaps with clip
            seg_start = seg["start_sec"]
            seg_end = seg["end_sec"]
            
            if seg_end <= actual_start or seg_start >= actual_end:
                continue
            
            words = seg.get("words", [])

            # ── Preferred: word-level "moving" effect ────────────────────────
            if words:
                # Reels-style captions: phrase-based groups timed to speech.
                # Goals:
                # - Natural reading (not word-flash jitter)
                # - Avoid wrapping (wrapping makes the text block "jump" vertically)
                # - Use word timestamps for accurate timing

                # Tunables (can be overridden via env if needed)
                max_words = int(os.getenv("OZ_SUB_MAX_WORDS", "6") or 6)
                # Ensure captions feel natural (avoid single-word "income" then "housing" flashes)
                min_words = int(os.getenv("OZ_SUB_MIN_WORDS", "2") or 2)
                max_chars = int(os.getenv("OZ_SUB_MAX_CHARS", "28") or 28)  # keep single-line
                max_dur = float(os.getenv("OZ_SUB_MAX_DUR", "1.6") or 1.6)
                min_dur = float(os.getenv("OZ_SUB_MIN_DUR", "0.7") or 0.7)
                gap_break = float(os.getenv("OZ_SUB_GAP_BREAK", "0.35") or 0.35)

                # Filter to clip range
                in_range = []
                for w in words:
                    try:
                        ws = float(w["start"])
                        we = float(w["end"])
                        txt = str(w.get("word", "")).strip()
                    except Exception:
                        continue
                    if not txt:
                        continue
                    if we <= actual_start or ws >= actual_end:
                        continue
                    in_range.append({"start": ws, "end": we, "word": txt})

                buf = []
                buf_start = None
                buf_end = None

                def flush(force_end: float | None = None):
                    nonlocal count, buf, buf_start, buf_end
                    if not buf or buf_start is None or buf_end is None:
                        buf = []
                        buf_start = None
                        buf_end = None
                        return

                    text = " ".join([x["word"] for x in buf]).strip()
                    if not text:
                        buf = []
                        buf_start = None
                        buf_end = None
                        return

                    start = buf_start
                    end = force_end if force_end is not None else buf_end
                    if end <= start:
                        buf = []
                        buf_start = None
                        buf_end = None
                        return

                    # Relative times
                    rel_start = max(0.0, start - actual_start)
                    rel_end = min(actual_end - actual_start, end - actual_start)
                    if (rel_end - rel_start) < min_dur:
                        rel_end = min(actual_end - actual_start, rel_start + min_dur)
                    if rel_end <= rel_start:
                        buf = []
                        buf_start = None
                        buf_end = None
                        return

                    f.write(f"{count}\n")
                    f.write(f"{_format_timestamp(rel_start)} --> {_format_timestamp(rel_end)}\n")
                    f.write(f"{text}\n\n")
                    count += 1

                    buf = []
                    buf_start = None
                    buf_end = None

                for idx, w in enumerate(in_range):
                    if buf_start is None:
                        buf_start = w["start"]
                    buf.append(w)
                    buf_end = w["end"]

                    text_len = len(" ".join([x["word"] for x in buf]))
                    dur = (buf_end - buf_start) if (buf_start is not None and buf_end is not None) else 0.0

                    # Lookahead gap / punctuation
                    next_start = in_range[idx + 1]["start"] if (idx + 1) < len(in_range) else None
                    gap = (next_start - w["end"]) if next_start is not None else 0.0
                    ends_punct = w["word"].endswith((".", "?", "!", ","))

                    should_break = False
                    if len(buf) >= max_words:
                        should_break = True
                    if text_len >= max_chars:
                        should_break = True
                    if dur >= max_dur and len(buf) >= min_words:
                        should_break = True
                    if gap >= gap_break and len(buf) >= min_words:
                        should_break = True
                    if ends_punct and len(buf) >= min_words:
                        should_break = True

                    if should_break:
                        # End at next word start when available for a clean handoff
                        flush(force_end=next_start if next_start is not None else buf_end)

                flush()
                continue

            # ── Fallback: no word timestamps, time text chunks across segment ─
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            seg_clip_start = max(seg_start, actual_start)
            seg_clip_end = min(seg_end, actual_end)
            seg_dur = max(0.0, seg_clip_end - seg_clip_start)
            if seg_dur <= 0.0:
                continue

            tokens = text.split()
            if not tokens:
                continue

            # Bigger chunks read more naturally (less "shouting" / flashing)
            chunk_size = 10
            chunks = [" ".join(tokens[j : j + chunk_size]) for j in range(0, len(tokens), chunk_size)]
            if not chunks:
                continue

            min_chunk_dur = 0.80
            total = len(chunks)
            for idx, chunk_text in enumerate(chunks):
                rel_start = (seg_clip_start - actual_start) + (seg_dur * (idx / total))
                rel_end = (seg_clip_start - actual_start) + (seg_dur * ((idx + 1) / total))
                if (rel_end - rel_start) < min_chunk_dur:
                    rel_end = min(actual_end - actual_start, rel_start + min_chunk_dur)
                if rel_end <= rel_start:
                    continue

                f.write(f"{count}\n")
                f.write(f"{_format_timestamp(rel_start)} --> {_format_timestamp(rel_end)}\n")
                f.write(f"{chunk_text.strip()}\n\n")
                count += 1


def extract_segments(video_path: str, transcript_path: str, scored_clips: list, output_dir: Path, console=None):
    """
    Node 4 — extract_clips
    Uses ffmpeg to crop to 9:16, add 'moving' subtitles, and clean up.
    """
    if console:
        console.print("\n[bold blue]┌─ Step 4/5 — Extracting Clips (Moving Subtitles + Polish)[/bold blue]")

    # Load transcript for context and word-level SRT generation
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    segments = transcript_data.get("segments", [])

    ffmpeg_exe = _get_ffmpeg_path()
    output_files = []
    output_dir = output_dir.absolute()
    max_clips_env = os.getenv("OZ_MAX_CLIPS", "").strip()
    max_clips = int(max_clips_env) if max_clips_env.isdigit() else 0

    # Clean up old outputs so you only see the current batch
    for p in output_dir.glob("clip_*.mp4"):
        try:
            p.unlink()
        except Exception:
            pass
    for p in output_dir.glob("clip_*.srt"):
        try:
            p.unlink()
        except Exception:
            pass

    for i, clip in enumerate(scored_clips, 1):
        if max_clips and i > max_clips:
            break
        # Score threshold gate (scoring node also filters, but keep it defensive here)
        try:
            if float(clip.get("average_score", 0)) <= 7:
                continue
        except Exception:
            pass
        target_start = clip["start_sec"]
        target_end = clip["end_sec"]
        
        # ── 1. Find the closest segment indices ──────────────────────────────
        # Instead of exact match, find the segment that contains or is closest to target
        start_idx = 0
        min_start_diff = float('inf')
        end_idx = len(segments) - 1
        min_end_diff = float('inf')

        for idx, seg in enumerate(segments):
            # Check for start
            s_diff = abs(seg["start_sec"] - target_start)
            if s_diff < min_start_diff:
                min_start_diff = s_diff
                start_idx = idx
            
            # Check for end
            e_diff = abs(seg["end_sec"] - target_end)
            if e_diff < min_end_diff:
                min_end_diff = e_diff
                end_idx = idx

        # ── 2. Apply One-Segment Lookback ───────────────────────────────────
        buffered_start_idx = max(0, start_idx - 1)
        actual_start = segments[buffered_start_idx]["start_sec"]
        # Choose a natural ending:
        # - Prefer a sentence boundary in 30–90s (ideal)
        # - If none exists, allow up to 120s MAX (still sentence boundary)
        # - If it still can't end naturally <=120s, skip rendering and report a suggestion.
        min_end = actual_start + 30
        preferred_max_end = actual_start + 90
        hard_max_end = actual_start + 120
        model_target_end = float(target_end)

        punct = (".", "?", "!")
        sentence_candidates_preferred = []
        sentence_candidates_hard = []
        for j in range(buffered_start_idx, len(segments)):
            e = float(segments[j]["end_sec"])
            if e < min_end:
                continue
            if e > hard_max_end:
                break
            txt = (segments[j].get("text") or "").strip()
            if txt.endswith(punct):
                if e <= preferred_max_end:
                    sentence_candidates_preferred.append(j)
                sentence_candidates_hard.append(j)

        if sentence_candidates_preferred:
            end_idx = min(sentence_candidates_preferred, key=lambda j: abs(float(segments[j]["end_sec"]) - model_target_end))
        elif sentence_candidates_hard:
            end_idx = min(sentence_candidates_hard, key=lambda j: abs(float(segments[j]["end_sec"]) - model_target_end))
        else:
            # No sentence boundary within 120s from start: skip and suggest.
            if console:
                console.print(
                    f"[yellow]   ! Skipping clip {i}: can't find a sentence-ending within 120s. Suggested segment: {target_start:.2f}s → {target_end:.2f}s[/yellow]"
                )
            continue

        actual_end = float(segments[end_idx]["end_sec"]) + 0.2
        duration = actual_end - actual_start
        fade_duration = 0.1
        fade_start = duration - fade_duration

        # If we still ended up too short, extend to the first segment end past 30s.
        if duration < 30:
            j = end_idx
            while j < (len(segments) - 1) and float(segments[j]["end_sec"]) < min_end:
                j += 1
            end_idx = j
            actual_end = min(float(segments[end_idx]["end_sec"]) + 0.2, hard_max_end)
            duration = actual_end - actual_start
            if duration < 30:
                if console:
                    console.print(f"[yellow]   ! Skipping clip {i}: {duration:.1f}s (<30s after alignment)[/yellow]")
                continue

        # Absolute ceiling (should be rare given sentence-boundary selection)
        if duration > 120:
            if console:
                console.print(
                    f"[yellow]   ! Skipping clip {i}: natural ending exceeds 120s. Suggested segment: {actual_start:.2f}s → {actual_end:.2f}s[/yellow]"
                )
            continue

        # ── 3. Generate 'Moving' SRT file ───────────────────────────────────
        srt_path = output_dir / f"clip_{i:02d}.srt"
        _create_srt(segments, actual_start, actual_end, srt_path)

        out_name = output_dir / f"clip_{i:02d}.mp4"
        
        if console:
            console.print(f"[dim]   → Clip {i}: {duration:.1f}s | Moving Subs | Polish applied[/dim]")

        # ── 4. Stylized FFmpeg: Vertical + Subs + Polish ──────────────────────
        srt_sub_path = str(srt_path).replace("\\", "/").replace(":", "\\:")

        # True vertical conversion (fills 9:16):
        # - Scale to fill 1080x1920, then center-crop to exact 9:16.
        # This converts horizontal -> vertical in a Shorts/Reels-native way.
        # Note: Filling 9:16 requires cropping some width on wide sources.
        # IMPORTANT: do trimming inside the filtergraph (trim/atrim) to avoid
        # black tails / abrupt cut artifacts from seek behavior.
        filter_complex = (
            f"[0:v]trim=start={actual_start}:end={actual_end},setpts=PTS-STARTPTS,"
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,"
            f"setsar=1,"
            f"subtitles='{srt_sub_path}':force_style='"
            f"FontName=Helvetica,"
            f"FontSize=16,"
            f"Bold=1,"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=1,"
            f"Outline=1,"
            f"Shadow=0,"
            f"Alignment=2,"
            f"MarginV=25,"
            f"MarginL=70,"
            f"MarginR=70"
            f"',"
            f"fade=t=out:st={fade_start}:d=0.5[v]; "
            f"[0:a]atrim=start={actual_start}:end={actual_end},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={fade_start}:d=0.5[a]"
        )

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-shortest",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_name)
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            output_files.append(str(out_name))
            # Auto-cleanup temporary SRT files
            if srt_path.exists():
                srt_path.unlink()
        except subprocess.CalledProcessError:
            if console:
                console.print(f"[red]   ✗ Failed to extract clip {i}[/red]")
            continue

    if console:
        console.print(f"[bold green]   ✓ Successfully extracted professional visual clips ({len(output_files)})[/bold green]")
        
    return output_files
