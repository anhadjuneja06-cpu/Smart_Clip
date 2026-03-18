import os
import httpx
from deepgram import DeepgramClient

_MODEL_SIZES_MB = {
    "tiny": "75",
    "base": "145",
    "small": "460",
    "medium": "1500",
    "large": "2900",
}

def _as_dict(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    # Fall back: some SDK objects are pydantic-like / attr objects
    try:
        return dict(obj)
    except Exception:
        return None


def _extract_words(dg_response) -> list[dict]:
    """
    Normalize Deepgram response into a list of {word,start,end}.
    Uses punctuated_word when available so segments read naturally.
    """
    data = _as_dict(dg_response)
    if not data:
        return []

    results = data.get("results") or {}
    if not isinstance(results, dict):
        results = _as_dict(results) or {}

    channels = results.get("channels") or []
    if not isinstance(channels, list):
        channels = _as_dict(channels) or []
    if not channels:
        return []
    ch0 = channels[0]
    if not isinstance(ch0, dict):
        ch0 = _as_dict(ch0) or {}

    alternatives = (ch0.get("alternatives") or [])
    if not isinstance(alternatives, list):
        alternatives = _as_dict(alternatives) or []
    if not alternatives:
        return []
    alt0 = alternatives[0]
    if not isinstance(alt0, dict):
        alt0 = _as_dict(alt0) or {}

    words = alt0.get("words") or []
    if not isinstance(words, list):
        words = _as_dict(words) or []

    out = []
    for w in words:
        if not isinstance(w, dict):
            w = _as_dict(w) or {}
        word = w.get("punctuated_word") or w.get("word") or ""
        start = w.get("start")
        end = w.get("end")
        if not word or start is None or end is None:
            continue
        out.append({"word": str(word), "start": float(start), "end": float(end)})
    return out


def _reconstruct_segments(word_data: list[dict]) -> list[dict]:
    """Turn word-level timestamps into readable sentence-ish segments."""
    if not word_data:
        return []

    segments: list[dict] = []
    current_words: list[dict] = []
    current_start: float | None = None
    last_end: float | None = None

    # Heuristics: break on sentence punctuation, long gaps, or very long runs
    max_words = 48
    gap_break_sec = 0.90
    end_punct = (".", "?", "!")

    for wi in word_data:
        word = (wi.get("word") or "").strip()
        if not word:
            continue

        start = float(wi["start"])
        end = float(wi["end"])
        if current_start is None:
            current_start = start

        if last_end is not None and (start - last_end) >= gap_break_sec and current_words:
            segments.append(
                {
                    "start_sec": round(float(current_start), 2),
                    "end_sec": round(float(last_end), 2),
                    "text": " ".join([w["word"] for w in current_words]).strip(),
                    "words": current_words
                }
            )
            current_words = []
            current_start = start

        current_words.append(wi)
        last_end = end

        if (
            word.endswith(end_punct)
            or len(current_words) >= max_words
        ):
            segments.append(
                {
                    "start_sec": round(float(current_start), 2),
                    "end_sec": round(float(end), 2),
                    "text": " ".join([w["word"] for w in current_words]).strip(),
                    "words": current_words
                }
            )
            current_words = []
            current_start = None
            last_end = None

    if current_words and current_start is not None and last_end is not None:
        segments.append(
            {
                "start_sec": round(float(current_start), 2),
                "end_sec": round(float(last_end), 2),
                "text": " ".join([w["word"] for w in current_words]).strip(),
                "words": current_words
            }
        )

    return segments

def transcribe(audio_path: str, model_size: str = "base", console=None) -> list:
    dg_api_key = os.getenv("DEEPGRAM_API_KEY")
    if not dg_api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set")

    if console:
        console.print("\n[bold blue]┌─ Step 2/2 — Transcribe Audio (Deepgram Nova-3)[/bold blue]")
        console.print("[yellow]   → Transcribing with Deepgram (word timestamps enabled)...[/yellow]")

    deepgram = DeepgramClient(api_key=dg_api_key)

    def _chunk_file(path: str, chunk_size: int = 1024 * 1024):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    # Deepgram SDK v6: prerecorded transcription (bytes in, structured response out)
    response = deepgram.listen.v1.media.transcribe_file(
        request=_chunk_file(audio_path),
        model="nova-3",
        smart_format=True,
        punctuate=True,
        utterances=True,
        request_options={
            "timeout": httpx.Timeout(600.0, connect=30.0, read=600.0, write=600.0, pool=30.0)
        },
    )
    words = _extract_words(response)
    segments = _reconstruct_segments(words)

    if console:
        console.print(f"[bold green]   ✓ Deepgram transcription complete ({len(segments)} segments)[/bold green]")
    return segments
