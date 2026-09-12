"""
Bilan de Valeur - MVP hackathon
-------------------------------
Un athlète renseigne son profil (+ capture d'écran optionnelle de ses stats
réseaux sociaux) -> l'IA rédige un dossier de sponsoring professionnel ->
export PDF prêt à envoyer à des PME.

Lancer en local :
    python -m streamlit run app.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from utils import (
    DEFAULT_MODEL,
    build_pdf,
    charger_temoignages,
    contenu_depuis_dict,
    extract_social_stats,
    generate_bilan_content,
    get_bilans_utilisateur,
    sauver_bilan_pour_utilisateur,
    sauver_temoignage,
    stats_depuis_dict,
)

st.set_page_config(page_title="Bilan de Valeur", page_icon="🏆", layout="wide")


def _get_secret(key: str, default: str = "") -> str:
    """Lit st.secrets sans planter si aucun secrets.toml n'existe (cas normal
    en local, avant tout déploiement)."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


st.markdown(
    """
    <style>
    .sous-titre { color: #5B6672; font-size: 1.05rem; margin-top: -0.6rem; }
    .encart-fiscal {
        background-color: #EEF2F6; border-left: 4px solid #1E4D8C;
        padding: 0.9rem 1.1rem; border-radius: 4px; font-size: 0.85rem; color: #3A4550;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "contenu_genere" not in st.session_state:
    st.session_state.contenu_genere = None
if "stats_extraites" not in st.session_state:
    st.session_state.stats_extraites = None
if "profil_courant" not in st.session_state:
    st.session_state.profil_courant = None
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None

# ---------------------------------------------------------------------------
# Barre latérale
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Configuration")

    api_key = st.text_input(
        "Clé API Anthropic",
        type="password",
        value=_get_secret("ANTHROPIC_API_KEY"),
        help="Récupérable sur console.anthropic.com. Jamais stockée : elle ne vit que le "
        "temps de la session de votre navigateur.",
    )

    modele = st.selectbox(
        "Modèle",
        options=[DEFAULT_MODEL, "claude-haiku-4-5-20251001"],
        index=0,
    )

    st.divider()
    st.subheader("Débloquer votre PDF")
    lien_paiement = st.text_input(
        "Lien de paiement (Stripe / Lydia / PayPal)",
        placeholder="https://buy.stripe.com/...",
    )
    if lien_paiement:
        st.link_button("💳 Débloquer mon Bilan de Valeur (1-2€)", lien_paiement, use_container_width=True)
        st.caption("Une fois le paiement effectué, revenez ici et téléchargez votre PDF ci-dessous.")

    st.divider()
    with st.expander("💬 Laisser un retour (preuve de traction)"):
        nom_temoin = st.text_input("Prénom / discipline", key="nom_temoin")
        sport_temoin = st.text_input("Sport pratiqué", key="sport_temoin")
        avis_temoin = st.text_area("Votre retour", key="avis_temoin")
        if st.button("Envoyer le retour"):
            if avis_temoin.strip():
                sauver_temoignage(nom_temoin, sport_temoin, avis_temoin)
                st.success("Merci, votre retour est enregistré !")
            else:
                st.warning("Écrivez quelques mots avant d'envoyer.")

# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------

st.title("Bilan de Valeur")
st.markdown(
    '<p class="sous-titre">Transformez votre profil sportif en dossier de sponsoring '
    "professionnel, prêt à envoyer, en quelques secondes.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Identification du compte (email, sans mot de passe — voir README pour le
# choix de scope assumé)
# ---------------------------------------------------------------------------

email_compte = st.text_input(
    "📧 Votre email (sert d'identifiant de compte pour retrouver vos Bilans)",
    key="email_compte",
    placeholder="camille.dubois@email.com",
)

onglet_nouveau, onglet_historique = st.tabs(["🆕 Nouveau Bilan", "📂 Mes Bilans"])

# ---------------------------------------------------------------------------
# Onglet : nouveau Bilan
# ---------------------------------------------------------------------------

with onglet_nouveau:
    with st.form("formulaire_profil"):
        col1, col2 = st.columns(2)
        with col1:
            nom = st.text_input("Nom / prénom *")
            sport = st.text_input("Sport pratiqué *")
            niveau = st.selectbox(
                "Niveau", ["Régional", "National", "International", "Équipe de France", "Olympique"]
            )
        with col2:
            objectif = st.text_input("Objectif de financement", placeholder="ex : équipement, saison 2027, JO 2028")
            contact = st.text_input("Téléphone / autre contact à afficher sur le PDF (optionnel)")

        palmares = st.text_area(
            "Palmarès et résultats principaux *",
            placeholder="ex : Championne de France 2025, 4e aux championnats d'Europe 2026...",
        )

        capture_stats = st.file_uploader(
            "Capture d'écran de vos statistiques réseaux sociaux (optionnel)",
            type=["png", "jpg", "jpeg", "webp"],
        )

        valide = st.form_submit_button("Générer mon Bilan de Valeur", type="primary")

    if valide:
        if not email_compte.strip():
            st.error("Renseignez votre email au-dessus du formulaire : c'est ce qui vous permet de "
                      "retrouver vos Bilans dans l'onglet « Mes Bilans ».")
        elif not api_key:
            st.error("Renseignez votre clé API Anthropic dans la barre latérale.")
        elif not (nom and sport and palmares):
            st.error("Les champs marqués d'un * sont obligatoires.")
        else:
            stats = None
            if capture_stats is not None:
                with st.spinner("Lecture de vos statistiques réseaux sociaux…"):
                    stats = extract_social_stats(capture_stats.read(), capture_stats.name, api_key, modele)
                    if stats.erreur:
                        st.warning(f"Stats non lues ({stats.erreur}) — le bilan sera généré sans elles.")
                        stats = None

            profil = {
                "nom": nom,
                "sport": sport,
                "niveau": niveau,
                "palmares": palmares,
                "objectif": objectif,
                "contact": contact or email_compte,
                "abonnes": stats.abonnes if stats else None,
            }

            with st.spinner("Rédaction de votre Bilan de Valeur par l'IA…"):
                contenu = generate_bilan_content(profil, api_key, modele)

            if contenu.erreur:
                st.error(f"Erreur lors de la génération : {contenu.erreur}")
            else:
                st.session_state.contenu_genere = contenu
                st.session_state.stats_extraites = stats
                st.session_state.profil_courant = profil
                st.session_state.pdf_path = None
                sauver_bilan_pour_utilisateur(email_compte, profil, contenu, stats)
                st.toast("Bilan enregistré dans votre compte — retrouvez-le dans « Mes Bilans ».")

    # -----------------------------------------------------------------
    # Résultat + export PDF
    # -----------------------------------------------------------------

    if st.session_state.contenu_genere:
        contenu = st.session_state.contenu_genere
        stats = st.session_state.stats_extraites
        profil = st.session_state.profil_courant

        st.subheader("Aperçu de votre Bilan de Valeur")
        if contenu.accroche:
            st.markdown(f"*{contenu.accroche}*")
        st.write(contenu.paragraphe_profil)

        if stats and stats.abonnes:
            st.metric("Audience détectée", f"{stats.abonnes:,}".replace(",", " ") + f" ({stats.plateforme})")

        st.write("**Pourquoi s'associer à ce projet ?**")
        st.write(contenu.proposition_de_valeur)

        if contenu.paliers:
            st.write("**Paliers de partenariat proposés**")
            for p in contenu.paliers:
                with st.container(border=True):
                    st.markdown(f"**{p.get('nom', '')} — {int(p.get('montant_eur', 0)):,} €**".replace(",", " "))
                    for c in p.get("contreparties", []):
                        st.markdown(f"- {c}")

        st.markdown(
            '<div class="encart-fiscal">📋 Le document PDF inclut un encart sur le cadre fiscal du '
            "sponsoring (article 39 du CGI), avec la mention qu'il ne s'agit pas d'un conseil fiscal "
            "personnalisé.</div>",
            unsafe_allow_html=True,
        )

        st.divider()

        if st.button("📄 Générer le PDF"):
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = str(Path(tmp) / "bilan_de_valeur.pdf")
                build_pdf(profil, stats, contenu, pdf_path)
                st.session_state.pdf_path = Path(pdf_path).read_bytes()
            st.success("PDF généré !")

        if st.session_state.pdf_path:
            st.download_button(
                "⬇️ Télécharger mon Bilan de Valeur (PDF)",
                data=st.session_state.pdf_path,
                file_name=f"bilan_de_valeur_{profil['nom'].replace(' ', '_')}.pdf",
                mime="application/pdf",
            )
            if not lien_paiement:
                st.caption(
                    "💡 Astuce démo : ajoutez un lien de paiement dans la barre latérale pour proposer "
                    "le téléchargement contre une petite contribution."
                )

# ---------------------------------------------------------------------------
# Onglet : historique du compte
# ---------------------------------------------------------------------------

with onglet_historique:
    if not email_compte.strip():
        st.info("Renseignez votre email en haut de la page pour voir vos Bilans précédents.")
    else:
        historique = get_bilans_utilisateur(email_compte)
        if not historique:
            st.info("Aucun Bilan généré pour l'instant avec cet email.")
        else:
            st.caption(f"{len(historique)} Bilan(s) trouvé(s) pour {email_compte.strip().lower()}")
            for i, entree in enumerate(historique):
                profil_h = entree["profil"]
                with st.container(border=True):
                    col_info, col_bouton = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**{profil_h.get('nom', '')}** — {profil_h.get('sport', '')}")
                        st.caption(f"Généré le {entree['date']}")
                    with col_bouton:
                        contenu_h = contenu_depuis_dict(entree["contenu"])
                        stats_h = stats_depuis_dict(entree.get("stats"))
                        with tempfile.TemporaryDirectory() as tmp:
                            pdf_path = str(Path(tmp) / "bilan.pdf")
                            build_pdf(profil_h, stats_h, contenu_h, pdf_path)
                            pdf_bytes = Path(pdf_path).read_bytes()
                        st.download_button(
                            "⬇️ PDF",
                            data=pdf_bytes,
                            file_name=f"bilan_{profil_h.get('nom', 'athlete').replace(' ', '_')}_{i}.pdf",
                            mime="application/pdf",
                            key=f"dl_historique_{i}",
                        )
