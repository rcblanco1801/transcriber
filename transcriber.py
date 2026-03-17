import whisperx, gc, os, pathlib
from huggingface_hub import snapshot_download


HF_TOKEN = os.environ["HF_TOKEN"]
BASE_DIR = pathlib.Path("models")
REPOS = {   # repo HF  ->  subcarpeta local
    "openai/whisper-small": "whisper-small",
    "openai/whisper-large-v3-turbo": "whisper-large-v3-turbo",
}

def _go_offline():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    print("Modo OFFLINE activo.")

def _ensure_repo(repo_id: str, subdir: str):
    """Descarga repo_id en models/subdir si aún no existe."""
    tgt = BASE_DIR / subdir
    if tgt.exists() and any(tgt.iterdir()):
        print(f"{repo_id} ya descargado.")
        return tgt
    print(f"Descargando {repo_id} ...")
    snapshot_download(
        repo_id,
        local_dir=str(tgt),
        local_dir_use_symlinks=False,          # archivos reales, no symlinks
        token=HF_TOKEN,
        resume_download=True,                  # reanuda si se corta
    )
    return tgt

def _prepare_models():
    BASE_DIR.mkdir(exist_ok=True)
    for repo, sub in REPOS.items():
        _ensure_repo(repo, sub)

class Transcriber:
    def __init__(self):
        self._device = "cpu"
        self._batch_size = 16
        self._compute_type = "int8"
        self._paths = {
            "whisper-large": BASE_DIR / "whisper-large-v3-turbo",
            "whisper-small": BASE_DIR / "whisper-small",
            "align": BASE_DIR / "voxpopuli",
        }

        _prepare_models()
        _go_offline()

    def __call__(self, audio_file, model_type = "large"):
        # --- Transcripción ------------------------------------------------------
        model_name = "small"
        path = self._paths["whisper-small"]
        if model_type == "large":
            model_name = "large-v3-turbo"
            path = self._paths["whisper-large"]

        model = whisperx.load_model(
            model_name, self._device,
            compute_type=self._compute_type, language="es",
            download_root=str(path)
        )
        audio = whisperx.load_audio(audio_file)
        result = model.transcribe(audio, batch_size=self._batch_size)
        del model; gc.collect()

        # --- Alineado ------------------------------------------------------
        align_model, meta = whisperx.load_align_model(
            language_code=result["language"], device=self._device,
            model_dir=self._paths["align"]
        )
        result = whisperx.align(
            result["segments"], align_model, meta, audio,
            self._device, return_char_alignments=False
        )
        del align_model; gc.collect()

        # --- Diarización ---------------------------------------------------
        diar = whisperx.diarize.DiarizationPipeline(
            device=self._device,
            use_auth_token=None
        )
        spk = diar(audio)
        del diar; gc.collect()
        
        return whisperx.assign_word_speakers(spk, result)

