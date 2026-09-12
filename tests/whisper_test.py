import os
from dotenv import load_dotenv
from google import genai
from scenedetect import detect, ContentDetector  # 1. Import PySceneDetect

# 2. Load variables from the local .env file into os.environ
load_dotenv()

# 3. Initialize the Gemini client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# # --- PART 1: GEMINI AUDIO ANALYSIS ---
# print("Analyzing audio with Gemini...")
# audio_file = client.files.upload(file="tests/test_audio.wav")

# response = client.models.generate_content(
#     model="gemini-2.5-flash",  # Using a standard fast tier model
#     contents=[
#         audio_file,
#         "Listen to this film audio track. Provide a timestamped breakdown of the dialogue and emotional shifts."
#     ]
# )

# print("\n--- GEMINI AUDIO ANALYSIS ---")
# print(response.text)

# --- PART 2: PYSCENEDETECT VIDEO ANALYSIS ---
print("\nDetecting video scenes locally...")
# This scans your local test_video.mp4 for camera cuts
scene_list = detect('tests/test_video.mp4', ContentDetector())

print("\n--- DETECTED SHOTS (PySceneDetect) ---")
for i, scene in enumerate(scene_list):
    print(f"Shot {i+1}: Start {scene[0].get_timecode()} -> End {scene[1].get_timecode()}")