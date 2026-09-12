# Bilan de Valeur

**Transformez votre profil sportif en dossier de sponsoring professionnel, prêt à envoyer, en quelques secondes.**

Projet réalisé dans le cadre du hackathon FounderRace (24h) — thème Intelligence Artificielle &
Productivité. Inspiré d'un projet de plateforme B2B de sponsoring sportif porté avant le hackathon ;
ce MVP en constitue la première brique concrète.

## Le problème

Les sportifs de haut niveau français (hors élite médiatisée) manquent de temps et de compétences
commerciales pour démarcher des sponsors. Rédiger un dossier de sponsoring professionnel prend des
heures, et la plupart des athlètes n'ont ni les mots ni la mise en forme pour convaincre un dirigeant
de PME. Côté PME, le sponsoring sportif est un levier fiscal sous-utilisé (déduction à 100% des
charges de publicité, contrairement au mécénat plafonné) faute d'un dossier suffisamment carré pour
lever les doutes du dirigeant.

## Ce que fait le MVP

1. L'athlète s'identifie avec son email (sert d'identifiant de compte, voir plus bas).
2. Il renseigne son profil (sport, palmarès, objectif de financement) et peut uploader une capture
   d'écran de ses statistiques réseaux sociaux (lue automatiquement par IA vision).
3. L'IA rédige un dossier structuré : accroche, présentation, proposition de valeur pour l'entreprise,
   et 3 paliers de partenariat avec contreparties suggérées.
4. Chaque Bilan généré est **enregistré dans le compte** (`data/comptes.json`) : l'athlète peut revenir
   plus tard, se ré-identifier avec le même email, et retrouver tous ses Bilans précédents dans
   l'onglet « Mes Bilans » — sans repasser par l'IA pour re-télécharger un PDF déjà généré.
5. Export en PDF professionnel, prêt à envoyer.
6. Lien de paiement pour débloquer le téléchargement (traction "client payant", pas juste "utilisateur
   inscrit").

## Pourquoi un compte, et pourquoi si simple

Le brief du hackathon demande un MVP **SaaS**, pas un simple outil à usage unique : la différence
tient à la persistance des données d'une visite à l'autre. Le compte est volontairement réduit à un
identifiant email, sans mot de passe — une vraie authentification (magic link, OAuth) est la suite
logique évidente, mais construire un système d'auth sécurisé en une nuit de hackathon, sur un projet
qui a déjà pivoté plusieurs fois, aurait été le mauvais arbitrage de temps. Ce choix est assumé et
documenté ici plutôt que caché.

## Choix de scope volontaires (et pourquoi)

- **L'argument fiscal est un texte fixe, pas généré par l'IA.** Un LLM qui invente un taux ou une
  condition fiscale précise est un risque réel (fausse assurance donnée à un dirigeant de PME). Le
  paragraphe sur l'article 39 du CGI est écrit une fois pour toutes dans le code, avec une mention
  explicite que ce n'est pas un conseil fiscal personnalisé.
- **Pas de mise en relation automatique avec des PME.** Des plateformes comme GM Sponsoring ou Sponsoo
  font déjà ce matching. Ce MVP ne cherche pas à les concurrencer sur ce terrain : il se concentre sur
  la partie qu'elles ne couvrent pas bien, la préparation du dossier.
- **Les montants proposés sont bornés (500€ à 10 000€)** dans le prompt système, pour éviter qu'un
  profil mal renseigné ne génère un montant absurde.
- **Pas d'escrow / séquestre de paiement ni de génération de contrat.** C'est l'étape suivante de la
  vision produit, qui nécessite une validation juridique que 24h ne permettent pas.

## Lancer le projet en local

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

(Sur Windows, si `streamlit run app.py` seul ne fonctionne pas, utilisez bien `python -m streamlit run
app.py` — voir la note dans le code.)

Il vous faut une clé API Anthropic (console.anthropic.com), à saisir dans la barre latérale — elle
n'est jamais stockée, seulement gardée en mémoire de session.

## Déployer sur Streamlit Community Cloud

1. Poussez ce dépôt sur GitHub.
2. Sur [share.streamlit.io](https://share.streamlit.io), connectez le dépôt et pointez sur `app.py`.
3. Ajoutez votre clé dans **Settings → Secrets** :
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

## Stack technique

- **Front-end** : Streamlit
- **Génération PDF** : ReportLab (Platypus)
- **Moteur IA** : API Anthropic, `claude-sonnet-5` (texte + vision), avec
  `claude-haiku-4-5-20251001` en option.

## Vision au-delà du hackathon

Ce générateur est la première brique d'une infrastructure plus large : standardisation des contrats
de sponsoring, paiement séquestré, et génération automatique du certificat fiscal de prestation
("coffre-fort fiscal"). Ces briques demandent une validation juridique et un partenaire de paiement
agréé — hors scope volontaire de cette nuit de hackathon.

## Traction

Les retours des athlètes testeurs sont enregistrés dans `data/temoignages.json` via le formulaire de
la barre latérale.
