import argparse
import json
import os
import sys
import warnings

# Filter warnings to keep output clean
warnings.filterwarnings("ignore")

def main():
    parser = argparse.ArgumentParser(description="Run Whisper ASR in a separate process")
    parser.add_argument("audio_path", help="Path to the input audio file")
    parser.add_argument("--model", default="base", help="Whisper model size")
    parser.add_argument("--language", default=None, help="Language code")
    parser.add_argument("--model_dir", default=None, help="Custom model directory")
    
    args = parser.parse_args()
    
    try:
        # Set model directory if provided
        if args.model_dir:
            os.environ['WHISPER_CACHE_DIR'] = args.model_dir
            
        import whisper
        import torch
        
        # Check if CUDA is available (just for info, we might be on CPU)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load model
        model = whisper.load_model(args.model, download_root=args.model_dir, device=device)
        
        # Transcribe
        result = model.transcribe(
            args.audio_path,
            language=args.language if args.language and args.language != "None" else None
        )
        
        # Output result as JSON
        # We only need the segments
        output = {
            "segments": result["segments"],
            "text": result["text"]
        }
        
        # Print JSON to stdout
        print(json.dumps(output))
        
    except Exception as e:
        # Print error to stderr
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
