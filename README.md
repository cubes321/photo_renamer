# photo_renamer

Give your photos meaningful names and searchable descriptions using an AI vision model.

`photo_renamer` looks at each JPG in a folder, asks a vision-capable language model what's
in it, and then:

- **renames** it, by copying it to an output folder with a descriptive name such as
  `2024-05-01 Golden retriever running on a beach at sunset.jpg`, and/or
- **tags** it, by writing a one- or two-sentence description into the photo's EXIF metadata.
  Windows Explorer, Lightroom, digiKam and most photo managers can show and search this.

It works with any **OpenAI-compatible API**. That includes OpenAI, OpenRouter, and Google
Gemini, and also models running on your own machine with LM Studio, Ollama or vLLM, so
your photos never have to leave your computer.

```
$ python photo_renamer.py holiday renamed --mode b
Found 3 JPG files
[1/3] C:\photos\holiday\IMG_4021.JPG
  New name:    2024-05-01 Golden retriever running on a beach at sunset.jpg
  Description: A golden retriever runs along wet sand at sunset, with waves breaking behind it.
Apply? (y/n): y
Copied C:\photos\holiday\IMG_4021.JPG to: C:\photos\renamed\2024-05-01 Golden retriever running on a beach at sunset.jpg
Setting exif data for C:\photos\renamed\2024-05-01 Golden retriever running on a beach at sunset.jpg
...
Done. 3 file(s) changed, 0 failed.
```

## Features

- **Safe by default.** Originals are never moved or renamed; renaming makes a copy. Existing
  files are never overwritten. Every suggestion is shown for approval unless you say otherwise.
- **Undo.** Every change is logged, and `--undo` reverses the last run.
- **Dry run.** See exactly what would happen before anything changes.
- **Picks up where it left off.** Re-running skips photos that are already done.
- **Copes with failures.** Rate limits and network errors are retried. A photo that still
  fails is skipped, and the run carries on.
- **Date-prefixed names.** Names start with the date the photo was taken, so they sort in
  date order.
- **Review in bulk.** `--batch` collects every suggestion first, then lets you choose which
  to apply. `--yes` runs unattended.
- **No quality loss.** Metadata is written without re-compressing the image, and existing
  EXIF data (camera, date, GPS and so on) is kept.

## Requirements

- Python 3.8 or newer
- Access to a **vision-capable** model through an OpenAI-compatible API (see
  [Choosing a model provider](#choosing-a-model-provider))

## Quick start

```
git clone https://github.com/cubes321/photo_renamer.git
cd photo_renamer
pip install -r requirements.txt
```

Set your API key (OpenAI shown here; see below for other providers):

```
set OPENAI_API_KEY=sk-...                # Windows (cmd)
$env:OPENAI_API_KEY = "sk-..."           # Windows (PowerShell)
export OPENAI_API_KEY=sk-...             # Linux / macOS
```

Try it on a folder without changing anything:

```
python photo_renamer.py "C:\photos\holiday" "C:\photos\renamed" --mode b --dry-run
```

If you like the suggestions, run it for real:

```
python photo_renamer.py "C:\photos\holiday" "C:\photos\renamed" --mode b
```

The output folder must already exist.

## Choosing a model provider

Three settings control which service is used. Each can be an environment variable or a
command-line option:

| Environment variable | Option | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | – | contents of `e:/ai/genai_api_key.txt`, if that file exists | Local servers don't need one |
| `OPENAI_BASE_URL` | `--base-url` | OpenAI | Address of any OpenAI-compatible server |
| `PHOTO_RENAMER_MODEL` | `--model` | `gpt-4o-mini` | Must accept images |

Examples (shown with `set` for Windows cmd; use `export` on Linux/macOS):

**OpenAI**
```
set OPENAI_API_KEY=sk-...
set PHOTO_RENAMER_MODEL=gpt-4o-mini
```

**Google Gemini** (through Gemini's OpenAI-compatible endpoint)
```
set OPENAI_API_KEY=<your Gemini API key>
set OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
set PHOTO_RENAMER_MODEL=gemini-2.0-flash
```

**OpenRouter**
```
set OPENAI_API_KEY=sk-or-...
set OPENAI_BASE_URL=https://openrouter.ai/api/v1
set PHOTO_RENAMER_MODEL=openai/gpt-4o-mini
```

**LM Studio** (local; load a vision model such as Qwen2.5-VL, and start the server)
```
set OPENAI_BASE_URL=http://localhost:1234/v1
set PHOTO_RENAMER_MODEL=qwen2.5-vl-7b-instruct
```

**Ollama** (local; e.g. `ollama pull llava` first)
```
set OPENAI_BASE_URL=http://localhost:11434/v1
set PHOTO_RENAMER_MODEL=llava
```

Model names change often. Use whatever vision model your provider currently offers.

## Usage

```
python photo_renamer.py <input_folder> [output_folder] [options]
python photo_renamer.py --undo <folder>
```

The input folder is searched recursively for `.jpg` and `.jpeg` files (any capitalisation).

### Modes

| Mode | What it does | Needs output folder |
|---|---|---|
| `r` rename | Copies each photo into the output folder under its new name | yes |
| `a` amend EXIF | Writes the description into the **original** photos' EXIF | no |
| `b` both | Copies under the new name, and writes the description into the **copy's** EXIF | yes |

If you don't give `--mode`, you're asked. If you don't give an output folder, the mode is
`a`.

### Options

| Option | Meaning |
|---|---|
| `-m`, `--mode r\|a\|b` | Choose the mode (see above). |
| `-y`, `--yes` | Apply every suggestion without asking. |
| `--batch` | Get all suggestions first, then choose which to apply in one go. |
| `--dry-run` | Show suggestions without copying or changing anything. |
| `--no-date` | Don't start new filenames with the date the photo was taken. |
| `--force` | Also process photos that were already done. |
| `--undo` | Undo the last run logged in the given folder. |
| `--retries N` | How many times to retry a failed API call (default 3). |
| `--timeout SECONDS` | How long to wait for each API call (default 120). |
| `--model NAME` | Model to use (overrides `PHOTO_RENAMER_MODEL`). |
| `--base-url URL` | API address (overrides `OPENAI_BASE_URL`). |

### Batch selection

With `--batch`, every suggestion is numbered. At the end you're asked which to apply:

| You type | Applies |
|---|---|
| Enter or `all` | everything |
| `none` | nothing |
| `1 3 5-7` | just those |
| `-2 4` | everything except 2 and 4 |

### Examples

```
# Preview without changing anything
python photo_renamer.py photos renamed --mode b --dry-run

# Approve each photo one at a time
python photo_renamer.py photos renamed --mode b

# Look through all the suggestions, then pick
python photo_renamer.py photos renamed --mode b --batch

# Process a whole library unattended
python photo_renamer.py photos renamed --mode b --yes

# Only add descriptions to the originals, keeping their filenames
python photo_renamer.py photos --yes

# Use a local model in LM Studio for this run
python photo_renamer.py photos renamed -m r --base-url http://localhost:1234/v1 --model qwen2.5-vl-7b-instruct

# Undo the last run
python photo_renamer.py --undo renamed
```

## How it works

1. Each photo is shrunk to at most 1024 pixels on its longest side and sent to the model.
   The original file is not changed.
2. The model replies with a short name (up to 10 words) and a longer description.
3. **Filename:** punctuation and characters Windows doesn't allow are removed. The date
   taken, from the EXIF `DateTimeOriginal` tag, is added to the front if the photo has one.
   If the name is already taken, ` (2)`, ` (3)` and so on are added.
4. **EXIF:** the description is written to the `ImageDescription` and `UserComment` tags.
   Other EXIF data is kept, and the image itself isn't re-compressed.
5. Each change is appended to `photo_renamer_log.csv`.

## Re-runs, the log and undo

Every change is recorded in **`photo_renamer_log.csv`**:

- in the **output folder** when renaming (modes `r` and `b`)
- in the **input folder** when only setting EXIF (mode `a`)

The log records each file's original location, its new location, and (for EXIF edits) the
description it had before. Keep this file if you want to be able to undo.

**Skipping finished photos.** When you run the script again, it skips:

- in modes `r`/`b`: photos the log says were already copied, as long as the copy still exists
- in mode `a`: photos that already have a description. Placeholder text some cameras write,
  such as `OLYMPUS DIGITAL CAMERA`, doesn't count.

Use `--force` to process them again.

**Undo.** `python photo_renamer.py --undo <folder>` reverses the most recent run logged in
that folder:

- copies it made are **deleted** (originals are untouched)
- EXIF descriptions it wrote to originals are put back to what they were before

Run it again to undo the run before that. Once everything is undone, the log file is
removed.

## Errors

- Rate limits, timeouts, dropped connections and server errors are retried automatically,
  waiting a little longer each time.
- A photo that still fails is skipped, and the rest carry on. Failures are listed at the
  end of the run, and the exit code is 1.
- A wrong API key, a model that doesn't exist, or 5 failures in a row stop the run straight
  away, because the remaining photos would fail too.
- Press Ctrl+C to stop. Photos already processed stay done, and re-running continues from
  where you stopped. In `--batch` mode, nothing collected so far is applied.

## Privacy and cost

- With a hosted provider (OpenAI, Gemini, OpenRouter), a reduced-size copy of each photo is
  uploaded to that provider. Check their data policy if your photos are private.
- With a local server (LM Studio, Ollama, vLLM), nothing leaves your machine.
- There is one API request per photo. `--dry-run` makes the same requests, so it costs the
  same as a real run.

## Troubleshooting

| Problem | Likely cause |
|---|---|
| `Error code: 401` | Missing or wrong API key. Check `OPENAI_API_KEY`. |
| `Error code: 404` | Wrong model name or wrong `OPENAI_BASE_URL`. |
| `Error code: 400` on every photo | The model doesn't accept images. Choose a vision model. |
| `Connection error` with a local server | The server isn't running, or the port in `OPENAI_BASE_URL` is wrong. |
| Description is the same as the filename | Some small models ignore the requested two-line format. Try a larger model. |
| "Skipping N already done" when you expected them to run | They were processed before. Use `--force`. |
| Output folder error | It must already exist, and it can't be the same folder as the input. |

On Windows, put paths that contain spaces in quotes.

## Limitations

- JPG/JPEG only; PNG, HEIC and other formats are ignored.
- Renamed copies are always saved with a `.jpg` extension.
- Undo deletes the copies a run made, including any edits you made to them since.
- In mode `b`, the description is written to the copies only, not to the originals.
