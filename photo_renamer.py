# 1st argument is the folder path to search for jpg files
# 2nd argument is path for renamed files
from google import genai
from google.genai import types, errors
import sys
import os
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import glob
import shutil
import PIL.Image
import piexif
# pip install piexif
import os

if len(sys.argv) < 3:
    print("Usage: python photo_renamer.py <folder_path> <output_folder>")
    sys.exit(1)

sys_instruct_art= "Limit your output to 10 words.  No commas, no periods, no quotes, no double quotes or other punctuation"

with open('e:/ai/genai_api_key.txt') as file:
    api_key = file.read().strip()
client = genai.Client(api_key=api_key)

def get_jpg_files(folder_path):
    # Get all .jpg files in the folder and subfolders
    return glob.glob(os.path.join(folder_path, '**', '*.jpg'), recursive=True) 

def remove_lfcr(text):
    return text.replace("\n"," ").replace("\r"," ")

def get_ai_filename(image_path):
    image = PIL.Image.open(image_path)
#code goes here
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=sys_instruct_art),
        contents=["Make your response good for a descriptive filename",image]
        )
    para_text = response.text.splitlines()
    output = remove_lfcr(para_text[0])
    print(output)
    return output

def set_exif_data(image_path, description, user_comment):
    # Open the image file
    img = PIL.Image.open(image_path)
    exif_dict = piexif.load(img.info['exif'])

    # Set the description and user comment in the EXIF data
    if description:
        
        exif_dict['0th'][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
    if user_comment:
        exif_dict['Exif'][piexif.ExifIFD.UserComment] = user_comment.encode('utf-8')

    # Convert the EXIF data back to bytes
    exif_bytes = piexif.dump(exif_dict)

    # Save the image with the new EXIF data
    img.save(image_path, exif=exif_bytes)

folder_path = sys.argv[1]
if os.path.exists(folder_path) == False:
    print(f"Folder {folder_path} does not exist.")
    sys.exit(1)
if os.path.exists(sys.argv[2]) == False:
    print(f"Output folder {sys.argv[2]} does not exist.")
    sys.exit(1)

jpgfiles = get_jpg_files(folder_path)
do_exif = input("Do you want to amend exif description and user comment? (y/n): ")
print("Found the following JPG files:")
for jpg_file in jpgfiles:
    print(jpg_file)
    output = get_ai_filename(jpg_file)


    confirm = input(f"Do you want to rename {jpg_file} as above? (y/n): ")
    if confirm.lower() != 'y':
        print("File renaming cancelled.")
        continue
    try:
        newfilename = sys.argv[2] + "\\" + output.replace(","," ").replace("."," ")
        print(f"Renamed {jpg_file} to: {newfilename}.jpg")
        shutil.copy(jpg_file, newfilename + ".jpg")
        if do_exif.lower () == 'y':
            set_exif_data(f"{newfilename}.jpg", output, output)

    except Exception as e:
        print(f"Error renaming file: {e}")
        sys.exit(1)
    except errors.APIError as e:
        print(f"Error: {e.code} - {e.message}")
        sys.exit(1)
