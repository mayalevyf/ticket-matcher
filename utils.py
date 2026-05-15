import re
import pandas as pd
from datetime import datetime


# ---------------------------------------------------------------------------
# Nettoyage des montants
# ---------------------------------------------------------------------------

def normaliser_montant(valeur) -> float | None:
    """Convertit n'importe quelle représentation de montant en float."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    try:
        if isinstance(valeur, str):
            valeur = valeur.replace(" ", "").replace("\u00a0", "")
            valeur = valeur.replace("€", "").replace("EUR", "")
            # Gère les formats 1.234,56 et 1,234.56
            if re.search(r"\d[.,]\d{3}[.,]\d{2}$", valeur):
                valeur = valeur[:-3].replace(".", "").replace(",", "") + valeur[-3:]
            valeur = valeur.replace(",", ".")
        return round(float(valeur), 2)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Nettoyage des dates
# ---------------------------------------------------------------------------

FORMATS_DATE = [
    "%d/%m/%Y", "%d/%m/%y",
    "%d-%m-%Y", "%d-%m-%y",
    "%Y-%m-%d",
    "%d.%m.%Y", "%d.%m.%y",
    "%m/%d/%Y", "%m/%d/%y",
]


def normaliser_date(valeur) -> datetime | None:
    """Convertit n'importe quel format de date en objet datetime."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    if isinstance(valeur, datetime):
        return valeur
    if isinstance(valeur, pd.Timestamp):
        return valeur.to_pydatetime()
    texte = str(valeur).strip()
    for fmt in FORMATS_DATE:
        try:
            return datetime.strptime(texte, fmt)
        except ValueError:
            continue
    return None


def date_vers_str(valeur) -> str:
    """Formate un datetime en JJ/MM/AAAA pour affichage."""
    d = normaliser_date(valeur)
    return d.strftime("%d/%m/%Y") if d else ""


# ---------------------------------------------------------------------------
# Nettoyage des noms d'enseignes
# ---------------------------------------------------------------------------

# Mots parasites fréquents dans les libellés bancaires
_MOTS_PARASITES = re.compile(
    r"\b(carte|cb|virement|prelevement|prlv|www|http|https|fr|sas|sarl|sa|eurl|sro|gmbh)\b",
    re.IGNORECASE,
)

_CARACTERES_SPECIAUX = re.compile(r"[*_\-/\\|#@!?=+<>{}[\]()]")


def normaliser_enseigne(valeur: str | None) -> str:
    """Nettoie et normalise un nom d'enseigne pour le matching."""
    if not valeur:
        return ""
    texte = str(valeur).strip()
    texte = _CARACTERES_SPECIAUX.sub(" ", texte)
    texte = _MOTS_PARASITES.sub(" ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    texte = texte.upper()
    return texte


# ---------------------------------------------------------------------------
# Détection automatique des colonnes d'un relevé bancaire
# ---------------------------------------------------------------------------

_CANDIDATS_DATE = ["date", "date opération", "date operation", "date valeur",
                   "dateop", "date_op", "jour"]
_CANDIDATS_MONTANT = ["montant", "debit", "débit", "credit", "crédit",
                      "valeur", "somme", "amount"]
_CANDIDATS_LIBELLE = ["libellé", "libelle", "description", "intitulé",
                      "intitule", "label", "detail", "détail", "wording"]


def _score_colonne(nom: str, candidats: list[str]) -> int:
    nom_norm = nom.lower().strip()
    for i, c in enumerate(candidats):
        if nom_norm == c:
            return len(candidats) - i          # correspondance exacte = score max
        if c in nom_norm or nom_norm in c:
            return len(candidats) - i - 1      # correspondance partielle
    return 0


def detecter_colonnes(df: pd.DataFrame) -> dict:
    """
    Détecte automatiquement les colonnes date, montant, libellé dans un DataFrame.
    Retourne {"date": col, "montant": col, "libelle": col} avec None si non trouvé.
    """
    colonnes = list(df.columns)
    resultat = {"date": None, "montant": None, "libelle": None}

    for cible, candidats in [
        ("date",    _CANDIDATS_DATE),
        ("montant", _CANDIDATS_MONTANT),
        ("libelle", _CANDIDATS_LIBELLE),
    ]:
        scores = {col: _score_colonne(col, candidats) for col in colonnes}
        meilleure = max(scores, key=scores.get)
        if scores[meilleure] > 0:
            resultat[cible] = meilleure

    return resultat


# ---------------------------------------------------------------------------
# Construction du DataFrame tickets (sortie OCR → app)
# ---------------------------------------------------------------------------

COLONNES_TICKETS = ["fichier", "enseigne", "montant", "tva", "date"]


def creer_dataframe_vide() -> pd.DataFrame:
    return pd.DataFrame(columns=COLONNES_TICKETS)


def ajouter_ligne(df: pd.DataFrame, resultat_ocr: dict) -> pd.DataFrame:
    """Ajoute une ligne OCR normalisée au DataFrame tickets."""
    ligne = {
        "fichier":  resultat_ocr.get("fichier", ""),
        "enseigne": resultat_ocr.get("enseigne") or "",
        "montant":  normaliser_montant(resultat_ocr.get("montant")),
        "tva":      normaliser_montant(resultat_ocr.get("tva")),
        "date":     date_vers_str(resultat_ocr.get("date")),
    }
    return pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
