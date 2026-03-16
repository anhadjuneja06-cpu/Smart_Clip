# OZListings YouTube Clip Agent 🎥

An AI-powered content strategist that extracts high-value short-form clips (30-60s) from long-form YouTube videos, optimized for YouTube Shorts, Instagram Reels, and TikTok.

## Features
- **Smart Hook Selection**: Uses Gemini 1.5 Flash to identify "scroll-stopping" moments based on "Think School" style storytelling.
- **Sentence-Aligned Clips**: Automatically groups transcription segments into complete thoughts to ensure clips don't start or end mid-sentence.
- **Local Transcription**: Uses OpenAI Whisper (locally) for high-accuracy timestamped transcripts.
- **Automated Extraction**: FFmpeg-powered precise clip cutting with smooth professional transitions.

## Prerequisites
- **Python 3.10+**
- **FFmpeg**: Must be installed and available in your PATH.
- **Gemini API Key**: Get one from [Google AI Studio](https://aistudio.google.com/).

## Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd oz_clip_agent
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Create a `.env` file in the root directory and add your API key:
   ```env
   GEMINI_API_KEY=your_actual_key_here
   ```

## Usage

Run the agent with a YouTube URL:
```bash
python agent.py --url "https://www.youtube.com/watch?v=your_video_id"
```

### Options:
- `--model`: Choose Whisper model size (`tiny`, `base`, `small`, `medium`, `large`). Default is `base`. Larger models are more accurate but slower.

## Technical Workflow
1. **Ingest**: Downloads audio and metadata using `yt-dlp`.
2. **Transcribe**: Uses Whisper with word-level timestamps to reconstruct the transcript into sentence-aligned segments.
3. **Score**: Gemini analyzes the transcript against a 5-point social media rubric.
4. **Extract**: FFmpeg cuts the selected clips with precise start/end points and professional fade-outs.
5. **Manifest**: Generates a `clips_summary.md` and `clips_manifest.json` for easy review and posting.
