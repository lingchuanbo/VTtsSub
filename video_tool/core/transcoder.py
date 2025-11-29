import subprocess
import os

class Transcoder:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def transcode(self, input_path, output_path, crf=23, preset="medium"):
        """
        Transcodes a video file.
        
        Args:
            input_path (str): Path to input video.
            output_path (str): Path to output video.
            crf (int): Constant Rate Factor (0-51, lower is better quality). Default 23.
            preset (str): Encoding preset (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow).
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        command = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]

        print(f"Running command: {' '.join(command)}")
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Transcoding complete: {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error transcoding: {e}")
            raise e

if __name__ == "__main__":
    # Test
    pass
