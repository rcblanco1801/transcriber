from rq import Queue
import redis, os
from transcriber import Transcriber
from pathlib import Path


TRANSCRIPT_DIR = Path("transcripts")
TRANSCRIPT_DIR.mkdir(exist_ok=True)

r = redis.Redis()
q = Queue("transcriber", connection=r)

def transcribe_file(audio_path: str, model_type: str) -> str:
    transcriber = Transcriber()          # se crea una sola vez por worker
    out = transcriber(audio_path, model_type)
    
    transcription = ""
    for segment in out["segments"]:
        speaker = segment.get("speaker")
        text = segment["text"].strip()
        if speaker is not None:
            transcription += f"[{speaker.replace("SPEAKER_", "Persona ")}]: {text}\n\n"
        else:
            transcription += f"[???]: {text}\n\n"

    job_id = Path(audio_path).stem.split("_")[0]
    fname = f"{job_id}.txt"
    txt_path = TRANSCRIPT_DIR / fname

    with open(txt_path, "w", encoding="utf-8") as f:  
        f.write(transcription)

    os.remove(audio_path)              
    return str(txt_path)