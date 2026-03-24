from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from rq.job import Job
from tasks import q
from pathlib import Path           
from fastapi import status 
from rq.exceptions import NoSuchJobError
import uuid, os, shutil, redis

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

r = redis.Redis()
ALLOWED_EXT = {".wav", ".mp3", ".flac", ".aac", ".m4a", 
    ".ogg", ".opus", ".webm", ".mp4", ".mkv", ".mov", ".avi"}

def _validate_extension(filename: str):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Extensión «{ext}» no soportada. Solo {', '.join(ALLOWED_EXT)}"
        )
    
def _remove_transcription(path: Path, job_id: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    else:
        # Opcional: marca el job como “purged”
        job = Job.fetch(job_id, connection=r)
        job.meta["purged"] = True
        job.save_meta()

# ---------- Vistas HTML ----------

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/transcribe", response_class=RedirectResponse, status_code=303)
async def enqueue_web(request: Request,
                      file: UploadFile = File(...),
                      model_type: str = Form("small")):
    _validate_extension(file.filename)
    job_id = uuid.uuid4().hex
    filename = os.path.basename(file.filename)
    dest = os.path.join(UPLOAD_DIR, f"{job_id}_{filename}")
    with open(dest, "wb") as bf:
        shutil.copyfileobj(file.file, bf)

    job = q.enqueue("tasks.transcribe_file",
                    dest, model_type,
                    job_id=job_id,
                    job_timeout="5d")

    # Redirigimos a la página de estado
    return f"/jobs/{job.id}"

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_status_html(request: Request, job_id: str):
    try:
        job = Job.fetch(job_id, connection=r)
    except NoSuchJobError:
        txt = Path(f"transcripts/{job_id}.txt")
        if txt.exists():
            return templates.TemplateResponse("job.html",
                                          {"request": request, "job_id": job.id})
        raise HTTPException(410, "La transcripción ya no está disponible")
    
    if job.is_finished:
        # En lugar de descargar, redirigimos a la vista 'done'
        return RedirectResponse(f"/done/{job_id}", status_code=303)
    elif job.is_failed:
        raise HTTPException(500, "La transcripción falló")
    else:
        return templates.TemplateResponse("job.html",
                                          {"request": request, "job_id": job.id})
    
@app.get("/download/{job_id}")
async def download(job_id: str, background_tasks: BackgroundTasks):
    try:
        job = Job.fetch(job_id, connection=r)
    except NoSuchJobError:
        file_path = Path(f"transcripts/{job_id}.txt")
        if file_path.exists():
            return FileResponse(
                path=file_path,
                media_type="text/plain",
                filename=f"{file_path.stem}.txt"
            )
        raise HTTPException(410, "La transcripción ya no está disponible")
    
    if not job.is_finished:
        raise HTTPException(202, "Aún se está procesando")

    file_path = Path(f"transcripts/{job_id}.txt")
    if not file_path.exists():
        raise HTTPException(410, "La transcripción ya no está disponible")

    # programa la limpieza
    background_tasks.add_task(_remove_transcription, file_path, job_id)

    return FileResponse(
        path=file_path,
        media_type="text/plain",
        filename=f"{file_path.stem}.txt"
    )

@app.get("/done/{job_id}", response_class=HTMLResponse)
def done(request: Request, job_id: str):
    """
    Muestra la página 'Transcripción lista' con el enlace de descarga.
    """
    return templates.TemplateResponse("done.html", {"request": request,
                                                    "job_id": job_id})

# ---------- Endpoints JSON (compatibilidad API) ----------

@app.post("/api/transcribe", status_code=202)
async def enqueue_api(file: UploadFile = File(...), model_type: str = Form(...)):
    # idéntico a la versión web, sólo cambia la respuesta
    job_id = uuid.uuid4().hex
    dest = os.path.join(UPLOAD_DIR, f"{job_id}_{os.path.basename(file.filename)}")
    with open(dest, "wb") as bf:
        shutil.copyfileobj(file.file, bf)
    job = q.enqueue("tasks.transcribe_file", dest, model_type,
                    job_id=job_id, job_timeout="5d")
    return {"job_id": job.id}

@app.get("/api/jobs/{job_id}")
def job_status_api(job_id: str):
    try:
        job = Job.fetch(job_id, connection=r)
    except redis.exceptions.RedisError:
        raise HTTPException(404, "Job desconocido")
    except NoSuchJobError:
        file_path = Path(f"transcripts/{job_id}.txt")
        if file_path.exists():
            return {"status": "finished", "result": str(file_path)}
        raise HTTPException(500, f"Error: {job.exc_info}")

    if job.is_finished:
        return {"status": "finished", "result": job.result}
    if job.is_failed:
        raise HTTPException(500, f"Error: {job.exc_info}")
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)