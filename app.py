import io
import pandas as pd
import streamlit as st

from ocr import extraire_ticket
from utils import creer_dataframe_vide, ajouter_ligne, COLONNES_TICKETS

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
# Initialisation du session state
# ---------------------------------------------------------------------------

if "etape" not in st.session_state:
    st.session_state.etape = 1

if "df_tickets" not in st.session_state:
    st.session_state.df_tickets = creer_dataframe_vide()

if "fichiers_traites" not in st.session_state:
    st.session_state.fichiers_traites = set()


# ---------------------------------------------------------------------------
# Barre de progression des étapes
# ---------------------------------------------------------------------------

def afficher_etapes(etape_active: int):
    cols = st.columns(3)
    etapes = ["1 · Import & extraction", "2 · Vérification", "3 · Matching bancaire"]
    for i, (col, label) in enumerate(zip(cols, etapes), start=1):
        if i < etape_active:
            col.success(f"✓ {label}")
        elif i == etape_active:
            col.info(f"**{label}**")
        else:
            col.container().markdown(
                f"<div style='color:gray;padding:8px'>{label}</div>",
                unsafe_allow_html=True,
            )


afficher_etapes(st.session_state.etape)
st.divider()


# ---------------------------------------------------------------------------
# ÉTAPE 1 — Import et extraction OCR
# ---------------------------------------------------------------------------

if st.session_state.etape == 1:
    st.subheader("📷 Étape 1 — Importer vos photos de tickets")

    fichiers = st.file_uploader(
        "Sélectionne une ou plusieurs photos",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True,
    )

    if fichiers:
        nouveaux = [f for f in fichiers if f.name not in st.session_state.fichiers_traites]

        if nouveaux:
            st.info(f"{len(nouveaux)} nouveau(x) fichier(s) détecté(s). Lancement de l'extraction…")
            barre = st.progress(0, text="Démarrage…")

            for idx, fichier in enumerate(nouveaux):
                barre.progress(
                    int((idx / len(nouveaux)) * 100),
                    text=f"Analyse de {fichier.name}…",
                )
                image_bytes = fichier.read()
                col_img, col_res = st.columns([1, 2])
                with col_img:
                    st.image(fichier, caption=fichier.name, use_container_width=True)

                
                resultat = extraire_ticket(image_bytes, fichier.name)

                with col_res:
                    if "erreur" in resultat:
                        st.error(f"❌ {resultat['erreur']}")
                    else:
                        st.success("✅ Extraction réussie")
                        st.json({
                            "enseigne": resultat.get("enseigne"),
                            "montant":  resultat.get("montant"),
                            "date":     resultat.get("date"),
                        })
                        st.session_state.df_tickets = ajouter_ligne(
                            st.session_state.df_tickets, resultat
                        )
                        st.session_state.fichiers_traites.add(fichier.name)

            barre.progress(100, text="Extraction terminée ✓")

        else:
            st.success(f"✅ {len(fichiers)} fichier(s) déjà traité(s).")

        if not st.session_state.df_tickets.empty:
            st.divider()
            st.markdown(f"**{len(st.session_state.df_tickets)} ligne(s) extraite(s) au total**")
            st.dataframe(st.session_state.df_tickets, use_container_width=True)

            if st.button("Passer à la vérification →", type="primary"):
                st.session_state.etape = 2
                st.rerun()
    else:
        st.session_state.fichiers_traites = set()
        st.session_state.df_tickets = creer_dataframe_vide()


# ---------------------------------------------------------------------------
# ÉTAPE 2 — Vérification et export CSV
# ---------------------------------------------------------------------------

elif st.session_state.etape == 2:
    st.subheader("✏️ Étape 2 — Vérifier et corriger les données")

    if st.session_state.df_tickets.empty:
        st.warning("Aucune donnée à afficher. Retourne à l'étape 1.")
        if st.button("← Retour"):
            st.session_state.etape = 1
            st.rerun()
    else:
        st.caption("Clique directement sur une cellule pour modifier sa valeur.")

        df_edite = st.data_editor(
            st.session_state.df_tickets,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "fichier":  st.column_config.TextColumn("Fichier", disabled=True),
                "enseigne": st.column_config.TextColumn("Enseigne"),
                "montant":  st.column_config.NumberColumn("Montant (€)", format="%.2f"),
                "date":     st.column_config.TextColumn("Date (JJ/MM/AAAA)"),
            },
            key="editeur_tickets",
        )
        st.session_state.df_tickets = df_edite

        st.divider()
        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            if st.button("← Retour à l'import"):
                st.session_state.etape = 1
                st.rerun()

        with col2:
            csv_bytes = df_edite.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
            st.download_button(
                label="⬇️ Exporter le CSV",
                data=csv_bytes,
                file_name="tickets_extraits.csv",
                mime="text/csv",
            )

        with col3:
            if st.button("Passer au matching →", type="primary"):
                st.session_state.etape = 3
                st.rerun()


# ---------------------------------------------------------------------------
# ÉTAPE 3 — Matching bancaire
# ---------------------------------------------------------------------------

elif st.session_state.etape == 3:
    from matcher import effectuer_matching
    from utils import detecter_colonnes

    st.subheader("🏦 Étape 3 — Rapprochement avec le relevé bancaire")

    fichier_releve = st.file_uploader(
        "Importe le CSV de ton relevé bancaire",
        type=["csv"],
        key="releve",
    )

    if fichier_releve:
        # Lecture du relevé avec détection automatique du séparateur
        df_releve = None
        try:
            contenu = fichier_releve.read()
            for sep in [";", ",", "\t", "|"]:
                for enc in ["utf-8-sig", "latin-1", "cp1252", "utf-8"]:
                    try:
                        df_tmp = pd.read_csv(io.BytesIO(contenu), sep=sep, encoding=enc)
                        if len(df_tmp.columns) > 1:
                            df_releve = df_tmp  # ← ligne manquante
                            break
                    except Exception:
                        continue
                if df_releve is not None:
                    break
        except Exception as e:
            st.error(f"Impossible de lire le fichier : {e}")
            st.stop()
        
        if df_releve is None:
            st.error("Impossible de détéceter le séparateur du fichier CSV.")
            st.stop()

        st.success(f"✅ Relevé chargé — {len(df_releve)} lignes, {len(df_releve.columns)} colonnes")

        # Détection automatique des colonnes
        colonnes_auto = detecter_colonnes(df_releve)

        st.markdown("**Correspondance des colonnes** — vérifie ou corrige :")
        col1, col2, col3 = st.columns(3)

        with col1:
            col_date = st.selectbox(
                "Colonne DATE",
                df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["date"])
                if colonnes_auto["date"] in df_releve.columns else 0,
            )
        with col2:
            col_montant = st.selectbox(
                "Colonne MONTANT",
                df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["montant"])
                if colonnes_auto["montant"] in df_releve.columns else 0,
            )
        with col3:
            col_libelle = st.selectbox(
                "Colonne LIBELLÉ",
                df_releve.columns,
                index=list(df_releve.columns).index(colonnes_auto["libelle"])
                if colonnes_auto["libelle"] in df_releve.columns else 0,
            )

        st.divider()

        # Paramètres de tolérance
        with st.expander("⚙️ Paramètres de matching"):
            tolerance_montant = st.slider(
                "Tolérance montant (€)", 0.0, 2.0, 0.02, 0.01,
                help="Écart maximum autorisé entre le montant du ticket et celui du relevé"
            )
            tolerance_jours = st.slider(
                "Tolérance date (jours)", 0, 10, 3,
                help="Écart maximum en jours entre la date du ticket et celle du relevé"
            )

        if st.button("🔍 Lancer le matching", type="primary"):
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

            # Affichage des métriques
            n_total   = len(df_resultat)
            n_trouve  = (df_resultat["statut"] == "✅ Trouvé").sum()
            n_ecart   = (df_resultat["statut"] == "⚠️ Écart").sum()
            n_absent  = (df_resultat["statut"] == "❌ Non trouvé").sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total tickets", n_total)
            m2.metric("✅ Trouvés",    n_trouve)
            m3.metric("⚠️ Écarts",     n_ecart)
            m4.metric("❌ Non trouvés", n_absent)

            st.divider()

            # Coloration par statut
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

            # Export
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
