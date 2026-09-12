"""
Bilan de Valeur - logique coeur
-------------------------------
Un athlète de haut niveau renseigne son profil (et peut uploader une capture
d'écran de ses statistiques réseaux sociaux) -> l'IA rédige un "Bilan de
Valeur" professionnel -> un PDF prêt à envoyer à des sponsors potentiels est
généré.

Choix de scope assumé : l'argument fiscal (déductibilité du sponsoring) est
un paragraphe FIXE, pas généré par l'IA, pour éviter tout chiffre ou seuil
légal halluciné. L'IA ne rédige que la partie propre à l'athlète (profil,
proposition de valeur, contreparties suggérées) — jamais les données
chiffrées ayant une portée légale ou fiscale.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "claude-sonnet-5"

PALIERS_BORNES = {"min": 500, "max": 10000}  # garde-fou : bornes du pitch fondateur

SYSTEM_PROMPT_CONTENU = f"""Tu es un rédacteur spécialisé en sponsoring sportif, qui aide des athlètes
de haut niveau français à rédiger un dossier de sponsoring professionnel ("Bilan de Valeur") destiné à
des dirigeants de PME/ETI (BTP, ESN, industrie, conseil).

Tu reçois le profil d'un athlète en JSON. Réponds UNIQUEMENT avec un objet JSON valide, sans texte
autour, sans balises markdown, avec exactement ces clés :

{{
  "accroche": string,               // une phrase d'ouverture percutante (1 phrase, pas de superlatifs creux)
  "paragraphe_profil": string,      // 3-4 phrases présentant l'athlète, son parcours, ses valeurs
  "proposition_de_valeur": string,  // 2-3 phrases : pourquoi une PME locale gagnerait à s'associer à cet athlète
  "paliers": [
    {{
      "nom": string,               // ex: "Partenaire Découverte"
      "montant_eur": number,       // entre {PALIERS_BORNES['min']} et {PALIERS_BORNES['max']}, cohérent avec le profil
      "contreparties": [string]    // 2-4 contreparties concrètes (logo sur maillot, mention réseaux sociaux, etc.)
    }}
  ]  // exactement 3 paliers, montants croissants
}}

Règles :
- Ton sobre et professionnel, orienté PME locale (pas de ton "influenceur").
- Les montants de référence (bas/moyen/haut) te sont donnés dans le message utilisateur : utilise-les
  comme base pour les 3 paliers, ajuste de ±20% maximum si le profil le justifie clairement (ex :
  palmarès exceptionnel malgré peu d'abonnés). Ne les ignore jamais complètement.
- Les contreparties de chaque palier DOIVENT être choisies parmi celles listées dans
  "contreparties_disponibles" du profil (c'est ce que l'athlète a réellement accepté d'offrir). Si
  cette liste est vide, propose des contreparties standards du secteur.
- Si une ville/région est renseignée, utilise-la dans la proposition de valeur pour appuyer
  l'argument de l'ancrage local auprès d'une PME.
- Ne mentionne aucun chiffre de fiscalité ou de loi : ce n'est pas ton rôle, une autre partie du
  document s'en charge.
- Réponds uniquement avec le JSON, rien d'autre.
"""

SYSTEM_PROMPT_STATS = """Tu analyses une capture d'écran de statistiques d'un réseau social
(Instagram, TikTok, Strava, etc.) appartenant à un athlète. Réponds UNIQUEMENT avec un objet JSON
valide, sans texte autour, avec ces clés :

{
  "plateforme": string,        // "Instagram", "TikTok", "Strava", "" si indéterminé
  "abonnes": number,           // nombre d'abonnés/followers, 0 si illisible
  "moyenne_likes": number,     // moyenne de likes par publication si visible, 0 sinon
  "alerte": string             // "" si rien à signaler, sinon ce qui est illisible
}

Ne jamais inventer un chiffre non visible sur l'image : mets 0 ou "" et signale-le dans "alerte".
"""

FISCAL_TEXTE_FIXE = """Le sponsoring (parrainage) versé à un athlète dans le cadre d'un contrat de
partenariat commercial constitue, sous certaines conditions, une charge de publicité déductible du
résultat imposable de l'entreprise (article 39 du Code Général des Impôts). Contrairement au mécénat,
il permet également une contrepartie de visibilité pour l'entreprise. Ce document ne constitue pas un
conseil fiscal : la déductibilité effective dépend de chaque situation et doit être validée avec votre
expert-comptable avant signature."""

# Palette "médaille" pour les 3 paliers, cohérente entre l'aperçu Streamlit et le PDF.
COULEURS_PALIERS = ["#B08D57", "#8C9199", "#C9A227"]  # bronze, argent, or

CONTREPARTIES_STANDARD = [
    "Visibilité sur mes réseaux sociaux (posts, stories régulières)",
    "Logo sur ma tenue d'entraînement ou de compétition",
    "Présence physique (événements ou locaux de l'entreprise)",
    "Mention dans mes interviews / relations presse",
]

NIVEAU_SCORES = {
    "Régional": 0, "National": 1, "International": 2, "Équipe de France": 3, "Olympique": 4,
}


def calculer_montants_suggeres(niveau: str, abonnes: int) -> tuple[int, int, int]:
    """Calcule 3 montants de référence (bas/moyen/haut) à partir du niveau sportif et du
    nombre d'abonnés déclarés. Ce calcul est fait en code, pas par le LLM, pour que
    l'adaptation du prix au profil soit fiable et vérifiable plutôt que livrée à
    l'interprétation du modèle."""
    niveau_score = NIVEAU_SCORES.get(niveau, 0)
    abonnes = abonnes or 0
    if abonnes < 1000:
        abonnes_score = 0
    elif abonnes < 10000:
        abonnes_score = 1
    elif abonnes < 50000:
        abonnes_score = 2
    elif abonnes < 200000:
        abonnes_score = 3
    else:
        abonnes_score = 4

    score = niveau_score + abonnes_score  # de 0 à 8

    def _arrondi_50(valeur: float) -> int:
        return int(round(valeur / 50.0) * 50)

    bas = _arrondi_50(500 + (score / 8) * 1000)
    moyen = _arrondi_50(800 + (score / 8) * 4200)
    haut = _arrondi_50(1200 + (score / 8) * 8800)
    return bas, moyen, haut


@dataclass
class ContenuBilan:
    accroche: str = ""
    paragraphe_profil: str = ""
    proposition_de_valeur: str = ""
    paliers: list = field(default_factory=list)
    erreur: str = ""


@dataclass
class StatsReseauSocial:
    plateforme: str = ""
    abonnes: int = 0
    moyenne_likes: int = 0
    alerte: str = ""
    erreur: str = ""


def _clean_json_response(raw_text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()


def _call_claude(system_prompt: str, content_blocks: list, api_key: str, model: str) -> tuple[str, str]:
    """Retourne (texte_json, erreur). erreur est vide si tout s'est bien passé."""
    try:
        import anthropic
    except ImportError as exc:
        return "", f"paquet anthropic manquant : {exc}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": content_blocks}],
        )
        raw_text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        ).strip()
        return raw_text, ""
    except Exception as exc:
        return "", str(exc)


def generate_bilan_content(profil: dict, api_key: str, model: str = DEFAULT_MODEL) -> ContenuBilan:
    bas, moyen, haut = calculer_montants_suggeres(profil.get("niveau", ""), profil.get("abonnes") or 0)

    contenu_utilisateur = (
        f"Montants de référence calculés à partir du niveau et de l'audience déclarés : "
        f"palier bas ≈ {bas}€, palier moyen ≈ {moyen}€, palier haut ≈ {haut}€.\n\n"
        "Voici le profil de l'athlète, au format JSON. Rédige le Bilan de Valeur demandé.\n\n"
        + json.dumps(profil, ensure_ascii=False, indent=2)
    )
    raw_text, erreur = _call_claude(
        SYSTEM_PROMPT_CONTENU,
        [{"type": "text", "text": contenu_utilisateur}],
        api_key,
        model,
    )
    if erreur:
        return ContenuBilan(erreur=erreur)

    try:
        data = json.loads(_clean_json_response(raw_text))
    except json.JSONDecodeError:
        return ContenuBilan(erreur=f"réponse IA non structurée : {raw_text[:200]}")

    paliers = data.get("paliers", [])
    for p in paliers:
        try:
            p["montant_eur"] = max(
                PALIERS_BORNES["min"], min(PALIERS_BORNES["max"], float(p.get("montant_eur", 0)))
            )
        except (TypeError, ValueError):
            p["montant_eur"] = PALIERS_BORNES["min"]

    return ContenuBilan(
        accroche=str(data.get("accroche", "")).strip(),
        paragraphe_profil=str(data.get("paragraphe_profil", "")).strip(),
        proposition_de_valeur=str(data.get("proposition_de_valeur", "")).strip(),
        paliers=paliers,
    )


def _guess_media_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
        ext, "image/jpeg"
    )


def extract_social_stats(
    file_bytes: bytes, filename: str, api_key: str, model: str = DEFAULT_MODEL
) -> StatsReseauSocial:
    media_type = _guess_media_type(filename)
    b64_data = base64.standard_b64encode(file_bytes).decode("utf-8")
    content_blocks = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
        {"type": "text", "text": "Analyse cette capture d'écran de statistiques et renvoie le JSON demandé."},
    ]
    raw_text, erreur = _call_claude(SYSTEM_PROMPT_STATS, content_blocks, api_key, model)
    if erreur:
        return StatsReseauSocial(erreur=erreur)

    try:
        data = json.loads(_clean_json_response(raw_text))
    except json.JSONDecodeError:
        return StatsReseauSocial(erreur=f"réponse IA non structurée : {raw_text[:200]}")

    try:
        abonnes = int(float(data.get("abonnes", 0)))
    except (TypeError, ValueError):
        abonnes = 0

    return StatsReseauSocial(
        plateforme=str(data.get("plateforme", "")).strip(),
        abonnes=abonnes,
        moyenne_likes=int(float(data.get("moyenne_likes", 0) or 0)),
        alerte=str(data.get("alerte", "")).strip(),
    )


# ---------------------------------------------------------------------------
# Génération du PDF
# ---------------------------------------------------------------------------

def _photo_circulaire(photo_bytes: bytes, taille_px: int = 400):
    """Recadre une photo en carré centré puis applique un masque circulaire.
    Retourne un buffer PNG (avec transparence) prêt à être intégré au PDF."""
    import io
    from PIL import Image as PILImage, ImageDraw, ImageOps

    img = PILImage.open(io.BytesIO(photo_bytes)).convert("RGBA")
    img = ImageOps.exif_transpose(img)  # respecte l'orientation EXIF (photos de téléphone)

    # Recadrage carré centré
    largeur, hauteur = img.size
    cote = min(largeur, hauteur)
    gauche = (largeur - cote) // 2
    haut = (hauteur - cote) // 2
    img = img.crop((gauche, haut, gauche + cote, haut + cote)).resize((taille_px, taille_px))

    masque = PILImage.new("L", (taille_px, taille_px), 0)
    dessin = ImageDraw.Draw(masque)
    dessin.ellipse((0, 0, taille_px, taille_px), fill=255)

    resultat = PILImage.new("RGBA", (taille_px, taille_px))
    resultat.paste(img, (0, 0), mask=masque)

    tampon = io.BytesIO()
    resultat.save(tampon, format="PNG")
    tampon.seek(0)
    return tampon


def build_pdf(
    profil: dict,
    stats: Optional[StatsReseauSocial],
    contenu: ContenuBilan,
    output_path: str,
    photo_bytes: Optional[bytes] = None,
) -> Optional[str]:
    """Génère le PDF. Retourne None si tout s'est bien passé, ou un message
    d'avertissement (string) si la photo n'a pas pu être intégrée — le PDF est
    alors quand même généré, sans photo, plutôt que d'échouer complètement."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable,
        Image,
    )

    styles = getSampleStyleSheet()
    bleu = colors.HexColor("#1E4D8C")

    titre_style = ParagraphStyle(
        "TitreBilan", parent=styles["Title"], textColor=bleu, fontSize=22, spaceAfter=4, alignment=0
    )
    accroche_style = ParagraphStyle(
        "Accroche", parent=styles["Normal"], fontSize=13, textColor=colors.HexColor("#3A4550"),
        spaceAfter=14, leading=17,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], textColor=bleu, spaceBefore=14, spaceAfter=6
    )
    corps_style = ParagraphStyle("Corps", parent=styles["Normal"], leading=15, spaceAfter=8)
    petit_style = ParagraphStyle(
        "Petit", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#6B7280"), leading=11
    )

    story = []
    avertissement_photo = None

    # En-tête : titre + sous-titre à gauche, photo circulaire à droite si fournie
    sous_titre = f"{profil.get('sport', '')} — Dossier de partenariat"
    if profil.get("ville"):
        sous_titre = f"{profil.get('sport', '')} · {profil['ville']} — Dossier de partenariat"

    bloc_titre = [
        Paragraph(profil.get("nom", "Bilan de Valeur"), titre_style),
        Paragraph(sous_titre, accroche_style),
    ]
    if photo_bytes:
        try:
            photo_buffer = _photo_circulaire(photo_bytes)
            img_flowable = Image(photo_buffer, width=2.6 * cm, height=2.6 * cm)
            entete = Table([[bloc_titre, img_flowable]], colWidths=[12.5 * cm, 3 * cm])
            entete.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]))
            story.append(entete)
        except Exception as exc:
            # Une photo illisible ne doit jamais faire échouer tout le PDF, mais
            # l'erreur doit être visible plutôt que masquée.
            avertissement_photo = f"Photo non intégrée au PDF ({type(exc).__name__}: {exc})"
            story.extend(bloc_titre)
    else:
        story.extend(bloc_titre)

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=bleu, thickness=1))
    story.append(Spacer(1, 10))

    if contenu.accroche:
        story.append(Paragraph(f"<i>{contenu.accroche}</i>", accroche_style))

    story.append(Paragraph("Profil", section_style))
    story.append(Paragraph(contenu.paragraphe_profil or "—", corps_style))

    if profil.get("palmares"):
        story.append(Paragraph("Palmarès", section_style))
        story.append(Paragraph(profil["palmares"], corps_style))

    if stats and stats.abonnes:
        story.append(Paragraph("Audience", section_style))
        texte_stats = f"{stats.abonnes:,} abonnés".replace(",", " ")
        if stats.plateforme:
            texte_stats += f" sur {stats.plateforme}"
        if stats.moyenne_likes:
            texte_stats += f" — {stats.moyenne_likes:,} likes en moyenne par publication".replace(",", " ")
        story.append(Paragraph(texte_stats, corps_style))

    story.append(Paragraph("Pourquoi s'associer à ce projet ?", section_style))
    story.append(Paragraph(contenu.proposition_de_valeur or "—", corps_style))

    if contenu.paliers:
        story.append(Paragraph("Paliers de partenariat proposés", section_style))
        nom_style = ParagraphStyle("NomPalier", parent=corps_style, fontSize=9, leading=12)
        montant_style = ParagraphStyle(
            "MontantPalier", parent=corps_style, fontSize=9, leading=12, alignment=1
        )
        data_table = [["Palier", "Montant", "Contreparties"]]
        for p in contenu.paliers:
            contreparties = "<br/>".join(f"• {c}" for c in p.get("contreparties", []))
            data_table.append([
                Paragraph(p.get("nom", ""), nom_style),
                Paragraph(f"{int(p.get('montant_eur', 0)):,} €".replace(",", " "), montant_style),
                Paragraph(contreparties, corps_style),
            ])
        table = Table(data_table, colWidths=[4.3 * cm, 2.4 * cm, 8.3 * cm])
        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), bleu),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        # Liseré coloré (bronze / argent / or) devant chaque ligne de palier.
        for i in range(len(contenu.paliers)):
            couleur = colors.HexColor(COULEURS_PALIERS[i % len(COULEURS_PALIERS)])
            style_commands.append(("LINEBEFORE", (0, i + 1), (0, i + 1), 4, couleur))
        table.setStyle(TableStyle(style_commands))
        story.append(table)

    story.append(Spacer(1, 16))
    story.append(Paragraph("Cadre fiscal", section_style))
    story.append(Paragraph(FISCAL_TEXTE_FIXE, petit_style))

    if profil.get("contact"):
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"Contact : {profil['contact']}", corps_style))

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    doc.build(story)
    return avertissement_photo


# ---------------------------------------------------------------------------
# Témoignages (preuve de traction)
# ---------------------------------------------------------------------------

TEMOIGNAGES_PATH = Path(__file__).parent / "data" / "temoignages.json"


def charger_temoignages() -> list:
    if TEMOIGNAGES_PATH.exists():
        try:
            return json.loads(TEMOIGNAGES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def sauver_temoignage(nom: str, sport: str, avis: str) -> None:
    temoignages = charger_temoignages()
    temoignages.append({"nom": nom or "Anonyme", "sport": sport, "avis": avis})
    TEMOIGNAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMOIGNAGES_PATH.write_text(json.dumps(temoignages, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Comptes utilisateur (persistance des Bilans générés)
# ---------------------------------------------------------------------------
#
# Choix de scope assumé : le "compte" est identifié par une simple adresse
# email, sans mot de passe. Ce n'est pas une vraie authentification, c'est un
# identifiant de session persistante suffisant pour démontrer la mécanique
# SaaS (retrouver ses données d'une visite à l'autre) en une nuit de
# hackathon. Une vraie authentification (magic link, OAuth) est la suite
# logique, hors scope de ce soir.

COMPTES_PATH = Path(__file__).parent / "data" / "comptes.json"


def _normaliser_email(email: str) -> str:
    return email.strip().lower()


def _charger_comptes() -> dict:
    if COMPTES_PATH.exists():
        try:
            return json.loads(COMPTES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _sauver_comptes(comptes: dict) -> None:
    COMPTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPTES_PATH.write_text(json.dumps(comptes, ensure_ascii=False, indent=2), encoding="utf-8")


def sauver_bilan_pour_utilisateur(
    email: str, profil: dict, contenu: ContenuBilan, stats: Optional[StatsReseauSocial]
) -> None:
    """Enregistre un Bilan généré dans l'historique du compte (créé à la volée)."""
    from datetime import datetime

    email_normalise = _normaliser_email(email)
    if not email_normalise:
        return

    comptes = _charger_comptes()
    comptes.setdefault(email_normalise, [])
    comptes[email_normalise].append(
        {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "profil": profil,
            "contenu": asdict(contenu),
            "stats": asdict(stats) if stats else None,
        }
    )
    _sauver_comptes(comptes)


def get_bilans_utilisateur(email: str) -> list:
    """Retourne l'historique des Bilans générés pour ce compte, du plus récent au plus ancien."""
    comptes = _charger_comptes()
    entrees = comptes.get(_normaliser_email(email), [])
    return list(reversed(entrees))


def contenu_depuis_dict(d: dict) -> ContenuBilan:
    return ContenuBilan(
        accroche=d.get("accroche", ""),
        paragraphe_profil=d.get("paragraphe_profil", ""),
        proposition_de_valeur=d.get("proposition_de_valeur", ""),
        paliers=d.get("paliers", []),
    )


def stats_depuis_dict(d: Optional[dict]) -> Optional[StatsReseauSocial]:
    if not d:
        return None
    return StatsReseauSocial(
        plateforme=d.get("plateforme", ""),
        abonnes=d.get("abonnes", 0),
        moyenne_likes=d.get("moyenne_likes", 0),
    )