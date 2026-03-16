import json
from pathlib import Path


def generate_manifest(video_data: dict, scored_clips: list, output_dir: Path, console=None):
    """
    Node 5 — deliver_manifest
    Generates the final human-readable Markdown summary and structured JSON.
    """
    if console:
        console.print("\n[bold blue]┌─ Step 5/5 — Manifest & Delivery[/bold blue]")
        
    # ── 1. Create JSON Manifest ───────────────────────────────────────────────
    manifest_path = output_dir / "clips_manifest.json"
    manifest_data = {
        "video_title": video_data.get("title", ""),
        "total_clips": len(scored_clips),
        "clips": []
    }
    
    for i, clip in enumerate(scored_clips, 1):
        manifest_data["clips"].append({
            "clip_id": i,
            "file": f"clip_{i:02d}.mp4",
            "start_sec": clip["start_sec"],
            "end_sec": clip["end_sec"],
            "score": clip.get("average_score", 0),
            "suggested_caption": clip.get("caption_hook", ""),
            "why_it_works": clip.get("why_it_works", ""),
            "transcript_excerpt": clip.get("transcript_excerpt", "")
        })

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)


    # ── 2. Create Markdown Summary ───────────────────────────────────────────
    md_path = output_dir / "clips_summary.md"
    
    md_text = [
        f"# Clips Summary: {video_data.get('title', 'Video')}",
        f"**Source URL:** {video_data.get('url', '')}",
        f"**Clips Extracted:** {len(scored_clips)}",
        "---",
        ""
    ]
    
    for i, clip in enumerate(scored_clips, 1):
        md_text.extend([
            f"## 🎬 Clip {i} — {clip.get('average_score', 0)}/10",
            f"**File:** `clip_{i:02d}.mp4` ({clip['start_sec']}s - {clip['end_sec']}s)",
            "",
            f"> **Caption Hook:** {clip.get('caption_hook', '')}",
            "",
            f"**Why it works:** {clip.get('why_it_works', '')}",
            "",
            "**Transcript Excerpt:**",
            f"_{clip.get('transcript_excerpt', '')}_",
            "---",
            ""
        ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_text))

    if console:
        console.print(f"[bold green]   ✓ Saved {manifest_path.name} and {md_path.name}[/bold green]")
