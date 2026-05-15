import io
import json
import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import fitz
from PIL import Image

from ocr import extraire_ticket, diagnostiquer_gpu
from utils import creer_dataframe_vide, ajouter_ligne, COLONNES_TICKETS

# ---------------------------------------------------------------------------
# Cache disque — dossier créé à côté de app.py
# ---------------------------------------------------------------------------

CACHE_DIR = Path("cache_ocr")
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(nom_fichier: str) -> Path:
    """Chemin du JSON de cache pour un fichier donné."""
    safe = re.sub(r"[^\w.\-]", "_", Path(nom_fichier).name)
    return CACHE_DIR / f"{safe}.json"


def charger_cache() -> tuple[pd.DataFrame, set]:
    """
    Lit tous les JSON du dossier cache et reconstruit le DataFrame tickets.
    Retourne (df_tickets, fichiers_traites).
    """
    import re
    df = creer_dataframe_vide()
    traites = set()
    for fichier_json in sorted(CACHE_DIR.glob("*.json")):
        try:
            data = json.loads(fichier_json.read_text(encoding="utf-8"))
            df = ajouter_ligne(df, data)
            traites.add(data.get("fichier", ""))
        except Exception:
            pass
    return df, traites


def sauvegarder_resultat(resultat: dict) -> None:
    """Écrit le résultat OCR d'un fichier dans le cache disque."""
    import re
    if not resultat.get("fichier"):
        return
    chemin = _cache_path(resultat["fichier"])
    chemin.write_text(
        json.dumps(resultat, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def supprimer_cache() -> int:
    """Supprime tous les JSON du cache. Retourne le nombre de fichiers supprimés."""
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count


import re  # nécessaire pour _cache_path avant l'import conditionnel

# ---------------------------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Ticket Matcher",
    page_icon="🧾",
    layout="wide",
)

st.title("🧾 Ticket Matcher")
st.caption("Extraction automatique de tickets · Vérification · Rapprochement bancaire")

# ---------------------------------------------------------------------------
# Initialisation du session state — chargement du cache au premier démarrage
# ---------------------------------------------------------------------------

if "etape" not in st.session_state:
    st.session_state.etape = 1

if "cache_charge" not in st.session_state:
    # Premier chargement : on lit le cache disque
    df_cache, traites_cache = charger_cache()
    st.session_state.df_tickets = df_cache
    st.session_state.fichiers_traites = traites_cache
    st.session_state.cache_charge = True

if "logs" not in st.session_state:
    st.session_state.logs = []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(message: str, niveau: str = "INFO"):
    horodatage = datetime.datetime.now().strftime("%H:%M:%S")
    icone = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌"}.get(niveau, "▪️")
    ligne = f"`{horodatage}` {icone} {message}"
    st.session_state.logs.append(ligne)
    print(f"[{horodatage}] [{niveau}] {message}")


# ---------------------------------------------------------------------------
# Sidebar — logs + GPU status + cache
# ---------------------------------------------------------------------------

with st.sidebar:

    # ── GPU status ──────────────────────────────────────────────────────────
    st.markdown("### 🖥️ GPU")
    if st.button("🔍 Vérifier GPU", use_container_width=True):
        with st.spinner("Diagnostic en cours…"):
            diag = diagnostiquer_gpu()
        st.session_state["diag_gpu"] = diag

    diag = st.session_state.get("diag_gpu")
    if diag:
        if diag["nvidia_ok"]:
            st.success(f"NVIDIA détecté\n{diag['nvidia_info']}")
        else:
            st.error("nvidia-smi introuvable → CPU probable")

        if diag["ollama_info"]:
            if diag["ollama_gpu"]:
                st.success(f"🟢 GPU actif\n{diag['ollama_info']}")
            else:
                st.warning(f"🟡 {diag['ollama_info']}")

        if diag["avertissement"]:
            st.error(diag["avertissement"])
    else:
        st.caption("Clique pour vérifier si Ollama utilise le GPU.")

    st.divider()

    # ── Cache disque ────────────────────────────────────────────────────────
    st.markdown("### 💾 Cache OCR")
    nb_cache = len(list(CACHE_DIR.glob("*.json")))
    st.caption(f"{nb_cache} fichier(s) en cache dans `{CACHE_DIR}/`")

    if nb_cache > 0 and st.button("🗑️ Vider le cache", use_container_width=True):
        n = supprimer_cache()
        st.session_state.df_tickets = creer_dataframe_vide()
        st.session_state.fichiers_traites = set()
        log(f"Cache vidé — {n} fichier(s) supprimé(s)", "WARN")
        st.rerun()

    st.divider()

    # ── Logs ────────────────────────────────────────────────────────────────
    st.markdown("### 🪵 Logs")
    if st.button("🗑️ Effacer les logs", use_container_width=True):
        st.session_state.logs = []
    with st.expander("Afficher les logs", expanded=True):
        if st.session_state.logs:
            for ligne in reversed(st.session_state.logs):
                st.markdown(ligne)
        else:
            st.caption("Aucun log pour l'instant.")


# ---------------------------------------------------------------------------
# Barre de navigation par étapes
# ---------------------------------------------------------------------------

def afficher_etapes(etape_active: int):
    etapes = ["1 · Import & extraction", "2 · Vérification", "3 · Matching bancaire"]
    icones = ["📷", "✏️", "🏦"]
    cols = st.columns(3)
    for i, (col, label, icone) in enumerate(zip(cols, etapes, icones), start=1):
        if i == etape_active:
            col.info(f"**{icone} {label}**")
        else:
            prefixe = "✓ " if i < etape_active else ""
            if col.button(f"{prefixe}{icone} {label}", key=f"nav_etape_{i}",
                          use_container_width=True):
                st.session_state.etape = i
                st.rerun()


afficher_etapes(st.session_state.etape)
st.divider()


# ---------------------------------------------------------------------------
# ÉTAPE 1 — Import et extraction OCR
# ---------------------------------------------------------------------------

if st.session_state.etape == 1:
    st.subheader("📷 Étape 1 — Importer vos photos de tickets")

    # ── Résumé du cache existant ────────────────────────────────────────────
    nb_deja = len(st.session_state.df_tickets)
    if nb_deja > 0:
        st.success(
            f"💾 **{nb_deja} ticket(s) déjà en cache** — ils seront inclus automatiquement. "
            f"Tu peux ajouter de nouveaux fichiers ou passer directement à l'étape 2."
        )
        st.dataframe(st.session_state.df_tickets, use_container_width=True)
        st.divider()

    fichiers = st.file_uploader(
        "Importer un ou plusieurs fichiers",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
    )

    if fichiers:
        nouveaux = [f for f in fichiers
                    if f.name not in st.session_state.fichiers_traites]

        if nouveaux:
            st.info(
                f"{len(nouveaux)} nouveau(x) fichier(s) détecté(s) sur {len(fichiers)} importé(s). "
                f"Lancement de l'extraction…"
            )
            barre = st.progress(0, text="Démarrage…")
            log(f"Extraction démarrée — {len(nouveaux)} fichier(s)")

            for idx, fichier in enumerate(nouveaux):
                barre.progress(
                    int((idx / len(nouveaux)) * 100),
                    text=f"[{idx+1}/{len(nouveaux)}] Analyse de {fichier.name}…",
                )
                log(f"[{idx+1}/{len(nouveaux)}] Début OCR : {fichier.name}")

                raw_bytes = fichier.read()
                col_img, col_res = st.columns([1, 2])

                # ── Prépare les bytes OCR ET l'affichage en une seule passe ──
                if fichier.type == "application/pdf":
                    doc = fitz.open(stream=raw_bytes, filetype="pdf")
                    pages_img = []
                    for page in doc:
                        # 1.5x suffit pour l'affichage, économise mémoire vs 2x
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        pages_img.append(
                            Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        )
                    # Page 1 en 2x pour l'OCR (meilleure résolution pour le modèle)
                    pix_ocr = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_ocr = Image.frombytes("RGB", [pix_ocr.width, pix_ocr.height],
                                             pix_ocr.samples)
                    buf = io.BytesIO()
                    img_ocr.save(buf, format="PNG")
                    image_for_ocr = buf.getvalue()
                    doc.close()

                    with col_img:
                        for i, img in enumerate(pages_img):
                            st.image(img, caption=f"{fichier.name} — p.{i+1}",
                                     use_container_width=True)
                else:
                    image_for_ocr = raw_bytes
                    with col_img:
                        st.image(raw_bytes, caption=fichier.name, use_container_width=True)

                resultat = extraire_ticket(image_for_ocr, fichier.name)

                with col_res:
                    if "erreur" in resultat:
                        st.error(f"❌ {resultat['erreur']}")
                        log(f"Erreur OCR sur {fichier.name} : {resultat['erreur']}", "ERR")
                    else:
                        # ── Sauvegarde immédiate sur disque ──────────────────
                        sauvegarder_resultat(resultat)

                        st.session_state.df_tickets = ajouter_ligne(
                            st.session_state.df_tickets, resultat
                        )
                        st.session_state.fichiers_traites.add(fichier.name)

                        st.success("✅ Extraction réussie — sauvegardée en cache")
                        log(
                            f"OCR OK : {fichier.name} → "
                            f"{resultat.get('enseigne')} | {resultat.get('montant')}€ | "
                            f"{resultat.get('date')}",
                            "OK",
                        )
                        st.json({
                            "enseigne": resultat.get("enseigne"),
                            "montant":  resultat.get("montant"),
                            "tva":      resultat.get("tva"),
                            "date":     resultat.get("date"),
                        })

            barre.progress(100, text="Extraction terminée ✓")
            log(
                f"Extraction terminée — {len(st.session_state.df_tickets)} ligne(s) au total",
                "OK",
            )

        else:
            st.success(f"✅ Tous les fichiers importés sont déjà en cache.")

        if not st.session_state.df_tickets.empty:
            st.divider()
            st.markdown(f"**{len(st.session_state.df_tickets)} ligne(s) extraite(s) au total**")
            if nouveaux:
                st.dataframe(st.session_state.df_tickets, use_container_width=True)
            if st.button("Passer à la vérification →", type="primary"):
                st.session_state.etape = 2
                st.rerun()

    elif nb_deja == 0:
        # Aucun fichier uploadé et cache vide
        st.session_state.fichiers_traites = set()
        st.session_state.df_tickets = creer_dataframe_vide()


# ---------------------------------------------------------------------------
# ÉTAPE 2 — Import CSV + mapping colonnes
# ---------------------------------------------------------------------------

if st.session_state.etape == 2:
    st.subheader("✏️ Étape 2 — Importer le CSV et choisir les colonnes")

    csv_upload = st.file_uploader("Importer un CSV", type=["csv"], key="csv_etape2")

    if csv_upload is not None:
        df = pd.read_csv(csv_upload, sep=None, engine="python", encoding_errors="replace")
        st.session_state.df_csv_brut = df
        log(f"CSV chargé : {len(df)} lignes, colonnes = {list(df.columns)}", "OK")

    df = st.session_state.get("df_csv_brut")

    if df is not None:
        st.markdown(f"**Colonnes détectées :** `{list(df.columns)}`")
        st.dataframe(df.head(5), use_container_width=True)

        st.divider()
        st.markdown("**Faire correspondre les colonnes :**")
        cols = ["— aucune —"] + list(df.columns)
        c1, c2, c3, c4 = st.columns(4)
        col_fichier  = c1.selectbox("Fichier",   cols, key="col_fichier")
        col_enseigne = c2.selectbox("Enseigne",  cols, key="col_enseigne")
        col_montant  = c3.selectbox("Montant",   cols, key="col_montant")
        col_date     = c4.selectbox("Date",      cols, key="col_date")

        if st.button("✅ Valider et continuer →", type="primary"):
            mapping = {
                "fichier":  col_fichier,
                "enseigne": col_enseigne,
                "montant":  col_montant,
                "date":     col_date,
            }
            # On garde seulement les colonnes mappées (ignore "— aucune —")
            df_final = pd.DataFrame()
            for cible, source in mapping.items():
                if source != "— aucune —":
                    df_final[cible] = df[source]
                else:
                    df_final[cible] = None

            st.session_state.df_tickets = df_final
            log(f"Mapping validé : {mapping}", "OK")
            st.session_state.etape = 3
            st.rerun()

    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("← Retour à l'import"):
            st.session_state.etape = 1
            st.rerun()


# ---------------------------------------------------------------------------
# ÉTAPE 3 — Matching bancaire
# ---------------------------------------------------------------------------

if st.session_state.etape == 3:
    from matcher import effectuer_matching
    from utils import detecter_colonnes

    st.subheader("🏦 Étape 3 — Rapprochement avec le relevé bancaire")

    fichier_releve = st.file_uploader(
        "Importe le CSV de ton relevé bancaire",
        type=["csv"],
        key="releve",
    )

    if fichier_releve:
        df_releve = None
        try:
            contenu = fichier_releve.read()
            for sep in [";", ",", "\t", "|"]:
                for enc in ["utf-8-sig", "latin-1", "cp1252", "utf-8"]:
                    try:
                        df_tmp = pd.read_csv(
                            io.BytesIO(contenu), sep=sep, encoding=enc
                        )
                        if len(df_tmp.columns) > 1:
                            df_releve = df_tmp
                            break
                    except Exception:
                        continue
                if df_releve is not None:
                    break
        except Exception as e:
            st.error(f"Impossible de lire le fichier : {e}")
            st.stop()

        if df_releve is None:
            st.error("Impossible de détecter le séparateur du fichier CSV.")
            st.stop()

        st.success(
            f"✅ Relevé chargé — {len(df_releve)} lignes, {len(df_releve.columns)} colonnes"
        )

        colonnes_auto = detecter_colonnes(df_releve)

        st.markdown("**Correspondance des colonnes** — vérifie ou corrige :")
        col1, col2, col3 = st.columns(3)

        with col1:
            col_date = st.selectbox(
                "Colonne DATE", df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["date"])
                if colonnes_auto["date"] in df_releve.columns else 0,
            )
        with col2:
            col_montant = st.selectbox(
                "Colonne MONTANT", df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["montant"])
                if colonnes_auto["montant"] in df_releve.columns else 0,
            )
        with col3:
            col_libelle = st.selectbox(
                "Colonne LIBELLÉ", df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["libelle"])
                if colonnes_auto["libelle"] in df_releve.columns else 0,
            )

        st.divider()

        with st.expander("⚙️ Paramètres de matching"):
            tolerance_montant = st.slider(
                "Tolérance montant (€)", 0.0, 2.0, 0.02, 0.01,
            )
            tolerance_jours = st.slider(
                "Tolérance date (jours)", 0, 10, 3,
            )

        m1, m2, m3, m4 = st.columns(4)

        if st.button("🔍 Lancer le matching", type="primary"):
            log(
                f"Matching lancé — {len(st.session_state.df_tickets)} tickets "
                f"vs {len(df_releve)} lignes relevé"
            )
            with st.spinner("Rapprochement en cours…"):
                df_resultat = effectuer_matching(
                    df_tickets=st.session_state.df_tickets,
                    df_releve=df_releve,
                    col_date=col_date,
                    col_montant=col_montant,
                    col_libelle=col_libelle,
                    tolerance_montant=tolerance_montant,
                    tolerance_jours=tolerance_jours,
                    seuil_nom=0,
                )

            n_total  = len(df_resultat)
            n_trouve = (df_resultat["statut"] == "✅ Trouvé").sum()
            n_ecart  = (df_resultat["statut"] == "⚠️ Écart").sum()
            n_absent = (df_resultat["statut"] == "❌ Non trouvé").sum()

            log(
                f"Matching terminé — ✅ {n_trouve} trouvés | ⚠️ {n_ecart} écarts "
                f"| ❌ {n_absent} non trouvés",
                "OK",
            )
            m1.metric("Total tickets", n_total)
            m2.metric("✅ Trouvés",    n_trouve)
            m3.metric("⚠️ Écarts",     n_ecart)
            m4.metric("❌ Non trouvés", n_absent)

            st.divider()

            def coloriser(row):
                couleurs = {
                    "✅ Trouvé":     "background-color: #EAF3DE",
                    "⚠️ Écart":      "background-color: #FAEEDA",
                    "❌ Non trouvé": "background-color: #FCEBEB",
                }
                return [couleurs.get(row["statut"], "")] * len(row)

            st.dataframe(
                df_resultat.style.apply(coloriser, axis=1),
                use_container_width=True,
            )

            st.divider()
            col_a, col_b = st.columns(2)

            with col_a:
                csv_out = df_resultat.to_csv(
                    index=False, sep=";", decimal=","
                ).encode("utf-8-sig")
                st.download_button(
                    "⬇️ Exporter rapport CSV",
                    data=csv_out,
                    file_name="rapport_matching.csv",
                    mime="text/csv",
                )

            with col_b:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_resultat.to_excel(writer, index=False, sheet_name="Matching")
                st.download_button(
                    "⬇️ Exporter rapport Excel",
                    data=buffer.getvalue(),
                    file_name="rapport_matching.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    st.divider()
    if st.button("← Retour à la vérification"):
        st.session_state.etape = 2
        st.rerun()
