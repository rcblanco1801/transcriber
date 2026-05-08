import torchaudio
import os
from pathlib import Path

# Define tu BASE_DIR (reemplaza esto por tu ruta real)
BASE_DIR = Path("./models") 
ruta_destino = BASE_DIR / "voxpopuli"

# Crear la carpeta si no existe
os.makedirs(ruta_destino, exist_ok=True)

print("Descargando el modelo VOXPOPULI_ASR_BASE_10K_ES desde PyTorch...")

# Obtenemos el "bundle" (paquete) del modelo desde torchaudio
bundle = torchaudio.pipelines.VOXPOPULI_ASR_BASE_10K_ES

# Al solicitar el modelo y pasarle el 'model_dir', torchaudio lo descarga 
# automáticamente en esa carpeta si no lo encuentra allí primero.
modelo = bundle.get_model(dl_kwargs={"model_dir": str(ruta_destino)})

print(f"¡Listo! Modelo descargado y guardado en: {ruta_destino}")