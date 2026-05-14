import pandas as pd
from datetime import timedelta
from rapidfuzz import fuzz

from utils import normaliser_montant, normaliser_date, normaliser_enseigne


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def effectuer_matching(
    df_tickets: pd.DataFrame,
    df_releve: pd.DataFrame,
    col_date: str,
    col_montant: str,
    col_libelle: str,
    tolerance_montant: float = 0.02,
    tolerance_jours: int = 3,
    seuil_nom: int = 60,
) -> pd.DataFrame:
    """
    Rapproche chaque ligne du DataFrame tickets avec le relevé bancaire.

    Retourne le DataFrame tickets enrichi avec les colonnes :
    - statut        : ✅ Trouvé / ⚠️ Écart / ❌ Non trouvé
    - releve_date   : date de la ligne matchée dans le relevé
    - releve_libelle: libellé de la ligne matchée
    - releve_montant: montant de la ligne matchée
    - score_nom     : score de similarité du nom (0-100)
    """

    # Normalisation du relevé
    releve = df_releve.copy()
    releve["_montant"] = releve[col_montant].apply(normaliser_montant)
    releve["_date"]    = releve[col_date].apply(normaliser_date)
    releve["_libelle"] = releve[col_libelle].apply(normaliser_enseigne)

    # Suppression des lignes sans montant ou sans date dans le relevé
    releve = releve.dropna(subset=["_montant", "_date"])

    resultats = []

    for _, ticket in df_tickets.iterrows():
        montant_ticket  = normaliser_montant(ticket.get("montant"))
        date_ticket     = normaliser_date(ticket.get("date"))
        enseigne_ticket = normaliser_enseigne(ticket.get("enseigne"))

        meilleur = _trouver_meilleure_correspondance(
            montant_ticket,
            date_ticket,
            enseigne_ticket,
            releve,
            tolerance_montant,
            tolerance_jours,
            seuil_nom,
        )

        resultats.append({
            "fichier":         ticket.get("fichier", ""),
            "enseigne":        ticket.get("enseigne", ""),
            "montant":         montant_ticket,
            "date":            ticket.get("date", ""),
            "statut":          meilleur["statut"],
            "releve_date":     meilleur["releve_date"],
            "releve_libelle":  meilleur["releve_libelle"],
            "releve_montant":  meilleur["releve_montant"],
            "score_nom":       meilleur["score_nom"],
        })

    return pd.DataFrame(resultats)


# ---------------------------------------------------------------------------
# Logique de correspondance
# ---------------------------------------------------------------------------

def _trouver_meilleure_correspondance(
    montant: float | None,
    date,
    enseigne: str,
    releve: pd.DataFrame,
    tolerance_montant: float,
    tolerance_jours: int,
    seuil_nom: int,
) -> dict:
    """Cherche la meilleure ligne du relevé correspondant au ticket."""

    vide = {
        "statut": "❌ Non trouvé",
        "releve_date": "",
        "releve_libelle": "",
        "releve_montant": "",
        "score_nom": 0,
    }

    if montant is None:
        return vide

    # --- Filtre 1 : montant dans la tolérance ---
    candidats = releve[
        (releve["_montant"] - montant).abs() <= tolerance_montant
    ].copy()

    if candidats.empty:
        # Tentative avec tolérance élargie x5 → statut Écart si trouvé
        candidats_larges = releve[
            (releve["_montant"] - montant).abs() <= tolerance_montant * 5
        ].copy()
        if candidats_larges.empty:
            return vide
        # On continue avec les candidats larges, statut sera ⚠️ Écart
        candidats = candidats_larges
        ecart_montant = True
    else:
        ecart_montant = False

    # --- Filtre 2 : date dans la tolérance ---
    if date is not None:
        date_min = date - timedelta(days=tolerance_jours)
        date_max = date + timedelta(days=tolerance_jours)
        candidats_date = candidats[
            (candidats["_date"] >= date_min) & (candidats["_date"] <= date_max)
        ].copy()
        ecart_date = candidats_date.empty
        if not ecart_date:
            candidats = candidats_date
    else:
        ecart_date = False

    # --- Score 3 : similarité du nom ---
    if enseigne:
        candidats["_score_nom"] = candidats["_libelle"].apply(
            lambda lib: fuzz.partial_ratio(enseigne, lib) if lib else 0
        )
    else:
        candidats["_score_nom"] = 50  # neutre si enseigne inconnue

    # On prend le candidat avec le meilleur score de nom
    meilleur_idx = candidats["_score_nom"].idxmax()
    meilleur     = candidats.loc[meilleur_idx]
    score_nom    = int(meilleur["_score_nom"])

    # --- Détermination du statut ---
    if ecart_montant or ecart_date :
        statut = "⚠️ Écart"
    else:
        statut = "✅ Trouvé"

    return {
        "statut":          statut,
        "releve_date":     meilleur["_date"].strftime("%d/%m/%Y") if meilleur["_date"] else "",
        "releve_libelle":  str(meilleur["_libelle"]),
        "releve_montant":  meilleur["_montant"],
        "score_nom":       score_nom,
    }
