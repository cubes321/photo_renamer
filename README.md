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
python photo_renamer.py <input_folder> [output_folder] [options]
```

| Option | Meaning |
|---|---|
| `-m`, `--mode r\|a\|b` | Rename (copy to output folder), amend EXIF, or both. Asked interactively if omitted. |
| `-y`, `--yes` | Apply every suggestion without asking. |
| `--batch` | Get all suggestions first, then pick which to apply in one go. |
| `--no-date` | Don't prefix new filenames with the date taken (`2024-05-01 Dog on beach.jpg`). |
| `--dry-run` | Show suggestions without copying or changing anything. |
| `--force` | Also process photos already done (see below). |
| `--undo` | Undo the last run recorded in the folder given (see below). |
| `--retries N` | Retries for a failed API call (default 3). |
| `--timeout SECONDS` | Wait per API call (default 120). |
| `--model NAME` | Overrides `PHOTO_RENAMER_MODEL`. |
| `--base-url URL` | Overrides `OPENAI_BASE_URL`. |

Without an output folder, only EXIF data is set on the originals. Renamed files
are copies; the originals are never moved. Existing files are never overwritten
(`name (2).jpg` is used instead).

The model returns a short name (used for the filename) and a longer
description (written to EXIF `ImageDescription` and `UserComment`). The date
prefix comes from the EXIF `DateTimeOriginal` tag and is skipped when a photo
has none.

In `--batch` mode the selection prompt accepts `all` (or Enter), `none`, a list
like `1 3 5-7`, or a leading `-` to exclude (`-2 4` applies everything except
2 and 4).

## Errors, re-runs and undo

- Rate limits, timeouts and server errors are retried automatically with
  backoff. A photo that still fails is skipped, and the run carries on; failures
  are listed at the end. A bad API key or unknown model stops the run straight
  away, as does 5 failures in a row.
- Every change is recorded in `photo_renamer_log.csv`: in the output folder
  when renaming, or in the input folder when only setting EXIF.
- Re-running skips photos that are already done: ones already copied (per the
  log, if the copy still exists), or, in EXIF-only mode, ones that already have
  a description (camera placeholders like `OLYMPUS DIGITAL CAMERA` don't
  count). Use `--force` to redo them.
- `--undo <folder>` reverses the most recent run logged in that folder:
  copies it made are deleted, and EXIF descriptions it changed on originals
  are restored to what they were. Run it again to step back another run.

Examples:

```
# See what it would do first
python photo_renamer.py photos renamed --mode b --dry-run

# Review every suggestion one by one
python photo_renamer.py photos renamed

# Rename and tag a whole folder unattended
python photo_renamer.py photos renamed --mode b --yes

# Review a list of suggestions at the end
python photo_renamer.py photos renamed --mode b --batch

# Didn't like the result? Remove the copies from the last run
python photo_renamer.py --undo renamed
```
