import base64
import json
import re
import ollama
from pathlib import Path
from datetime import datetime


# Nom exact du modèle — vérifie avec : ollama list
MODEL = "qwen3-vl"

# Options GPU
# num_gpu=-1  : charge toutes les couches sur le GPU (recommandé)
# num_gpu=0   : CPU uniquement
# num_gpu=20  : charge partielle si VRAM insuffisante (ajuste selon ta carte)
GPU_OPTIONS = {
    "temperature": 0,
    "num_gpu": -1,         # -1 = tout sur GPU
    "num_ctx": 4096,       # taille du contexte — réduis à 2048 si VRAM < 6 Go
}

PROMPT = """Tu es un assistant d'extraction de données sur des tickets de caisse, factures et reçus.

Analyse cette image et extrais exactement trois informations :
- Le montant total payé (en chiffres, avec centimes)
- La date de la transaction
- Le nom de l'enseigne ou du commerce

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après, sans balises markdown :
{"montant": <nombre décimal>, "date": "<JJ/MM/AAAA>", "enseigne": "<nom>"}

Règles :
- montant : nombre décimal uniquement, ex: 12.50 (utilise le point comme séparateur décimal)
- date : format JJ/MM/AAAA uniquement
- enseigne : nom court et lisible, ex: "Carrefour", "SNCF", "Amazon"
- Si une information est illisible ou absente, utilise null
"""


def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _parse_reponse(texte: str) -> dict:
    texte = texte.strip()
    texte = re.sub(r"^```[a-z]*\n?", "", texte)
    texte = re.sub(r"\n?```$", "", texte)
    texte = texte.strip()

    match = re.search(r"\{.*\}", texte, re.DOTALL)
    if match:
        texte = match.group()

    try:
        data = json.loads(texte)
    except json.JSONDecodeError:
        return {"montant": None, "date": None, "enseigne": None, "erreur": "JSON invalide"}

    return {
        "montant": _nettoyer_montant(data.get("montant")),
        "date":    _nettoyer_date(data.get("date")),
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


def _nettoyer_date(valeur: str | None) -> str | None:
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


def _nettoyer_enseigne(valeur: str | None) -> str | None:
    if not valeur:
        return None
    valeur = str(valeur).strip()
    valeur = re.sub(r"\s+", " ", valeur)
    return valeur.title() if valeur.isupper() else valeur


def extraire_ticket(image_bytes: bytes, nom_fichier: str = "") -> dict:
    """
    Envoie une image à Qwen2-VL via Ollama et retourne un dict :
    {"montant": float|None, "date": str|None, "enseigne": str|None}
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
            "date": None,
            "enseigne": None,
            "erreur": f"Ollama inaccessible : {e}",
        }

    resultat = _parse_reponse(texte_brut)
    resultat["fichier"] = Path(nom_fichier).name if nom_fichier else ""
    return resultat


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage : python ocr.py <chemin_image>")
        sys.exit(1)

    chemin = Path(sys.argv[1])
    if not chemin.exists():
        print(f"Fichier introuvable : {chemin}")
        sys.exit(1)

    print(f"Analyse de {chemin.name} (GPU num_gpu={GPU_OPTIONS['num_gpu']})...")
    with open(chemin, "rb") as f:
        contenu = f.read()

    resultat = extraire_ticket(contenu, chemin.name)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
