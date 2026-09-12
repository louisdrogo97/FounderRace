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

# Nom affiché du produit — centralisé ici pour n'avoir qu'un seul endroit à changer
# (titres, PDF, emails...).
NOM_PRODUIT = "Pack Sponsoring"

DEFAULT_MODEL = "claude-sonnet-5"

PALIERS_BORNES = {"min": 500, "max": 10000}  # garde-fou : bornes du pitch fondateur

SYSTEM_PROMPT_CONTENU = f"""Tu es un expert en marketing sportif B2B. Tu rédiges un "{NOM_PRODUIT}" pour convaincre des dirigeants de PME/ETI (notamment dans le BTP, l'industrie, les ESN ou le conseil).

Tu reçois le profil d'un athlète en JSON. Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, sans balises markdown, avec exactement ces clés :

{{
  "accroche": string,                 // 1 phrase choc liant la performance de l'athlète à l'ambition de l'entreprise.
  "paragraphe_profil": string,        // Un storytelling percutant (3 phrases) : focus sur la résilience, l'objectif, et le parallèle avec le monde de l'entreprise. Pas de liste de résultats ennuyeuse.
  "proposition_de_valeur": string,    // 3 phrases : Démontre l'impact ROI (Marque employeur, fierté interne, ancrage territorial, management).
  "paliers": [
    {{
      "nom": string,                  // ex: "Partenaire Performance", "Pack Marque Employeur"
      "montant_eur": number,          // entre {PALIERS_BORNES['min']} et {PALIERS_BORNES['max']}, cohérent avec le profil.
      "contreparties": [string]       // 2-4 contreparties concrètes (logo, intervention en entreprise, post LinkedIn, etc.).
    }}
  ]  // exactement 3 paliers, montants croissants
}}

Règles :
- Ton incisif, business, orienté "retour sur investissement" et "management".
- Remplace impérativement le vocabulaire associatif ("aidez-moi", "soutenez-moi", "don") par un vocabulaire de partenariat ("investissez", "associez votre image", "collaborons").
- Les montants de référence (bas/moyen/haut) te sont donnés dans le message utilisateur : utilise-les comme base pour les 3 paliers, ajuste de ±20% maximum si le profil le justifie clairement. Ne les ignore jamais complètement.
- Les contreparties de chaque palier DOIVENT être choisies parmi celles listées dans "contreparties_disponibles" du profil (c'est ce que l'athlète a réellement accepté d'offrir). Si cette liste est vide, propose des contreparties standards du secteur.
- Si une ville/région est renseignée, utilise-la dans la proposition de valeur pour appuyer l'argument de l'ancrage local.
- Ne mentionne aucun chiffre de fiscalité ou de loi : ce n'est pas ton rôle, une autre partie du document s'en charge.
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

# Texte FIXE (pas généré par IA) pour la même raison que FISCAL_TEXTE_FIXE : un taux de
# référence sourcé plutôt qu'un chiffre inventé au cas par cas par le modèle.
BENCHMARK_ENGAGEMENT_TEXTE = (
    "À titre de repère, le taux d'engagement moyen constaté sur les réseaux sociaux se situe "
    "généralement entre 1 % et 3 % des abonnés. Un taux plus élevé traduit une audience plus "
    "qualifiée et donc plus réceptive aux messages relayés pour vos partenaires."
)

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


def _call_claude(
    system_prompt: str, content_blocks: list, api_key: str, model: str, max_tokens: int = 1500
) -> tuple[str, str]:
    """Retourne (texte_json, erreur). erreur est vide si tout s'est bien passé."""
    try:
        import anthropic
    except ImportError as exc:
        return "", f"paquet anthropic manquant : {exc}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
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
        f"Voici le profil de l'athlète, au format JSON. Rédige le {NOM_PRODUIT} demandé.\n\n"
        + json.dumps(profil, ensure_ascii=False, indent=2)
    )
    raw_text, erreur = _call_claude(
        SYSTEM_PROMPT_CONTENU,
        [{"type": "text", "text": contenu_utilisateur}],
        api_key,
        model,
        max_tokens=4000,
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
    stats_liste: Optional[list],
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
        KeepTogether,
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
        Paragraph(profil.get("nom", NOM_PRODUIT), titre_style),
        Paragraph(sous_titre, accroche_style),
    ]
    if photo_bytes:
        try:
            photo_buffer = _photo_circulaire(photo_bytes, taille_px=600)
            img_flowable = Image(photo_buffer, width=4.0 * cm, height=4.0 * cm)
            entete = Table([[bloc_titre, img_flowable]], colWidths=[11.5 * cm, 4.5 * cm])
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
        accroche_encart_style = ParagraphStyle(
            "AccrocheEncart", parent=styles["Normal"], fontSize=12.5, leading=17,
            textColor=colors.HexColor("#16365F"), fontName="Helvetica-Oblique",
        )
        encart = Table(
            [[Paragraph(contenu.accroche, accroche_encart_style)]], colWidths=[15 * cm]
        )
        encart.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2F6")),
            ("LINEBEFORE", (0, 0), (0, -1), 4, bleu),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ]))
        story.append(encart)
        story.append(Spacer(1, 12))

    story.append(Paragraph("Profil", section_style))
    story.append(Paragraph(contenu.paragraphe_profil or "—", corps_style))

    if profil.get("palmares"):
        story.append(Paragraph("Palmarès", section_style))
        story.append(Paragraph(profil["palmares"], corps_style))

    stats_valides = [s for s in (stats_liste or []) if s and s.abonnes]
    if stats_valides:
        story.append(Paragraph("Audience & visibilité", section_style))

        data_audience = [["Réseau", "Abonnés", "Engagement moyen", "Taux d'engagement"]]
        for s in stats_valides:
            taux = (s.moyenne_likes / s.abonnes * 100) if s.abonnes else 0
            data_audience.append([
                Paragraph(s.plateforme or "—", corps_style),
                Paragraph(f"{s.abonnes:,}".replace(",", " "), corps_style),
                Paragraph(f"{s.moyenne_likes:,} likes / pub".replace(",", " ") if s.moyenne_likes else "—", corps_style),
                Paragraph(f"{taux:.1f} %" if s.moyenne_likes else "—", corps_style),
            ])

        table_audience = Table(data_audience, colWidths=[3.5 * cm, 3 * cm, 4.5 * cm, 4 * cm])
        table_audience.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), bleu),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table_audience)
        story.append(Spacer(1, 8))

        if len(stats_valides) > 1:
            audience_totale = sum(s.abonnes for s in stats_valides)
            story.append(Paragraph(
                f"Audience cumulée sur {len(stats_valides)} réseaux : "
                f"{audience_totale:,} abonnés touchés au total.".replace(",", " "),
                corps_style,
            ))

        if any(s.moyenne_likes for s in stats_valides):
            story.append(Paragraph(BENCHMARK_ENGAGEMENT_TEXTE, petit_style))

    story.append(Paragraph("Pourquoi s'associer à ce projet ?", section_style))
    story.append(Paragraph(contenu.proposition_de_valeur or "—", corps_style))

    if contenu.paliers:
        bloc_paliers = [Paragraph("Paliers de partenariat proposés", section_style)]
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
        bloc_paliers.append(table)
        # KeepTogether évite que la dernière ligne du tableau se retrouve seule
        # sur la page suivante, sans son en-tête (défaut visuel constaté).
        story.append(KeepTogether(bloc_paliers))

    story.append(Spacer(1, 18))
    story.append(Paragraph("Cadre fiscal", section_style))
    story.append(Paragraph(FISCAL_TEXTE_FIXE, petit_style))

    contact = profil.get("contact")
    if contact:
        cta_style = ParagraphStyle(
            "CTA", parent=styles["Normal"], fontSize=11, leading=15, textColor=colors.white,
        )
        cta_titre_style = ParagraphStyle(
            "CTATitre", parent=cta_style, fontSize=13, fontName="Helvetica-Bold", spaceAfter=4,
        )
        bloc_cta = Table(
            [[Paragraph("Intéressé par ce partenariat ?", cta_titre_style)],
             [Paragraph(f"Contactez {profil.get('nom', 'moi')} directement : {contact}", cta_style)]],
            colWidths=[15 * cm],
        )
        bloc_cta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bleu),
            ("TOPPADDING", (0, 0), (-1, 0), 14),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 1), (-1, 1), 2),
        ]))
        story.append(Spacer(1, 16))
        story.append(bloc_cta)

    nom_athlete = profil.get("nom", NOM_PRODUIT)

    def _pied_de_page(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(bleu)
        canvas.rect(0, 0, A4[0], 1.1 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 0.4 * cm, f"{NOM_PRODUIT} — {nom_athlete}")
        canvas.drawRightString(A4[0] - 2 * cm, 0.4 * cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2.3 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    doc.build(story, onFirstPage=_pied_de_page, onLaterPages=_pied_de_page)
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
PHOTOS_DIR = Path(__file__).parent / "data" / "photos"


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
    email: str,
    profil: dict,
    contenu: ContenuBilan,
    stats_liste: Optional[list],
    photo_bytes: Optional[bytes] = None,
) -> None:
    """Enregistre un Bilan généré dans l'historique du compte (créé à la volée).

    Si une photo est fournie, elle est écrite sur disque (data/photos/) et
    seul son nom de fichier est stocké dans comptes.json — on évite de
    gonfler ce fichier JSON avec des blobs binaires encodés en base64."""
    from datetime import datetime

    email_normalise = _normaliser_email(email)
    if not email_normalise:
        return

    nom_photo = None
    if photo_bytes:
        try:
            PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            nom_photo = f"{email_normalise.replace('@', '_at_')}.jpg"
            (PHOTOS_DIR / nom_photo).write_bytes(photo_bytes)
        except OSError:
            nom_photo = None  # l'échec d'écriture de la photo ne doit pas bloquer la sauvegarde du bilan

    comptes = _charger_comptes()
    comptes.setdefault(email_normalise, [])
    comptes[email_normalise].append(
        {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "profil": profil,
            "contenu": asdict(contenu),
            "stats": [asdict(s) for s in stats_liste] if stats_liste else [],
            "photo": nom_photo,
        }
    )
    _sauver_comptes(comptes)


def charger_photo(nom_photo: Optional[str]) -> Optional[bytes]:
    if not nom_photo:
        return None
    chemin = PHOTOS_DIR / nom_photo
    if chemin.exists():
        return chemin.read_bytes()
    return None


def get_bilans_utilisateur(email: str) -> list:
    """Retourne l'historique des Bilans générés pour ce compte, du plus récent au plus ancien."""
    comptes = _charger_comptes()
    entrees = comptes.get(_normaliser_email(email), [])
    return list(reversed(entrees))


def get_tous_les_profils() -> list:
    """Retourne, pour chaque compte ayant généré au moins un Bilan, son entrée la plus
    récente — utilisé pour la page d'accueil qui liste tous les athlètes inscrits."""
    comptes = _charger_comptes()
    profils = []
    for email, entrees in comptes.items():
        if entrees:
            derniere = entrees[-1]
            profils.append({"email": email, **derniere})
    # Les plus récemment actifs en premier
    profils.sort(key=lambda p: p.get("date", ""), reverse=True)
    return profils


def contenu_depuis_dict(d: dict) -> ContenuBilan:
    return ContenuBilan(
        accroche=d.get("accroche", ""),
        paragraphe_profil=d.get("paragraphe_profil", ""),
        proposition_de_valeur=d.get("proposition_de_valeur", ""),
        paliers=d.get("paliers", []),
    )


def stats_liste_depuis_dict(d) -> list:
    """Reconstruit la liste de StatsReseauSocial sauvegardée. Gère aussi l'ancien format
    (un seul dict par bilan, avant le support multi-réseaux) pour ne pas casser l'historique
    des bilans déjà enregistrés."""
    if not d:
        return []
    entrees = [d] if isinstance(d, dict) else d
    return [
        StatsReseauSocial(
            plateforme=e.get("plateforme", ""),
            abonnes=e.get("abonnes", 0),
            moyenne_likes=e.get("moyenne_likes", 0),
        )
        for e in entrees
    ]


# ---------------------------------------------------------------------------
# Envoi du Bilan par email
# ---------------------------------------------------------------------------
#
# Choix de scope assumé : envoi via SMTP avec un compte email dédié à
# l'application (ex: un compte Gmail avec un "mot de passe d'application"),
# pas via un service tiers payant (Resend, SendGrid...) pour éviter d'ajouter
# encore une inscription à faire cette nuit. À faire évoluer vers un service
# transactionnel dédié si le volume d'envoi grandit.

def envoyer_bilan_par_email(
    destinataire: str,
    nom_athlete: str,
    pdf_bytes: bytes,
    expediteur: str,
    mot_de_passe_app: str,
    smtp_serveur: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> Optional[str]:
    """Envoie le PDF par email. Retourne None si succès, sinon un message d'erreur lisible."""
    import smtplib
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not destinataire or "@" not in destinataire:
        return "Adresse email de destination invalide."
    if not expediteur or not mot_de_passe_app:
        return "Configuration email manquante (expéditeur / mot de passe d'application) dans la barre latérale."

    message = MIMEMultipart()
    message["From"] = expediteur
    message["To"] = destinataire
    message["Subject"] = f"Votre {NOM_PRODUIT} — {nom_athlete}"
    message.attach(MIMEText(
        f"Bonjour,\n\nVoici votre {NOM_PRODUIT} généré pour {nom_athlete}, prêt à être envoyé à "
        "vos partenaires potentiels.\n\nBonne prospection !",
        "plain",
    ))
    piece_jointe = MIMEApplication(pdf_bytes, _subtype="pdf")
    piece_jointe.add_header(
        "Content-Disposition", "attachment", filename=f"bilan_de_valeur_{nom_athlete.replace(' ', '_')}.pdf"
    )
    message.attach(piece_jointe)

    try:
        with smtplib.SMTP(smtp_serveur, smtp_port, timeout=15) as serveur:
            serveur.starttls()
            serveur.login(expediteur, mot_de_passe_app)
            serveur.sendmail(expediteur, destinataire, message.as_string())
        return None
    except smtplib.SMTPAuthenticationError:
        return ("Authentification refusée : utilisez un mot de passe d'application (pas votre mot de "
                "passe Gmail habituel) — voir myaccount.google.com/apppasswords.")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"




import requests

SYSTEM_PROMPT_PROSPECTION = """Tu es un expert en développement commercial B2B et en rédaction d'emails de prospection.
Analyse les résultats bruts de recherche web fournis (avec leur source) et sélectionne, PARMI CES
RÉSULTATS UNIQUEMENT, jusqu'à 7 entreprises (toute taille : PME, ETI, grand groupe, cabinet, agence...)
susceptibles d'être approchées pour un partenariat de sponsoring sportif local, classées de la plus
pertinente à la moins pertinente. Sois inclusif plutôt que sélectif : dès qu'un nom d'entreprise
identifiable apparaît dans les résultats et a une présence locale plausible, retiens-le, même si le lien
avec le sponsoring sportif n'est pas parfait — c'est à "pourquoi_pertinente" de construire ce lien, pas un
critère d'exclusion. Priorité, si les résultats le permettent, aux entreprises des secteurs sport,
nutrition, santé ou bien-être, mais ce n'est jamais obligatoire : mieux vaut proposer une entreprise
pertinente d'un autre secteur que de ne rien proposer.

En plus de la liste d'entreprises, rédige UN SEUL email type de prospection, générique et réutilisable
pour n'importe laquelle des entreprises listées (pas un email par entreprise) — l'athlète le personnalisera
lui-même avant chaque envoi.

Réponds UNIQUEMENT avec un JSON valide, sans texte autour, sans balises markdown, respectant
exactement ce format :
{
  "cibles": [
    {
      "nom_entreprise": string,        // DOIT être un nom qui apparaît explicitement dans les résultats fournis
      "source_url": string,            // l'URL du résultat d'où vient cette entreprise, copiée telle quelle
      "pourquoi_pertinente": string,   // 2 phrases max : lien direct entre l'entreprise, le sport et la marque employeur
      "contact_nom": string,           // nom d'un responsable/décideur SEULEMENT s'il est cité explicitement dans les résultats, sinon ""
      "contact_email": string,         // email SEULEMENT s'il apparaît explicitement dans les résultats, sinon ""
      "contact_telephone": string      // téléphone SEULEMENT s'il apparaît explicitement dans les résultats, sinon ""
    }
  ],
  "email_type": {
    "objet": string,   // objet court et concret, ex: "Partenariat sponsoring — [Nom athlète]"
    "corps": string    // email complet, voir consignes ci-dessous
  }
}

Consignes de rédaction pour "email_type.corps" :
- Ton professionnel et direct, dans un cadre de partenariat commercial (jamais de vocabulaire associatif
  du type "aidez-moi" ou "faites un don").
- Générique : utilise "[Nom de l'entreprise]" et, si pertinent, "[Prénom du contact]" comme placeholders à
  remplacer par l'athlète avant l'envoi — ne mentionne aucune entreprise en particulier.
- Structure en 4 courts paragraphes séparés par des sauts de ligne ("\\n\\n") : (1) formule de politesse +
  qui est l'athlète et son objectif sportif, (2) pourquoi il cherche des partenaires locaux comme
  "[Nom de l'entreprise]" (ancrage territorial, valeurs communes), (3) ce que le partenariat apporte
  concrètement à l'entreprise (visibilité, marque employeur, ancrage local), (4) appel à l'action clair
  (proposer un échange) + formule de politesse finale et le nom de l'athlète.
- Environ 120 à 180 mots. Pas de markdown, texte brut uniquement.

Règles impératives :
- N'invente JAMAIS un nom d'entreprise, une URL, ou un détail qui n'apparaît pas explicitement dans
  les résultats de recherche fournis. C'est la règle la plus importante : une entreprise fabriquée
  n'a aucune valeur et peut nuire à la crédibilité de l'athlète auprès d'un vrai interlocuteur. En
  dehors de cette contrainte de non-fabrication, reste large sur ce que tu acceptes comme cible.
- Ne réponds avec {"cibles": []} qu'en tout dernier recours, si les résultats fournis ne contiennent
  vraiment AUCUN nom d'entreprise identifiable (ex : uniquement des pages génériques sans aucune
  raison sociale citée). Si au moins une entreprise est nommée quelque part dans les résultats,
  retiens-la plutôt que de renvoyer une liste vide.
- S'il y a moins de 7 entreprises identifiables dans les résultats, renvoie-en moins — n'invente
  jamais pour atteindre 7.
- "contact_nom", "contact_email" et "contact_telephone" doivent rester vides ("") par défaut. Ne
  les remplis QUE si la donnée exacte (nom de personne, adresse email ou numéro) apparaît telle
  quelle dans les résultats fournis. Ne déduis jamais un email à partir d'un nom d'entreprise
  (ex : ne génère jamais "contact@nomdelentreprise.fr" si cette adresse n'est pas écrite noir sur
  blanc dans les résultats) : un contact inventé est pire qu'aucun contact.
"""

def generer_plan_prospection(profil: dict, tavily_key: str, anthropic_key: str, model: str = DEFAULT_MODEL) -> dict:
    # `.get(clé, defaut)` ne s'applique que si la clé est absente, pas si elle vaut "" — d'où le `or`,
    # nécessaire puisque ces clés existent toujours dans profil (juste parfois vides).
    ville = profil.get("ville") or "Île-de-France"
    sport = profil.get("sport") or "sport de haut niveau"
    nom_athlete = profil.get("nom") or "L'athlète"

    # 1. Appel(s) API Tavily pour trouver les PME locales. Les requêtes sont volontairement variées
    # (un annuaire ou une liste d'entreprises locales matche mieux qu'une requête trop spécifique) ;
    # on vise assez de matière pour identifier jusqu'à 7 entreprises, quitte à enchaîner plusieurs
    # requêtes plutôt que d'abandonner tôt.
    requetes = [
        f"annuaire entreprises PME ETI {ville} BTP industrie ESN conseil",
        f"entreprises {ville} recrutement marque employeur sponsoring local contact dirigeant responsable RH",
        f"entreprises locales {ville} partenaire sponsoring {sport} club associations",
    ]

    blocs = []
    for query in requetes:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": "advanced", "max_results": 15},
                timeout=15
            )
            resp.raise_for_status()
            tavily_data = resp.json()
        except Exception as e:
            if not blocs:
                return {"erreur": f"Échec de la recherche web Tavily : {str(e)}"}
            continue

        resultats_bruts = tavily_data.get("results", [])
        blocs.extend(
            f"Source : {r.get('url', 'url inconnue')}\nContenu : {r.get('content', '')}"
            for r in resultats_bruts if r.get("content")
        )

        # Assez de matière pour espérer 7 entreprises distinctes : pas besoin des requêtes suivantes.
        if len(blocs) >= 18:
            break

    contexte_web = "\n\n---\n\n".join(blocs)

    if not contexte_web.strip():
        return {"erreur": "Aucun résultat exploitable trouvé par la recherche web pour cette ville/ce "
                           "secteur. Essayez avec une ville plus grande ou reformulez le profil.",
                "cibles": []}

    # 2. Synthèse par Claude, strictement ancrée sur les résultats ci-dessus
    contenu_utilisateur = (
        f"Athlète : {nom_athlete}, {sport}, basé(e) à {ville}.\n\n"
        f"Résultats de recherche web (avec leur source) :\n{contexte_web}\n\n"
        "Identifie, parmi CES résultats uniquement, les entreprises pertinentes ainsi qu'un email type "
        "de prospection réutilisable, et génère le JSON demandé."
    )

    raw_text, erreur = _call_claude(
        SYSTEM_PROMPT_PROSPECTION,
        [{"type": "text", "text": contenu_utilisateur}],
        anthropic_key,
        model,
        max_tokens=4000,
    )

    if erreur:
        return {"erreur": erreur}

    try:
        return json.loads(_clean_json_response(raw_text))
    except json.JSONDecodeError:
        # On remonte le texte brut (tronqué) plutôt que de cacher l'erreur : c'est ce qui
        # permet de diagnostiquer un vrai problème au lieu de deviner.
        return {"erreur": f"Réponse IA non structurée. Début de la réponse reçue : {raw_text[:300]}"}

def build_pdf_prospection(profil: dict, donnees_prospection: dict, output_path: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, KeepTogether

    styles = getSampleStyleSheet()
    bleu = colors.HexColor("#1E4D8C")

    titre_style = ParagraphStyle("Titre", parent=styles["Title"], textColor=bleu, fontSize=20, alignment=0)
    sous_titre = ParagraphStyle("SousTitre", parent=styles["Normal"], fontSize=12, spaceAfter=20, textColor=colors.HexColor("#3A4550"))
    nom_ent = ParagraphStyle("NomEnt", parent=styles["Heading2"], textColor=bleu, fontSize=14, spaceBefore=14, spaceAfter=6)
    corps = ParagraphStyle("Corps", parent=styles["Normal"], leading=15, spaceAfter=8)

    story = []
    story.append(Paragraph("Plan d'Attaque Prospection", titre_style))
    cibles = donnees_prospection.get("cibles", [])
    story.append(Paragraph(
        f"{len(cibles)} cible(s) identifiée(s) par IA pour {profil.get('nom', '')} ({profil.get('ville', '')})",
        sous_titre,
    ))
    story.append(HRFlowable(width="100%", color=bleu, thickness=1))
    story.append(Spacer(1, 15))

    contact_style = ParagraphStyle("Contact", parent=corps, fontSize=9, textColor=colors.HexColor("#1E293B"))
    source_style = ParagraphStyle("Source", parent=corps, fontSize=8, textColor=colors.HexColor("#6B7280"))

    for cible in cibles:
        bloc = [
            Paragraph(cible.get("nom_entreprise", "Entreprise"), nom_ent),
            Paragraph(f"<b>Pourquoi cette cible :</b> {cible.get('pourquoi_pertinente', '')}", corps),
        ]

        coordonnees = [
            (label, cible.get(champ, ""))
            for label, champ in [("Contact", "contact_nom"), ("Email", "contact_email"), ("Tél.", "contact_telephone")]
            if cible.get(champ)
        ]
        if coordonnees:
            texte_contact = " · ".join(f"<b>{label} :</b> {valeur}" for label, valeur in coordonnees)
            bloc.append(Paragraph(texte_contact, contact_style))
        else:
            bloc.append(Paragraph(
                "Coordonnées non trouvées dans la recherche web — à identifier via le site de "
                "l'entreprise ou LinkedIn avant contact.", contact_style,
            ))

        if cible.get("source_url"):
            bloc.append(Spacer(1, 4))
            bloc.append(Paragraph(f"Source à vérifier avant contact : {cible['source_url']}", source_style))

        story.append(KeepTogether(bloc))
        story.append(Spacer(1, 14))

    if not donnees_prospection.get("cibles"):
        story.append(Paragraph(
            "Aucune entreprise n'a pu être identifiée avec certitude à partir de la recherche web. "
            "Essayez avec une ville plus grande ou reformulez votre profil.", corps
        ))

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    doc.build(story)