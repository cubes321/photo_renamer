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
from openai import OpenAI, OpenAIError

API_KEY_FILE = 'e:/ai/genai_api_key.txt'
DEFAULT_MODEL = "gpt-4o-mini"
MAX_IMAGE_SIZE = 1024  # longest side in pixels sent to the model

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
    return sorted(f for f in files if f.lower().endswith(('.jpg', '.jpeg')))


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
    return parse_response(response.choices[0].message.content)


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
    return path


def set_exif_data(image_path, description, user_comment):
    # piexif.load on the path returns empty sections if the image has no EXIF
    exif_dict = piexif.load(image_path)

    # Set the description and user comment in the EXIF data
    if description:
        exif_dict['0th'][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
    if user_comment:
        exif_dict['Exif'][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(user_comment, encoding="unicode")

    # Thumbnail data can make dump fail and isn't needed
    exif_dict.pop('thumbnail', None)
    exif_dict.pop('1st', None)

    # Write the EXIF data in place without re-encoding the image
    piexif.insert(piexif.dump(exif_dict), image_path)


def build_new_name(name, image_path, date_prefix):
    name = clean_filename(name)
    if date_prefix:
        date = get_photo_date(image_path)
        if date:
            name = f"{date} {name}"
    return name


def apply(suggestion, args):
    # Copy/rename and/or write EXIF for one file
    jpg_file, name, description = suggestion
    target = jpg_file
    if args.mode in ('r', 'b'):
        target = unique_path(args.output, build_new_name(name, jpg_file, args.date_prefix))
        shutil.copy2(jpg_file, target)
        print(f"Copied {jpg_file} to: {target}")
    if args.mode in ('a', 'b'):
        print(f"Setting exif data for {target}")
        set_exif_data(target, description, description)


def show(suggestion, args):
    jpg_file, name, description = suggestion
    if args.mode in ('r', 'b'):
        print(f"  New name:    {build_new_name(name, jpg_file, args.date_prefix)}.jpg")
    if args.mode in ('a', 'b'):
        print(f"  Description: {description}")


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
    parser.add_argument("input", help="folder to search (recursively) for JPG files")
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
    parser.add_argument("--model", default=os.environ.get("PHOTO_RENAMER_MODEL", DEFAULT_MODEL),
                        help=f"model name (default: $PHOTO_RENAMER_MODEL or {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"),
                        help="API base URL (default: $OPENAI_BASE_URL or OpenAI)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        parser.error(f"Folder {args.input} does not exist.")
    if args.output:
        if not os.path.isdir(args.output):
            parser.error(f"Output folder {args.output} does not exist.")
        if os.path.abspath(args.input) == os.path.abspath(args.output):
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
    client = OpenAI(api_key=get_api_key(), base_url=args.base_url)

    jpgfiles = get_jpg_files(args.input)
    print(f"Found {len(jpgfiles)} JPG files")

    suggestions = []
    for i, jpg_file in enumerate(jpgfiles, 1):
        try:
            name, description = get_ai_description(client, args.model, jpg_file)
        except OpenAIError as e:
            print(f"API error for {jpg_file}: {e}")
            sys.exit(1)
        suggestion = (jpg_file, name, description)
        print(f"[{i}/{len(jpgfiles)}] {jpg_file}")
        show(suggestion, args)

        if args.batch:
            suggestions.append(suggestion)
            continue
        if not args.yes:
            if input("Apply? (y/n): ").lower() != 'y':
                print("Skipped.")
                continue
        try:
            apply(suggestion, args)
        except Exception as e:
            print(f"Error processing {jpg_file}: {e}")
            sys.exit(1)

    if args.batch and suggestions:
        if args.yes:
            selected = set(range(len(suggestions)))
        else:
            answer = input("\nApply which? (all / none / numbers e.g. 1 3 5-7 / -2 to apply all except 2): ")
            try:
                selected = parse_selection(answer, len(suggestions))
            except ValueError:
                print("Couldn't understand that selection.  Nothing was changed.")
                sys.exit(1)
        for i in sorted(selected):
            try:
                apply(suggestions[i], args)
            except Exception as e:
                print(f"Error processing {suggestions[i][0]}: {e}")
        print(f"Applied {len(selected)} of {len(suggestions)} suggestions.")


if __name__ == "__main__":
    main()
