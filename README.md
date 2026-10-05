# photo_renamer

Uses a vision-capable LLM (any OpenAI-compatible API) to suggest a short
descriptive name for each JPG in a folder, then copies it to a new name and/or
writes the description into the EXIF `ImageDescription` and `UserComment` tags.

## Install

```
pip install -r requirements.txt
```

## Configure

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | contents of `e:/ai/genai_api_key.txt` | Not needed for local servers |
| `OPENAI_BASE_URL` | OpenAI | Any OpenAI-compatible endpoint |
| `PHOTO_RENAMER_MODEL` | `gpt-4o-mini` | Must support image input |

Examples:

```
# OpenAI
set OPENAI_API_KEY=sk-...

# LM Studio
set OPENAI_BASE_URL=http://localhost:1234/v1
set PHOTO_RENAMER_MODEL=qwen2.5-vl-7b-instruct

# Ollama
set OPENAI_BASE_URL=http://localhost:11434/v1
set PHOTO_RENAMER_MODEL=llava

# Gemini via its OpenAI-compatible endpoint
set OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
set PHOTO_RENAMER_MODEL=gemini-2.0-flash
```

(Use `export` instead of `set` on Linux/macOS.)

## Usage

```
python photo_renamer.py <input_folder> [output_folder]
```

With an output folder you are asked whether to rename (copy to the new name),
amend EXIF, or both. Without one, only EXIF data is set on the originals.
Each suggestion is confirmed before anything is written.
