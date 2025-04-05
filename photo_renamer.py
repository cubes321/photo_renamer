import pathlib
from google import genai
from google.genai import types, errors
import sys
import os
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import glob
import time
import PIL.Image

sys_instruct_art= "Limit your output to 10 words."

with open('e:/ai/genai_api_key.txt') as file:
    api_key = file.read().strip()
client = genai.Client(api_key=api_key)

def get_jpg_files(folder_path):
    # Get all .jpg files in the folder and subfolders
    return glob.glob(os.path.join(folder_path, '**', '*.jpg'), recursive=True) 

def remove_lfcr(text):
    return text.replace("\n"," ").replace("\r"," ")

folder_path = sys.argv[1]
jpgfiles = get_jpg_files(folder_path)
print("Found the following JPG files:")
for jpg_file in jpgfiles:
    print(jpg_file)
    image = PIL.Image.open(jpg_file)
#code goes here
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=sys_instruct_art),
        contents=["Make your response good for exif description data",image]
        )
    para_text = response.text.splitlines()
    nonempty_para_text = [line for line in para_text if line.strip()]
    for paragraph in nonempty_para_text:
        output = remove_lfcr(paragraph)
        output = output[:450]
        print(output)
        time.sleep(1)

