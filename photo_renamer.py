# Uses a vision-capable LLM to name JPG files and/or write a description into their EXIF.
#
# Works with any OpenAI-compatible chat completions API (OpenAI, OpenRouter, LM Studio,
# Ollama, vLLM, ...). Configure with command line options or environment variables:
#   OPENAI_BASE_URL      e.g. http://localhost:1234/v1 (defaults to OpenAI)
#   OPENAI_API_KEY       falls back to the contents of API_KEY_FILE
#   PHOTO_RENAMER_MODEL  vision-capable model name (default gpt-4o-mini)
# pip install -r requirements.txt
# Run "python photo_renamer.py --help" for options.
import argparse
import base64
import csv
import glob
import io
import os
import re
import shutil
import sys
from datetime import datetime

import PIL.Image
import piexif
import piexif.helper
from openai import (OpenAI, OpenAIError, AuthenticationError, PermissionDeniedError,
                    NotFoundError)

API_KEY_FILE = 'e:/ai/genai_api_key.txt'
DEFAULT_MODEL = "gpt-4o-mini"
MAX_IMAGE_SIZE = 1024  # longest side in pixels sent to the model
LOG_NAME = "photo_renamer_log.csv"
LOG_FIELDS = ["run", "action", "source", "target", "old_description", "old_comment", "new_description"]
MAX_CONSECUTIVE_FAILURES = 5
# Placeholder descriptions some cameras write, which shouldn't count as "already described"
CAMERA_DEFAULT_DESCRIPTIONS = {"", "OLYMPUS DIGITAL CAMERA", "SONY DSC", "DIGITAL CAMERA",
                               "DCIM", "DEFAULT", "EXIF_JPEG_PICTURE"}

# Errors that will fail for every photo, so there's no point carrying on
FATAL_API_ERRORS = (AuthenticationError, PermissionDeniedError, NotFoundError)

sys_instruct_art = (
    "You describe photos. Reply with exactly two lines and nothing else.\n"
    "Line 1: a descriptive filename of at most 10 words. No commas, no periods, "
    "no quotes, no double quotes or other punctuation.\n"
    "Line 2: one or two sentences describing the photo in more detail."
)


def get_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE) as file:
            return file.read().strip()
    # Local servers (LM Studio, Ollama) don't check the key but the client requires one
    return "not-needed"


def get_jpg_files(folder_path):
    # Get all .jpg/.jpeg files (any case) in the folder and subfolders
    files = glob.glob(os.path.join(folder_path, '**', '*'), recursive=True)
    return sorted(os.path.abspath(f) for f in files if f.lower().endswith(('.jpg', '.jpeg')))


def image_to_data_url(image_path):
    # Downscale and re-encode so we don't upload full-size camera images
    with PIL.Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def parse_response(text):
    # Expect "filename\ndescription"; tolerate labels like "Line 1:" or "Filename:"
    lines = []
    for line in (text or "").splitlines():
        line = re.sub(r'^\s*(line\s*\d|filename|description)\s*:\s*', '', line, flags=re.I).strip()
        if line:
            lines.append(line)
    if not lines:
        return "", ""
    name = lines[0]
    description = " ".join(lines[1:]) or name
    return name, description


def get_ai_description(client, model, image_path):
    response = client.chat.completions.create(
        model=model,
        max_tokens=150,
        messages=[
            {"role": "system", "content": sys_instruct_art},
            {"role": "user", "content": [
                {"type": "text", "text": "Describe this photo."},
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
            ]},
        ],
    )
    name, description = parse_response(response.choices[0].message.content)
    if not name:
        raise ValueError("model returned an empty response")
    return name, description


def get_photo_date(image_path):
    # Date the photo was taken, from EXIF, as YYYY-MM-DD (None if unavailable)
    try:
        exif_dict = piexif.load(image_path)
    except Exception:
        return None
    raw = (exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
           or exif_dict['0th'].get(piexif.ImageIFD.DateTime))
    if not raw:
        return None
    try:
        return datetime.strptime(raw.decode('ascii', 'ignore').strip(), "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        return None


def get_exif_text(image_path):
    # Current (ImageDescription, raw UserComment bytes); either may be None
    try:
        exif_dict = piexif.load(image_path)
    except Exception:
        return None, None
    description = exif_dict['0th'].get(piexif.ImageIFD.ImageDescription)
    if description is not None:
        description = description.decode('utf-8', 'replace')
    return description, exif_dict['Exif'].get(piexif.ExifIFD.UserComment)


def has_description(image_path):
    description, _ = get_exif_text(image_path)
    if description is None:
        return False
    description = description.strip(" \x00")
    return description.upper() not in CAMERA_DEFAULT_DESCRIPTIONS


def clean_filename(text):
    # Drop punctuation and characters that are illegal in Windows filenames
    text = re.sub(r'[^\w\s-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text or "untitled"


def unique_path(folder, name, ext=".jpg"):
    # Avoid overwriting an existing file: "name.jpg", "name (2).jpg", ...
    path = os.path.join(folder, name + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{name} ({n}){ext}")
        n += 1
    return os.path.abspath(path)


def write_exif(image_path, description, comment_bytes):
    # Set (or remove, when None) ImageDescription and the raw UserComment, in place.
    # piexif.load on the path returns empty sections if the image has no EXIF.
    exif_dict = piexif.load(image_path)
    for ifd, tag, value in (('0th', piexif.ImageIFD.ImageDescription,
                             description.encode('utf-8') if description is not None else None),
                            ('Exif', piexif.ExifIFD.UserComment, comment_bytes)):
        if value is None:
            exif_dict[ifd].pop(tag, None)
        else:
            exif_dict[ifd][tag] = value

    # Thumbnail data can make dump fail and isn't needed
    exif_dict.pop('thumbnail', None)
    exif_dict.pop('1st', None)

    # Write the EXIF data without re-encoding the image
    piexif.insert(piexif.dump(exif_dict), image_path)


def set_exif_data(image_path, description, user_comment):
    write_exif(image_path, description,
               piexif.helper.UserComment.dump(user_comment, encoding="unicode") if user_comment else None)


def build_new_name(name, image_path, date_prefix):
    name = clean_filename(name)
    if date_prefix:
        date = get_photo_date(image_path)
        if date:
            name = f"{date} {name}"
    return name


# ---- Log of changes, used to skip finished photos and to undo a run ----

def log_folder(args):
    # Renamed copies are logged next to the copies; in-place EXIF edits next to the originals
    return args.output if args.mode in ('r', 'b') else args.input


def read_log(folder):
    path = os.path.join(folder, LOG_NAME)
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as file:
        return list(csv.DictReader(file))


def write_log(folder, rows):
    path = os.path.join(folder, LOG_NAME)
    if not rows:
        os.remove(path)
        return
    with open(path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def append_log(folder, row):
    path = os.path.join(folder, LOG_NAME)
    is_new = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def already_done(jpg_file, args, copied_sources):
    if args.mode in ('r', 'b'):
        return jpg_file in copied_sources
    return has_description(jpg_file)


def apply(suggestion, args, run_id):
    # Copy/rename and/or write EXIF for one file, and log what was done
    jpg_file, name, description = suggestion
    if args.mode in ('r', 'b'):
        target = unique_path(args.output, build_new_name(name, jpg_file, args.date_prefix))
        shutil.copy2(jpg_file, target)
        print(f"Copied {jpg_file} to: {target}")
        if args.mode == 'b':
            print(f"Setting exif data for {target}")
            set_exif_data(target, description, description)
        append_log(args.output, {"run": run_id, "action": "copy", "source": jpg_file,
                                 "target": target, "new_description": description})
    else:
        old_description, old_comment = get_exif_text(jpg_file)
        print(f"Setting exif data for {jpg_file}")
        set_exif_data(jpg_file, description, description)
        append_log(args.input, {
            "run": run_id, "action": "exif", "source": jpg_file, "target": jpg_file,
            # Empty field = tag was absent; otherwise prefixed so an empty tag survives the CSV
            "old_description": "" if old_description is None else "=" + old_description,
            "old_comment": "" if old_comment is None else base64.b64encode(old_comment).decode('ascii'),
            "new_description": description})


def show(suggestion, args):
    jpg_file, name, description = suggestion
    if args.mode in ('r', 'b'):
        print(f"  New name:    {build_new_name(name, jpg_file, args.date_prefix)}.jpg")
    if args.mode in ('a', 'b'):
        print(f"  Description: {description}")


def undo(folder, yes):
    rows = read_log(folder)
    if not rows:
        print(f"No {LOG_NAME} found in {folder}, nothing to undo.")
        return 1
    last_run = rows[-1]["run"]
    to_undo = [r for r in rows if r["run"] == last_run]
    copies = sum(r["action"] == "copy" for r in to_undo)
    edits = len(to_undo) - copies
    print(f"Last run ({last_run}): {copies} copied file(s) will be deleted, "
          f"{edits} file(s) will have their EXIF description restored.")
    if not yes and input("Undo it? (y/n): ").lower() != 'y':
        print("Nothing was changed.")
        return 0

    failed = []
    for row in reversed(to_undo):
        try:
            if row["action"] == "copy":
                if os.path.exists(row["target"]):
                    os.remove(row["target"])
                    print(f"Deleted {row['target']}")
                else:
                    print(f"Already gone: {row['target']}")
            else:
                old_description = row["old_description"][1:] if row["old_description"] else None
                old_comment = base64.b64decode(row["old_comment"]) if row["old_comment"] else None
                write_exif(row["target"], old_description, old_comment)
                print(f"Restored exif data for {row['target']}")
        except Exception as e:
            print(f"Could not undo {row['target']}: {e}")
            failed.append(row)

    # Keep only rows that are still in effect (earlier runs, and anything that failed to undo)
    write_log(folder, [r for r in rows if r["run"] != last_run] + failed)
    print(f"Undid {len(to_undo) - len(failed)} of {len(to_undo)} change(s).")
    return 1 if failed else 0


def parse_selection(text, count):
    # "all"/"" -> everything, "none" -> nothing, "1 3 5-7" -> those, prefix with "-" to exclude
    text = text.strip().lower()
    if text in ("", "a", "all", "y", "yes"):
        return set(range(count))
    if text in ("n", "no", "none"):
        return set()
    exclude = text.startswith("-")
    chosen = set()
    for part in re.split(r'[\s,]+', text.lstrip("-")):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            chosen.update(range(int(start) - 1, int(end)))
        else:
            chosen.add(int(part) - 1)
    chosen &= set(range(count))
    return set(range(count)) - chosen if exclude else chosen


def parse_args():
    parser = argparse.ArgumentParser(
        description="Name JPG files and/or set their EXIF description using a vision LLM.")
    parser.add_argument("input", help="folder to search (recursively) for JPG files "
                                      "(with --undo: the folder holding " + LOG_NAME + ")")
    parser.add_argument("output", nargs="?",
                        help="folder for renamed copies; omit to only set EXIF data on the originals")
    parser.add_argument("-m", "--mode", choices=["r", "a", "b"],
                        help="r = rename (copy), a = amend EXIF, b = both. Asked interactively if omitted")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="apply every suggestion without asking")
    parser.add_argument("--batch", action="store_true",
                        help="get all suggestions first, then choose which to apply in one go")
    parser.add_argument("--no-date", dest="date_prefix", action="store_false",
                        help="don't prefix new filenames with the EXIF date taken (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true",
                        help="also process photos that were already done (already copied, "
                             "or already have an EXIF description)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show suggestions but don't change or copy anything")
    parser.add_argument("--undo", action="store_true",
                        help="undo the last run recorded in the given folder's " + LOG_NAME)
    parser.add_argument("--retries", type=int, default=3,
                        help="times to retry a failed API call (default 3)")
    parser.add_argument("--timeout", type=float, default=120,
                        help="seconds to wait for each API call (default 120)")
    parser.add_argument("--model", default=os.environ.get("PHOTO_RENAMER_MODEL", DEFAULT_MODEL),
                        help=f"model name (default: $PHOTO_RENAMER_MODEL or {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"),
                        help="API base URL (default: $OPENAI_BASE_URL or OpenAI)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        parser.error(f"Folder {args.input} does not exist.")
    args.input = os.path.abspath(args.input)
    if args.undo:
        if args.output:
            parser.error("--undo takes a single folder: the one holding " + LOG_NAME)
        return args
    if args.output:
        if not os.path.isdir(args.output):
            parser.error(f"Output folder {args.output} does not exist.")
        args.output = os.path.abspath(args.output)
        if args.input == args.output:
            parser.error("Input and output folders are the same.  Please change one of them.")
    else:
        if args.mode in ('r', 'b'):
            parser.error("An output folder is needed to rename files.")
        if args.mode is None:
            print("You have not provided an output folder.  Only exif data will be set.")
        args.mode = 'a'

    if args.mode is None:
        args.mode = input("Do you want to rename files, amend exif data, or both? (r/a/b): ").lower()
        if args.mode not in ['r', 'a', 'b']:
            print("Invalid option. Please enter 'r', 'a', or 'b'.")
            sys.exit(1)
    return args


def main():
    args = parse_args()
    if args.undo:
        return undo(args.input, args.yes)

    # The client retries rate limits, timeouts and server errors itself, with backoff
    client = OpenAI(api_key=get_api_key(), base_url=args.base_url,
                    max_retries=args.retries, timeout=args.timeout)
    run_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    jpgfiles = get_jpg_files(args.input)
    if args.mode in ('r', 'b'):
        # Don't pick up our own output if it lives inside the input folder
        jpgfiles = [f for f in jpgfiles if not f.startswith(args.output + os.sep)]
    print(f"Found {len(jpgfiles)} JPG files")
    if args.dry_run:
        print("Dry run: nothing will be changed.")

    copied_sources = set()
    if args.mode in ('r', 'b'):
        copied_sources = {r["source"] for r in read_log(args.output)
                          if r["action"] == "copy" and os.path.exists(r["target"])}
    if not args.force:
        todo = [f for f in jpgfiles if not already_done(f, args, copied_sources)]
        if len(todo) < len(jpgfiles):
            print(f"Skipping {len(jpgfiles) - len(todo)} already done (use --force to redo them)")
        jpgfiles = todo

    suggestions = []
    failures = []
    applied = 0
    consecutive_failures = 0
    try:
        for i, jpg_file in enumerate(jpgfiles, 1):
            print(f"[{i}/{len(jpgfiles)}] {jpg_file}")
            try:
                name, description = get_ai_description(client, args.model, jpg_file)
                consecutive_failures = 0
            except FATAL_API_ERRORS as e:
                print(f"API error, stopping: {e}")
                failures.append((jpg_file, str(e)))
                break
            except (OpenAIError, ValueError, OSError) as e:
                print(f"  Failed, skipping: {e}")
                failures.append((jpg_file, str(e)))
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"{MAX_CONSECUTIVE_FAILURES} failures in a row, stopping.")
                    break
                continue
            suggestion = (jpg_file, name, description)
            show(suggestion, args)

            if args.dry_run:
                continue
            if args.batch:
                suggestions.append(suggestion)
                continue
            if not args.yes and input("Apply? (y/n): ").lower() != 'y':
                print("Skipped.")
                continue
            try:
                apply(suggestion, args, run_id)
                applied += 1
            except Exception as e:
                print(f"  Error processing {jpg_file}: {e}")
                failures.append((jpg_file, str(e)))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        suggestions = []  # don't apply a half-collected batch

    if suggestions:
        if args.yes:
            selected = set(range(len(suggestions)))
        else:
            answer = input("\nApply which? (all / none / numbers e.g. 1 3 5-7 / -2 to apply all except 2): ")
            try:
                selected = parse_selection(answer, len(suggestions))
            except ValueError:
                print("Couldn't understand that selection.  Nothing was changed.")
                selected = set()
        for i in sorted(selected):
            try:
                apply(suggestions[i], args, run_id)
                applied += 1
            except Exception as e:
                print(f"  Error processing {suggestions[i][0]}: {e}")
                failures.append((suggestions[i][0], str(e)))

    print(f"\nDone. {applied} file(s) changed, {len(failures)} failed.")
    for jpg_file, error in failures:
        print(f"  {jpg_file}: {error}")
    if applied:
        print(f"Changes logged in {os.path.join(log_folder(args), LOG_NAME)} "
              f"(undo with: python photo_renamer.py --undo \"{log_folder(args)}\")")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
