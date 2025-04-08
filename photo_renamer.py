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
    print("Usage: python photo_renamer.py <folder_path> <output_folder>.  Omitting output folder will only allow exif data to be set.")
    if len(sys.argv) < 2:
        print("Please provide a folder path to search for jpg files.")
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
#    print(output)
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
# check that the folder path is not the same as the output folder
if len(sys.argv) > 2:
    if sys.argv[1] == sys.argv[2]:
        print("Input and output folders are the same.  Please change one of them.")
        sys.exit(1)
# check that the folder path exists and is a directory
if os.path.exists(folder_path) == False:
    print(f"Folder {folder_path} does not exist.")
    sys.exit(1)
# check that the folder path is a directory
if len(sys.argv) > 2:
    if os.path.exists(sys.argv[2]) == False:
        print(f"Output folder {sys.argv[2]} does not exist.")
        sys.exit(1)

if len(sys.argv) ==2:
    do_what = "a"
    print("You have not provided an output folder.  Only exif data will be set.")
else:
    do_what = input("Do you want to rename files, amend exif data, or both? (r/a/b): ")
    if do_what.lower() not in ['r', 'a', 'b']:
        print("Invalid option. Please enter 'r', 'a', or 'b'.")
        sys.exit(1)

if do_what.lower() == 'r':  
    do_exif = 'n'
    do_rename = 'y'
if do_what.lower() == 'a':
    do_exif = 'y'
    do_rename = 'n'
if do_what.lower() == 'b':
    do_exif = 'y'
    do_rename = 'y'
jpgfiles = get_jpg_files(folder_path)
print("Found the following JPG files:")
for jpg_file in jpgfiles:
    output = get_ai_filename(jpg_file)
    if do_rename.lower() == 'y':
        print(f"Suggested filename: {output}")
        confirm = input(f"Do you want to rename {jpg_file} as above? (y/n): ")
        if confirm.lower() != 'y':
            print("File renaming cancelled.")
            continue
        try:
            newfilename = sys.argv[2] + "\\" + output.replace(","," ").replace("."," ")
            print(f"Renamed {jpg_file} to: {newfilename}.jpg")
            shutil.copy(jpg_file, newfilename + ".jpg")
            if do_exif.lower () == 'y':
                if do_rename.lower() == 'y':
                    print(f"Setting exif data for {newfilename}.jpg")
                    set_exif_data(f"{newfilename}.jpg", output, output)
        except Exception as e:
            print(f"Error renaming file: {e}")
            sys.exit(1)
        except errors.APIError as e:
            print(f"Error: {e.code} - {e.message}")
            sys.exit(1)
    if do_rename.lower() == 'n':
        print(f"Suggested exif data: {output}")
        confirm = input(f"Do you want to set exif data for {jpg_file} as above? (y/n): ")
        if confirm.lower() != 'y': 
            print("Exif data setting cancelled.")
            continue
        print(f"Setting exif data for {jpg_file}")
        set_exif_data(jpg_file, output, output)