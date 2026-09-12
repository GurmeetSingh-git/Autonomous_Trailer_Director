import subprocess
import os
from datetime import datetime, timedelta

def time_to_seconds(time_str):
    """Converts HH:MM:SS.mmm to total seconds (float)."""
    h, m, s = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

# Define your exact edit decision list (EDL) with snip coordinates
trailer_clips = [
    ("00:01:27.700", "00:01:39.133", "The Promise"),
    ("00:02:03.833", "00:02:32.167", "Social Reality"),
    ("00:03:16.967", "00:03:37.067", "The Price Shock"),
    ("00:02:45.333", "00:03:07.300", "Hard Labor Montage"),
    ("00:03:37.067", "00:03:52.033", "The Climax Pressure")
]

input_video = "tests/test_video.mp4"
temp_files = []

print("🎬 Step 1: Slicing clips and dynamically applying audio/video fades...")

for i, (start, end, desc) in enumerate(trailer_clips):
    temp_output = f"tests/clip_{i}.mp4"
    temp_files.append(temp_output)
    
    # Calculate exact clip duration dynamically
    start_sec = time_to_seconds(start)
    end_sec = time_to_seconds(end)
    duration = end_sec - start_sec
    
    # Fade out starts 0.4 seconds before the clip ends
    fade_out_start = max(0, duration - 0.4)
    
    # Construct dynamic filter strings for exact lengths
    vf_filter = f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out_start}:d=0.4"
    af_filter = f"afade=t=in:st=0:d=0.4,afade=t=out:st={fade_out_start}:d=0.4"
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", input_video,
        "-vf", vf_filter,
        "-af", af_filter,
        "-c:v", "libx264",
        "-c:a", "aac",
        temp_output
    ]
    
    print(f"Processing Clip {i+1} ({desc}) - Duration: {duration:.2f}s...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"Error on clip {i+1}: {result.stderr.decode('utf-8')}")

print("\n🔗 Step 2: Merging clips together into final_trailer.mp4...")

concat_file_path = "tests/concat_list.txt"
with open(concat_file_path, "w") as f:
    for file in temp_files:
        f.write(f"file '{os.path.basename(file)}'\n")

final_output = "tests/final_trailer.mp4"
concat_cmd = [
    "ffmpeg", "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", concat_file_path,
    "-c", "copy",
    final_output
]

subprocess.run(concat_cmd)

# Clean up temporary split files
print("🧹 Cleaning up temporary slice files...")
for file in temp_files:
    if os.path.exists(file):
        os.remove(file)
if os.path.exists(concat_file_path):
    os.remove(concat_file_path)

print(f"\n✨ Success! Your cinematic trailer with full audio is ready at: {final_output}")