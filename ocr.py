import base64
import json
import os
import re
import subprocess
import ollama
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "qwen3-vl"

# Forcer CUDA avant tout import GPU — à positionner AVANT ollama.chat()
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("OLLAMA_FLASH_ATTENTION", "1")   # réduit la VRAM (~20 %)

GPU_OPTIONS = {
    "temperature": 0,
    "num_gpu": -1,      # -1 = toutes les couches sur GPU
    "main_gpu": 0,      # index de la carte GPU principale
    "num_ctx": 4096,
    "num_thread": 4,    # limite les threads CPU quand le GPU prend tout
}

PROMPT = """
Analyse cette image et extrais exactement quatre informations :
- Le montant total payé (en chiffres, avec centimes)
- Le montant de la TVA (taxe, tax, VAT) si présent sur le ticket
- La date de la transaction
- Le nom de l'enseigne ou du commerce

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après, sans balises markdown :
{"montant": <nombre décimal>, "tva": <nombre décimal>, "date": "<JJ/MM/AAAA>", "enseigne": "<nom>"}

Règles :
- montant : montant total TTC, nombre décimal uniquement, ex: 12.50
- tva : montant de TVA en euros, nombre décimal uniquement, ex: 2.08 (utilise null si absent ou illisible)
- date : format JJ/MM/AAAA uniquement
- enseigne : nom court et lisible, ex: "Carrefour", "SNCF", "Amazon"
- Si une information est illisible ou absente, utilise null
"""


# ---------------------------------------------------------------------------
# Diagnostic GPU
# ---------------------------------------------------------------------------

def diagnostiquer_gpu() -> dict:
    """
    Vérifie si Ollama utilise bien le GPU.
    Retourne un dict avec les clés :
      - nvidia_ok   : bool  — nvidia-smi répond
      - nvidia_info : str   — nom + VRAM disponible
      - ollama_gpu  : bool  — le modèle est chargé sur GPU dans ollama ps
      - ollama_info : str   — détail ollama ps
      - avertissement : str — message lisible à afficher dans l'UI
    """
    result = {
        "nvidia_ok": False,
        "nvidia_info": "",
        "ollama_gpu": False,
        "ollama_info": "",
        "avertissement": "",
    }

    # --- nvidia-smi ---
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            timeout=5,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        result["nvidia_ok"] = True
        result["nvidia_info"] = out
    except (FileNotFoundError, subprocess.SubprocessError):
        result["avertissement"] = (
            "nvidia-smi introuvable — Ollama risque de tourner sur CPU. "
            "Vérifie que les drivers NVIDIA et CUDA sont installés."
        )
        return result

    # --- ollama ps (modèle chargé ?) ---
    try:
        ps = ollama.ps()
        modeles = ps.get("models", []) if isinstance(ps, dict) else getattr(ps, "models", [])
        for m in modeles:
            nom = m.get("name", "") if isinstance(m, dict) else getattr(m, "name", "")
            if MODEL in nom:
                details = m if isinstance(m, dict) else vars(m)
                # ollama ps retourne "size_vram" en octets si le modèle est sur GPU
                size_vram = details.get("size_vram", 0)
                result["ollama_gpu"] = size_vram > 0
                result["ollama_info"] = (
                    f"{nom} — VRAM utilisée : {size_vram // 1024**2} Mo"
                    if size_vram else f"{nom} chargé (VRAM=0 → CPU uniquement)"
                )
                break
        if not result["ollama_info"]:
            result["ollama_info"] = "Modèle pas encore chargé (premier appel plus lent)"
    except Exception as e:
        result["ollama_info"] = f"ollama ps indisponible : {e}"

    if result["nvidia_ok"] and not result["ollama_gpu"] and result["ollama_info"]:
        result["avertissement"] = (
            "GPU NVIDIA détecté mais le modèle semble tourner sur CPU. "
            "Relance `ollama serve` et vérifie que Ollama est compilé avec support CUDA "
            "(https://ollama.com/download)."
        )

    return result


# ---------------------------------------------------------------------------
# Encodage image
# ---------------------------------------------------------------------------

def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


# ---------------------------------------------------------------------------
# Parsing de la réponse
# ---------------------------------------------------------------------------

def _parse_reponse(texte: str) -> dict:
    texte = texte.strip()
    texte = re.sub(r"^```[a-z]*\n?", "", texte)
    texte = re.sub(r"\n?```$", "", texte)
    # Ignorer le bloc <think> de Qwen3
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip()

    match = re.search(r"\{.*\}", texte, re.DOTALL)
    if match:
        texte = match.group()

    try:
        data = json.loads(texte)
    except json.JSONDecodeError:
        return {"montant": None, "tva": None, "date": None, "enseigne": None,
                "erreur": "JSON invalide"}

    tva_brute = _nettoyer_montant(data.get("tva"))
    return {
        "montant":  _nettoyer_montant(data.get("montant")),
        "tva":      -tva_brute if tva_brute is not None else None,
        "date":     _nettoyer_date(data.get("date")),
        "enseigne": _nettoyer_enseigne(data.get("enseigne")),
    }


def _nettoyer_montant(valeur) -> float | None:
    if valeur is None:
        return None
    try:
        if isinstance(valeur, str):
            valeur = valeur.replace(",", ".").replace("€", "").replace(" ", "")
        return round(float(valeur), 2)
    except (ValueError, TypeError):
        return None


def _nettoyer_date(valeur) -> str | None:
    if not valeur:
        return None
    formats = [
        "%d/%m/%Y", "%d/%m/%y",
        "%d-%m-%Y", "%d-%m-%y",
        "%Y-%m-%d",
        "%d.%m.%Y", "%d.%m.%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(valeur).strip(), fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return str(valeur).strip()


def _nettoyer_enseigne(valeur) -> str | None:
    if not valeur:
        return None
    valeur = str(valeur).strip()
    valeur = re.sub(r"\s+", " ", valeur)
    return valeur.title() if valeur.isupper() else valeur


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def extraire_ticket(image_bytes: bytes, nom_fichier: str = "") -> dict:
    """
    Envoie une image à Qwen3-VL via Ollama et retourne un dict :
    {"montant": float|None, "tva": float|None, "date": str|None, "enseigne": str|None}
    """
    image_b64 = _encode_image(image_bytes)

    try:
        reponse = ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT,
                    "images": [image_b64],
                }
            ],
            options=GPU_OPTIONS,
        )
        texte_brut = reponse["message"]["content"]
    except Exception as e:
        return {
            "montant": None,
            "tva": None,
            "date": None,
            "enseigne": None,
            "erreur": f"Ollama inaccessible : {e}",
        }

    resultat = _parse_reponse(texte_brut)
    resultat["fichier"] = Path(nom_fichier).name if nom_fichier else ""
    return resultat


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=== Diagnostic GPU ===")
    diag = diagnostiquer_gpu()
    print(f"nvidia-smi : {'OK — ' + diag['nvidia_info'] if diag['nvidia_ok'] else 'NON DÉTECTÉ'}")
    print(f"ollama ps  : {diag['ollama_info']}")
    if diag["avertissement"]:
        print(f"⚠️  {diag['avertissement']}")
    print()

    if len(sys.argv) < 2:
        print("Usage : python ocr.py <chemin_image>")
        sys.exit(1)

    chemin = Path(sys.argv[1])
    if not chemin.exists():
        print(f"Fichier introuvable : {chemin}")
        sys.exit(1)

    print(f"Analyse de {chemin.name} (num_gpu={GPU_OPTIONS['num_gpu']})…")
    with open(chemin, "rb") as f:
        contenu = f.read()

    resultat = extraire_ticket(contenu, chemin.name)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
