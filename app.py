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
    CONTREPARTIES_STANDARD,
    COULEURS_PALIERS,
    DEFAULT_MODEL,
    build_pdf,
    charger_temoignages,
    contenu_depuis_dict,
    generate_bilan_content,
    get_bilans_utilisateur,
    sauver_bilan_pour_utilisateur,
    sauver_temoignage,
    stats_depuis_dict,
    StatsReseauSocial,
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
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }

    .bandeau-hero {
        background: linear-gradient(135deg, #1E4D8C 0%, #16365F 100%);
        color: white;
        padding: 2rem 2.2rem;
        border-radius: 14px;
        margin-bottom: 1.6rem;
    }
    .bandeau-hero h1 { color: white; margin: 0 0 0.3rem 0; font-weight: 800; }
    .bandeau-hero p { color: #D7E3F2; margin: 0; font-size: 1.05rem; }

    .encart-fiscal {
        background-color: #EEF2F6; border-left: 4px solid #1E4D8C;
        padding: 0.9rem 1.1rem; border-radius: 4px; font-size: 0.85rem; color: #3A4550;
    }

    .carte-palier {
        border-radius: 12px;
        padding: 1.1rem 1.2rem;
        background: white;
        box-shadow: 0 2px 10px rgba(20, 30, 50, 0.08);
        height: 100%;
    }
    .carte-palier .badge {
        display: inline-block; font-size: 0.72rem; font-weight: 700;
        color: white; padding: 0.15rem 0.6rem; border-radius: 20px; margin-bottom: 0.5rem;
    }
    .carte-palier .montant { font-size: 1.6rem; font-weight: 800; color: #16365F; margin: 0.2rem 0 0.7rem 0; }
    .carte-palier ul { margin: 0; padding-left: 1.1rem; }
    .carte-palier li { margin-bottom: 0.3rem; font-size: 0.92rem; color: #3A4550; }
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
if "photo_courante" not in st.session_state:
    st.session_state.photo_courante = None
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

st.markdown(
    """
    <div class="bandeau-hero">
        <h1>🏆 Bilan de Valeur</h1>
        <p>Transformez votre profil sportif en dossier de sponsoring professionnel,
        prêt à envoyer, en quelques secondes.</p>
    </div>
    """,
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
            ville = st.text_input("Ville / région", placeholder="ex : Lyon, Auvergne-Rhône-Alpes")
            contact = st.text_input("Téléphone / autre contact à afficher sur le PDF (optionnel)")

        palmares = st.text_area(
            "Palmarès et résultats principaux *",
            placeholder="ex : Championne de France 2025, 4e aux championnats d'Europe 2026...",
        )

        st.markdown("**Concrètement, que fais-tu en échange de leur soutien ?**")
        contreparties_choisies = st.multiselect(
            "Sélectionnez ce que vous êtes prêt à offrir (l'IA ne proposera que ces contreparties)",
            options=CONTREPARTIES_STANDARD,
            label_visibility="collapsed",
        )
        contrepartie_autre = st.text_input("Autre (optionnel)", placeholder="ex : dédicace de matériel, cours privé...")

        st.markdown("**Audience réseaux sociaux (optionnel)**")
        col3, col4, col5 = st.columns(3)
        with col3:
            reseau_social = st.selectbox(
                "Réseau principal", ["", "Instagram", "TikTok", "YouTube", "Strava", "X / Twitter", "Autre"]
            )
        with col4:
            abonnes_manuel = st.number_input("Nombre d'abonnés", min_value=0, step=100, value=0)
        with col5:
            likes_manuel = st.number_input("Moyenne de likes / publication", min_value=0, step=10, value=0)

        photo = st.file_uploader(
            "Photo (portrait ou action) — apparaîtra sur votre dossier PDF",
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
            if reseau_social and abonnes_manuel:
                stats = StatsReseauSocial(
                    plateforme=reseau_social, abonnes=int(abonnes_manuel), moyenne_likes=int(likes_manuel)
                )

            photo_bytes = photo.read() if photo is not None else None

            contreparties_disponibles = list(contreparties_choisies)
            if contrepartie_autre.strip():
                contreparties_disponibles.append(contrepartie_autre.strip())

            profil = {
                "nom": nom,
                "sport": sport,
                "niveau": niveau,
                "ville": ville,
                "palmares": palmares,
                "objectif": objectif,
                "contact": contact or email_compte,
                "abonnes": stats.abonnes if stats else None,
                "contreparties_disponibles": contreparties_disponibles,
            }

            with st.spinner("Rédaction de votre Bilan de Valeur par l'IA…"):
                contenu = generate_bilan_content(profil, api_key, modele)

            if contenu.erreur:
                st.error(f"Erreur lors de la génération : {contenu.erreur}")
            else:
                st.session_state.contenu_genere = contenu
                st.session_state.stats_extraites = stats
                st.session_state.profil_courant = profil
                st.session_state.photo_courante = photo_bytes
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
            noms_medailles = ["🥉 Bronze", "🥈 Argent", "🥇 Or"]
            cols_paliers = st.columns(len(contenu.paliers))
            for i, (col, p) in enumerate(zip(cols_paliers, contenu.paliers)):
                couleur = COULEURS_PALIERS[i % len(COULEURS_PALIERS)]
                badge = noms_medailles[i] if i < len(noms_medailles) else f"Palier {i+1}"
                contreparties_html = "".join(f"<li>{c}</li>" for c in p.get("contreparties", []))
                montant = f"{int(p.get('montant_eur', 0)):,}".replace(",", " ")
                with col:
                    st.markdown(
                        f"""
                        <div class="carte-palier">
                            <span class="badge" style="background-color:{couleur};">{badge}</span>
                            <div style="font-weight:700; color:#20272A;">{p.get('nom', '')}</div>
                            <div class="montant">{montant} €</div>
                            <ul>{contreparties_html}</ul>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

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
                avertissement = build_pdf(
                    profil, stats, contenu, pdf_path, photo_bytes=st.session_state.photo_courante
                )
                st.session_state.pdf_path = Path(pdf_path).read_bytes()
            if avertissement:
                st.warning(f"PDF généré, mais : {avertissement}")
            else:
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