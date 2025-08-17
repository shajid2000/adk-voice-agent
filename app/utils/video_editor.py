import requests
import tempfile
import os
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
import time


def stitch_videos(video_data, output_path="final_video.mp4"):
    """
    Stitches a list of videos (with URLs) into a single video.

    Args:
        video_data (list): List of dicts containing 'url' of each video.
        output_path (str): Path to save the final stitched video.

    Returns:
        str: Path to the stitched video file.
    """
    clips = []
    temp_files = []

    try:
        # Download each video and create VideoFileClip
        for item in video_data:
            url = item.get("url")
            if not url:
                continue

            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_files.append(temp_file.name)

            # Download video content
            resp = requests.get(url, stream=True)
            resp.raise_for_status()
            with open(temp_file.name, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)

            # Load video clip
            clip = VideoFileClip(temp_file.name)
            clips.append(clip)

        # Concatenate all clips
        if not clips:
            raise ValueError("No valid video clips to stitch.")

        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

        # Close all clips
        final_clip.close()
        for clip in clips:
            clip.close()

        return {"success": True, "path": output_path}

    finally:
        # Clean up temp files with a small delay
        for file in temp_files:
            if os.path.exists(file):
                try:
                    time.sleep(0.1)  # small delay before deletion
                    os.remove(file)
                except PermissionError:
                    print(f"Warning: Could not delete temp file {file} (still in use).")


# -------------------- Example Usage -------------------- #

# data = [
#     {
#         "sec": 1,
#         "scene": "A fluffy tabby cat sits on a woven rug in a sunlit living room, intently watching a bright red ball of yarn a few feet away. The living room is cozy with a sofa and plants. The cat's tail twitches with anticipation as it focuses on the yarn.",
#         "dialog": "(Sound of gentle purring)",
#         "url": "https://bytedance-animatediff-lightning.hf.space/file=/tmp/gradio/968e56d2722ace8e5f363c29dd47cf54c53d4a92/df65a543bebf4f43b8d059525412b09e.mp4"
#     },
#     {
#         "sec": 2,
#         "scene": "The fluffy tabby cat is still on the woven rug in the sunlit living room. Suddenly, it pounces, leaping towards the bright red ball of yarn with playful energy. The cozy living room is in the background as the cat springs into action.",
#         "dialog": "(Sound of a soft thump)",
#         "url": "https://bytedance-animatediff-lightning.hf.space/file=/tmp/gradio/62b1bbe9d94c87af2f1eb2b5edeb9a78870b3102/c981030f357748b5932df4f5f2fffe01.mp4"
#     },
#     {
#         "sec": 3,
#         "scene": "Now in the sunlit living room, the fluffy tabby cat bats the bright red ball of yarn with its paws, sending it rolling across the woven rug. The cat chases after it, eyes wide with excitement. The cozy living room setting remains in the background.",
#         "dialog": "(Sound of a playful meow)",
#         "url": "https://bytedance-animatediff-lightning.hf.space/file=/tmp/gradio/ea07b076a76212a83224237dad404a404865a865/4cc3f895979f4864a82b263ae141a444.mp4"
#     },
#     {
#         "sec": 4,
#         "scene": "The bright red ball of yarn rolls under a sofa in the sunlit living room. The fluffy tabby cat peeks under the sofa, trying to reach the yarn. The woven rug and plants are still visible around the sofa, keeping the cozy living room consistent.",
#         "dialog": "(Sound of soft scratching)",
#         "url": "https://bytedance-animatediff-lightning.hf.space/file=/tmp/gradio/d2cc1bf748f85c41b2c94f04413efabdbf08ce56/37f0a55522674de09e6332ba066ac17f.mp4"
#     },
#     {
#         "sec": 5,
#         "scene": "The fluffy tabby cat triumphantly emerges from under the sofa in the sunlit living room, the bright red ball of yarn clutched in its mouth. It proudly carries its prize back to the center of the woven rug, ready to continue playing in the cozy living room.",
#         "dialog": "(Sound of contented purring)",
#         "url": "https://bytedance-animatediff-lightning.hf.space/file=/tmp/gradio/32694830d49f4ef5bd75f769117352e2a2315ac9/0c0f7df48c02400690a99609a0f3d3e3.mp4"
#     }
# ]

# if __name__ == "__main__":
#     stitched_path = stitch_videos(data, output_path="stitched_cat_video.mp4")
#     print("Stitched video saved at:", stitched_path)
