# 1st argument is the folder path to search for jpg files
# 2nd argument is path for renamed files
#
# Uses any OpenAI-compatible chat completions API (OpenAI, OpenRouter, LM Studio,
# Ollama, vLLM, ...). Configure with environment variables:
#   OPENAI_BASE_URL      e.g. http://localhost:1234/v1 (defaults to OpenAI)
#   OPENAI_API_KEY       falls back to the contents of API_KEY_FILE
#   PHOTO_RENAMER_MODEL  vision-capable model name (default gpt-4o-mini)
# pip install -r requirements.txt
import base64
import glob
import io
import os
import re
import shutil
import sys

import PIL.Image
import piexif
import piexif.helper
from openai import OpenAI, OpenAIError

API_KEY_FILE = 'e:/ai/genai_api_key.txt'
MODEL = os.environ.get("PHOTO_RENAMER_MODEL", "gpt-4o-mini")
MAX_IMAGE_SIZE = 1024  # longest side in pixels sent to the model

sys_instruct_art = "Limit your output to 10 words.  No commas, no periods, no quotes, no double quotes or other punctuation"


def get_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE) as file:
            return file.read().strip()
    # Local servers (LM Studio, Ollama) don't check the key but the client requires one
    return "not-needed"


client = OpenAI(api_key=get_api_key(), base_url=os.environ.get("OPENAI_BASE_URL"))


def get_jpg_files(folder_path):
    # Get all .jpg/.jpeg files (any case) in the folder and subfolders
    files = glob.glob(os.path.join(folder_path, '**', '*'), recursive=True)
    return sorted(f for f in files if f.lower().endswith(('.jpg', '.jpeg')))


def remove_lfcr(text):
    return text.replace("\n", " ").replace("\r", " ")


def image_to_data_url(image_path):
    # Downscale and re-encode so we don't upload full-size camera images
    with PIL.Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def get_ai_filename(image_path):
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=40,
        messages=[
            {"role": "system", "content": sys_instruct_art},
            {"role": "user", "content": [
                {"type": "text", "text": "Make your response good for a descriptive filename"},
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
            ]},
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    para_text = text.splitlines() or [""]
    return remove_lfcr(para_text[0]).strip()


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


if len(sys.argv) < 3:
    print("Usage: python photo_renamer.py <folder_path> <output_folder>.  Omitting output folder will only allow exif data to be set.")
    if len(sys.argv) < 2:
        print("Please provide a folder path to search for jpg files.")
        sys.exit(1)

folder_path = sys.argv[1]
# check that the folder path is not the same as the output folder
if len(sys.argv) > 2:
    if os.path.abspath(sys.argv[1]) == os.path.abspath(sys.argv[2]):
        print("Input and output folders are the same.  Please change one of them.")
        sys.exit(1)
# check that the folder path exists and is a directory
if not os.path.isdir(folder_path):
    print(f"Folder {folder_path} does not exist.")
    sys.exit(1)
if len(sys.argv) > 2:
    if not os.path.isdir(sys.argv[2]):
        print(f"Output folder {sys.argv[2]} does not exist.")
        sys.exit(1)

if len(sys.argv) == 2:
    do_what = "a"
    print("You have not provided an output folder.  Only exif data will be set.")
else:
    do_what = input("Do you want to rename files, amend exif data, or both? (r/a/b): ").lower()
    if do_what not in ['r', 'a', 'b']:
        print("Invalid option. Please enter 'r', 'a', or 'b'.")
        sys.exit(1)

do_rename = do_what in ('r', 'b')
do_exif = do_what in ('a', 'b')

jpgfiles = get_jpg_files(folder_path)
print(f"Found {len(jpgfiles)} JPG files")
for jpg_file in jpgfiles:
    try:
        output = get_ai_filename(jpg_file)
    except OpenAIError as e:
        print(f"API error for {jpg_file}: {e}")
        sys.exit(1)
    if do_rename:
        print(f"Suggested filename: {output}")
        confirm = input(f"Do you want to rename {jpg_file} as above? (y/n): ")
        if confirm.lower() != 'y':
            print("File renaming cancelled.")
            continue
        try:
            newfilename = unique_path(sys.argv[2], clean_filename(output))
            shutil.copy2(jpg_file, newfilename)
            print(f"Renamed {jpg_file} to: {newfilename}")
            if do_exif:
                print(f"Setting exif data for {newfilename}")
                set_exif_data(newfilename, output, output)
        except Exception as e:
            print(f"Error renaming file: {e}")
            sys.exit(1)
    else:
        print(f"Suggested exif data: {output}")
        confirm = input(f"Do you want to set exif data for {jpg_file} as above? (y/n): ")
        if confirm.lower() != 'y':
            print("Exif data setting cancelled.")
            continue
        print(f"Setting exif data for {jpg_file}")
        set_exif_data(jpg_file, output, output)
