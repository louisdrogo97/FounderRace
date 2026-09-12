"""
Pack Sponsoring - MVP hackathon
-------------------------------
Un athlète renseigne son profil (+ capture d'écran optionnelle de ses stats
réseaux sociaux) -> l'IA rédige un dossier de sponsoring professionnel ->
export PDF prêt à envoyer à des PME.

Lancer en local :
    python -m streamlit run app.py
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import streamlit as st

from utils import (
    CONTREPARTIES_STANDARD,
    COULEURS_PALIERS,
    DEFAULT_MODEL,
    NOM_PRODUIT,
    build_pdf,
    charger_photo,
    charger_temoignages,
    contenu_depuis_dict,
    envoyer_bilan_par_email,
    generate_bilan_content,
    get_bilans_utilisateur,
    get_tous_les_profils,
    sauver_bilan_pour_utilisateur,
    sauver_temoignage,
    stats_liste_depuis_dict,
    StatsReseauSocial,
    generer_plan_prospection,
    build_pdf_prospection,
)

st.set_page_config(page_title=NOM_PRODUIT, page_icon="🏆", layout="wide")

OPTIONS_RESEAUX = ["", "Instagram", "TikTok", "YouTube", "Strava", "X / Twitter", "Autre"]


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

    /* Fond global */
    .stApp { background-color: #FAFAFA !important; }

    /* Barre latérale claire et lisible */
    [data-testid="stSidebar"] {
        background-color: #F1F5F9 !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h3 {
        color: #1E293B !important;
    }

    /* Textes globaux */
    .stApp p, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp li {
        color: #1E293B !important;
    }

    /* Champs de saisie globaux (inputs, textareas, selects) */
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div,
    [data-testid="stSidebar"] div[data-baseweb="input"] > div,
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 6px !important;
    }

    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] div {
        color: #0F172A !important;
        -webkit-text-fill-color: #0F172A !important;
        background-color: transparent !important;
    }

    /* Cartes Athlète (Correction du texte invisible blanc sur blanc) */
    .carte-palier, .carte-athlete {
        border-radius: 12px;
        background: #FFFFFF !important;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
    }
    .carte-palier { padding: 1.2rem; height: 100%; }
    .carte-athlete { padding: 1.2rem 1rem; text-align: center; margin-bottom: 0.6rem; }

    /* Forcer le texte des cartes athlètes en noir foncé */
    .carte-athlete p, .carte-athlete div, .carte-athlete span {
        color: #0F172A !important;
    }

    .carte-athlete img {
        width: 120px; height: 120px; border-radius: 50%; object-fit: cover;
        margin-bottom: 0.6rem; border: 3px solid #E2E8F0;
    }
    .carte-athlete .photo-vide {
        width: 120px; height: 120px; border-radius: 50%; background: #F1F5F9;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 0.6rem auto; font-size: 1.8rem; color: #64748B !important;
    }

    /* Cartes "Comment ça marche" */
    .carte-etape {
        border-radius: 12px;
        background: #FFFFFF !important;
        border: 1px solid #E2E8F0;
        padding: 1.2rem;
        height: 100%;
    }
    .carte-etape .numero {
        display: inline-flex; align-items: center; justify-content: center;
        width: 28px; height: 28px; border-radius: 50%;
        background: #1E4D8C; color: #FFFFFF !important; font-weight: 700;
        margin-bottom: 0.5rem;
    }

    /* Encart d'information fiscale */
    .encart-fiscal {
        background: #EEF2F6;
        border-left: 4px solid #1E4D8C;
        border-radius: 6px;
        padding: 0.8rem 1rem;
        color: #1E293B !important;
        font-size: 0.9rem;
        line-height: 1.5;
    }

    /* Boutons secondaires (fond blanc) : texte foncé lisible */
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-secondaryFormSubmit"] {
        color: #1E293B !important;
    }
    button[data-testid="stBaseButton-secondary"] p,
    button[data-testid="stBaseButton-secondary"] div,
    button[data-testid="stBaseButton-secondaryFormSubmit"] p,
    button[data-testid="stBaseButton-secondaryFormSubmit"] div {
        color: #1E293B !important;
        -webkit-text-fill-color: #1E293B !important;
    }

    /* Boutons primaires (fond coloré) : texte blanc lisible */
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        color: #FFFFFF !important;
    }
    button[data-testid="stBaseButton-primary"] p,
    button[data-testid="stBaseButton-primary"] div,
    button[data-testid="stBaseButton-primaryFormSubmit"] p,
    button[data-testid="stBaseButton-primaryFormSubmit"] div {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
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
if "photo_courante" not in st.session_state:
    st.session_state.photo_courante = None
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None
if "reseaux_ids" not in st.session_state:
    st.session_state.reseaux_ids = [0]
    st.session_state.reseaux_next_id = 1

# ---------------------------------------------------------------------------
# Barre latérale : navigation + configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    page = st.radio(
        "Navigation",
        ["🏠 Découvrir les athlètes", "🆕 Nouveau Pack", "📂 Mes Packs"],
        label_visibility="collapsed",
    )

    st.divider()

    # En déploiement, les clés/identifiants sont fournis via les secrets Streamlit : on ne montre
    # les champs de configuration que si un secret manque (usage local / première installation).
    api_key_secret = _get_secret("ANTHROPIC_API_KEY")
    tavily_key_secret = _get_secret("TAVILY_API_KEY")
    email_expediteur_secret = _get_secret("EMAIL_EXPEDITEUR")
    email_mdp_app_secret = _get_secret("EMAIL_MOT_DE_PASSE")

    if api_key_secret and tavily_key_secret and email_expediteur_secret and email_mdp_app_secret:
        api_key = api_key_secret
        tavily_key = tavily_key_secret
        email_expediteur = email_expediteur_secret
        email_mdp_app = email_mdp_app_secret
        modele = DEFAULT_MODEL
    else:
        st.header("Configuration")

        api_key = st.text_input(
            "Clé API Anthropic",
            type="password",
            value=api_key_secret,
            help="Récupérable sur console.anthropic.com. Pré-remplie automatiquement si présente dans "
            "les secrets Streamlit, sinon collez-la ici.",
        )
        tavily_key = st.text_input(
            "Clé API Tavily (recherche web, optionnelle)",
            type="password",
            value=tavily_key_secret,
            help="Nécessaire uniquement pour « Générer vos cibles de prospection ». Récupérable sur "
            "tavily.com.",
        )

        modele = st.selectbox(
            "Modèle",
            options=[DEFAULT_MODEL, "claude-haiku-4-5-20251001"],
            index=0,
        )

        with st.expander("📤 Configuration envoi par email"):
            st.caption("Compte email utilisé pour vous envoyer les Packs Sponsoring générés (ex: un Gmail avec un "
                       "« mot de passe d'application », voir myaccount.google.com/apppasswords).")
            email_expediteur = st.text_input(
                "Email expéditeur", value=email_expediteur_secret, key="email_expediteur"
            )
            email_mdp_app = st.text_input(
                "Mot de passe d'application", type="password",
                value=email_mdp_app_secret, key="email_mdp_app",
            )

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
    f"""
    <div class="bandeau-hero">
        <h1>🏆 {NOM_PRODUIT}</h1>
        <p>Transformez votre profil sportif en dossier de sponsoring professionnel,
        prêt à envoyer, en quelques secondes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown("#### Comment ça marche ?")
    c_etape1, c_etape2, c_etape3 = st.columns(3)
    with c_etape1:
        st.markdown(
            """<div class="carte-etape"><div class="numero">1</div>
            <b>Renseignez votre profil</b><br>Sport, palmarès, objectifs et audience sur vos réseaux
            sociaux.</div>""",
            unsafe_allow_html=True,
        )
    with c_etape2:
        st.markdown(
            """<div class="carte-etape"><div class="numero">2</div>
            <b>L'IA rédige votre dossier</b><br>Un pitch professionnel et des paliers de partenariat
            calibrés à votre profil.</div>""",
            unsafe_allow_html=True,
        )
    with c_etape3:
        st.markdown(
            """<div class="carte-etape"><div class="numero">3</div>
            <b>Téléchargez et envoyez</b><br>Un PDF prêt pour vos sponsors, et une liste d'entreprises
            locales à contacter.</div>""",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Identification du compte (email, sans mot de passe — voir README pour le
# choix de scope assumé)
# ---------------------------------------------------------------------------

email_compte = st.text_input(
    "📧 Votre email (sert d'identifiant de compte pour retrouver vos Packs)",
    key="email_compte",
    placeholder="camille.dubois@email.com",
)

# ---------------------------------------------------------------------------
# Page : galerie de tous les profils inscrits
# ---------------------------------------------------------------------------

if page == "🏠 Découvrir les athlètes":
    profils = get_tous_les_profils()
    if not profils:
        st.info(f"Aucun athlète n'a encore créé de {NOM_PRODUIT}. Soyez le premier dans "
                 "« Nouveau Pack » !")
    else:
        st.caption(
            f"{len(profils)} athlète(s) ont créé leur {NOM_PRODUIT} — seule leur bio publique est "
            "visible ici. Le dossier complet (paliers, contact) reste privé, propre à chaque athlète."
        )
        colonnes = st.columns(3)
        for i, p in enumerate(profils):
            profil_p = p["profil"]
            contenu_p = contenu_depuis_dict(p["contenu"])
            photo_bytes_p = charger_photo(p.get("photo"))
            with colonnes[i % 3]:
                if photo_bytes_p:
                    b64 = base64.b64encode(photo_bytes_p).decode("utf-8")
                    photo_html = f'<img src="data:image/jpeg;base64,{b64}" />'
                else:
                    photo_html = '<div class="photo-vide">🏅</div>'
                st.markdown(
                    f"""
                    <div class="carte-athlete">
                        {photo_html}
                        <div class="nom">{profil_p.get('nom', '')}</div>
                        <div class="details">{profil_p.get('sport', '')}</div>
                        <div class="details">{profil_p.get('ville', '')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.expander("Voir sa bio"):
                    if contenu_p.accroche:
                        st.markdown(f"*{contenu_p.accroche}*")
                    if profil_p.get("palmares"):
                        st.markdown(f"**Palmarès**  \n{profil_p['palmares']}")
                    if contenu_p.paragraphe_profil:
                        st.write(contenu_p.paragraphe_profil)

# ---------------------------------------------------------------------------
# Page : nouveau Pack Sponsoring
# ---------------------------------------------------------------------------

elif page == "🆕 Nouveau Pack":
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

    st.markdown("**Audience réseaux sociaux (optionnel)** — ajoutez une ligne par réseau")
    col_h1, col_h2, col_h3, _ = st.columns([2, 2, 2, 0.6])
    col_h1.caption("Réseau")
    col_h2.caption("Abonnés")
    col_h3.caption("Likes moyens / publication")

    id_ligne_a_supprimer = None
    for rid in st.session_state.reseaux_ids:
        c1, c2, c3, c4 = st.columns([2, 2, 2, 0.6])
        with c1:
            st.selectbox(
                "Réseau", OPTIONS_RESEAUX, key=f"reseau_sel_{rid}", label_visibility="collapsed",
            )
        with c2:
            st.number_input(
                "Abonnés", min_value=0, step=100, key=f"reseau_ab_{rid}", label_visibility="collapsed",
            )
        with c3:
            st.number_input(
                "Likes moyens", min_value=0, step=10, key=f"reseau_lk_{rid}", label_visibility="collapsed",
            )
        with c4:
            if len(st.session_state.reseaux_ids) > 1 and st.button("🗑️", key=f"reseau_del_{rid}"):
                id_ligne_a_supprimer = rid

    if id_ligne_a_supprimer is not None:
        st.session_state.reseaux_ids.remove(id_ligne_a_supprimer)
        st.rerun()

    if st.button("+ Ajouter un réseau"):
        st.session_state.reseaux_ids.append(st.session_state.reseaux_next_id)
        st.session_state.reseaux_next_id += 1
        st.rerun()

    photo = st.file_uploader(
        "Photo (portrait ou action) — apparaîtra sur votre dossier PDF",
        type=["png", "jpg", "jpeg", "webp"],
    )

    valide = st.button(f"Générer mon {NOM_PRODUIT}", type="primary")

    if valide:
        if not email_compte.strip():
            st.error("Renseignez votre email au-dessus du formulaire : c'est ce qui vous permet de "
                      "retrouver vos Packs dans « Mes Packs ».")
        elif not api_key:
            st.error("Renseignez votre clé API Anthropic dans la barre latérale.")
        elif not (nom and sport and palmares):
            st.error("Les champs marqués d'un * sont obligatoires.")
        else:
            stats_liste = []
            for rid in st.session_state.reseaux_ids:
                reseau = st.session_state.get(f"reseau_sel_{rid}", "")
                abonnes = st.session_state.get(f"reseau_ab_{rid}", 0)
                likes = st.session_state.get(f"reseau_lk_{rid}", 0)
                if reseau and abonnes:
                    stats_liste.append(
                        StatsReseauSocial(plateforme=reseau, abonnes=int(abonnes), moyenne_likes=int(likes))
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
                "abonnes": sum(s.abonnes for s in stats_liste) if stats_liste else None,
                "contreparties_disponibles": contreparties_disponibles,
            }

            with st.spinner(f"Rédaction de votre {NOM_PRODUIT} par l'IA…"):
                contenu = generate_bilan_content(profil, api_key, modele)

            if contenu.erreur:
                st.error(f"Erreur lors de la génération : {contenu.erreur}")
            else:
                st.session_state.contenu_genere = contenu
                st.session_state.stats_extraites = stats_liste
                st.session_state.profil_courant = profil
                st.session_state.photo_courante = photo_bytes
                st.session_state.pdf_path = None
                sauver_bilan_pour_utilisateur(email_compte, profil, contenu, stats_liste, photo_bytes=photo_bytes)
                st.toast(f"{NOM_PRODUIT} enregistré dans votre compte — retrouvez-le dans « Mes Packs ».")

    # -----------------------------------------------------------------
    # Résultat + export PDF
    # -----------------------------------------------------------------

    if st.session_state.contenu_genere:
        contenu = st.session_state.contenu_genere
        stats_liste = st.session_state.stats_extraites or []
        profil = st.session_state.profil_courant

        st.subheader(f"Aperçu de votre {NOM_PRODUIT}")
        if contenu.accroche:
            st.markdown(f"*{contenu.accroche}*")
        st.write(contenu.paragraphe_profil)

        if stats_liste:
            cols_stats = st.columns(len(stats_liste))
            for col, s in zip(cols_stats, stats_liste):
                with col:
                    st.metric(s.plateforme or "Réseau", f"{s.abonnes:,}".replace(",", " ") + " abonnés")

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
                    profil, stats_liste, contenu, pdf_path, photo_bytes=st.session_state.photo_courante
                )
                st.session_state.pdf_path = Path(pdf_path).read_bytes()
            if avertissement:
                st.warning(f"PDF généré, mais : {avertissement}")
            else:
                st.success("PDF généré !")

        if st.session_state.pdf_path:
            col_dl, col_email = st.columns(2)
            with col_dl:
                st.download_button(
                    f"⬇️ Télécharger mon {NOM_PRODUIT} (PDF)",
                    data=st.session_state.pdf_path,
                    file_name=f"pack_sponsoring_{profil['nom'].replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            with col_email:
                with st.popover("📧 Recevoir par email", use_container_width=True):
                    email_destination = st.text_input(
                        "Votre adresse email", value=email_compte, key="email_destination_envoi"
                    )
                    if st.button("Envoyer", key="bouton_envoi_email"):
                        with st.spinner("Envoi en cours…"):
                            erreur_envoi = envoyer_bilan_par_email(
                                email_destination,
                                profil["nom"],
                                st.session_state.pdf_path,
                                email_expediteur,
                                email_mdp_app,
                            )
                        if erreur_envoi:
                            st.error(erreur_envoi)
                        else:
                            st.success(f"Envoyé à {email_destination} !")

        st.divider()
        st.subheader("🎯 Générer vos cibles de prospection")
        st.write("L'IA va scanner le web pour trouver jusqu'à 7 entreprises locales pertinentes, et vous proposer un email type de prospection à personnaliser vous-même.")

        if st.button("🚀 Trouver mes 7 PME cibles (Recherche Web)"):
            if not tavily_key:
                st.error("Il manque la clé API Tavily dans vos secrets.")
            elif not ville.strip():
                st.error("Renseignez une ville / région dans le formulaire ci-dessus pour cibler la "
                          "recherche d'entreprises locales.")
            else:
                # On repart des champs actuels du formulaire (nom/sport/ville) plutôt que du profil figé
                # au moment du dernier « Générer mon Pack » : sinon, modifier la ville après coup sans
                # régénérer le Pack utilisait encore l'ancienne valeur (ou une ville vide).
                profil_prospection = {**profil, "nom": nom, "sport": sport, "ville": ville}
                with st.spinner("Analyse du web et sélection des entreprises en cours..."):
                    resultats = generer_plan_prospection(profil_prospection, tavily_key, api_key, modele)

                    if "erreur" in resultats:
                        st.error(resultats["erreur"])
                    else:
                        st.session_state.donnees_prospection = resultats
                        st.session_state.profil_prospection = profil_prospection
                        email_type = resultats.get("email_type", {})
                        st.session_state.email_type_objet = email_type.get("objet", "")
                        st.session_state.email_type_corps = email_type.get("corps", "")
                        st.success("Analyse terminée !")

        if st.session_state.get("donnees_prospection"):
            profil_pour_pdf = st.session_state.get("profil_prospection", profil)
            with tempfile.TemporaryDirectory() as tmp:
                pdf_prosp_path = str(Path(tmp) / "plan_prospection.pdf")
                build_pdf_prospection(profil_pour_pdf, st.session_state.donnees_prospection, pdf_prosp_path)
                pdf_prosp_bytes = Path(pdf_prosp_path).read_bytes()

                st.download_button(
                    "⬇️ Télécharger mon plan d'attaque PME (PDF)",
                    data=pdf_prosp_bytes,
                    file_name=f"cibles_prospection_{profil_pour_pdf['nom'].replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )

            st.markdown("**✉️ Email type de prospection**")
            st.caption(
                "Un seul modèle, réutilisable pour toutes vos cibles : remplacez [Nom de l'entreprise] "
                "(et [Prénom du contact] si présent) avant chaque envoi. Modifiable ci-dessous."
            )
            st.text_input("Objet", key="email_type_objet")
            st.text_area("Corps de l'email", key="email_type_corps", height=220)

# ---------------------------------------------------------------------------
# Page : historique du compte
# ---------------------------------------------------------------------------

elif page == "📂 Mes Packs":
    if not email_compte.strip():
        st.info("Renseignez votre email en haut de la page pour voir vos Packs précédents.")
    else:
        historique = get_bilans_utilisateur(email_compte)
        if not historique:
            st.info(f"Aucun {NOM_PRODUIT} généré pour l'instant avec cet email.")
        else:
            st.caption(f"{len(historique)} {NOM_PRODUIT}(s) trouvé(s) pour {email_compte.strip().lower()}")
            for i, entree in enumerate(historique):
                profil_h = entree["profil"]
                with st.container(border=True):
                    col_info, col_bouton = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**{profil_h.get('nom', '')}** — {profil_h.get('sport', '')}")
                        st.caption(f"Généré le {entree['date']}")
                    with col_bouton:
                        contenu_h = contenu_depuis_dict(entree["contenu"])
                        stats_h = stats_liste_depuis_dict(entree.get("stats"))
                        photo_h = charger_photo(entree.get("photo"))
                        with tempfile.TemporaryDirectory() as tmp:
                            pdf_path = str(Path(tmp) / "bilan.pdf")
                            build_pdf(profil_h, stats_h, contenu_h, pdf_path, photo_bytes=photo_h)
                            pdf_bytes = Path(pdf_path).read_bytes()
                        st.download_button(
                            "⬇️ PDF",
                            data=pdf_bytes,
                            file_name=f"pack_sponsoring_{profil_h.get('nom', 'athlete').replace(' ', '_')}_{i}.pdf",
                            mime="application/pdf",
                            key=f"dl_historique_{i}",
                        )
