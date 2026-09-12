# Find A Sponsor

**Le dossier de sponsoring que je n'ai jamais eu le temps de me faire, généré en 30 secondes.**

Projet construit en une nuit pour le hackathon FounderRace (24h, thème IA & Productivité).

---

## Pourquoi ce projet existe

Ancien nageur de haut niveau, j'ai passé des années à m'entraîner, à courir après des chronos. Je n'ai jamais eu le temps ni les mots pour démarcher des entreprises et financer ma saison. La plupart des sportifs de haut niveau français sont dans cette situation, en dehors des quelques noms qu'on voit à la télé. Ils ont un vrai palmarès. Ils n'ont aucune idée de comment le transformer en un dossier qui donne envie à un dirigeant de PME de sortir son chéquier.

En face, une PME locale a souvent une vraie bonne raison de sponsoriser. Le sponsoring sportif est déductible à 100% des bénéfices, contrairement au mécénat qui est plafonné. C'est aussi un levier de marque employeur que beaucoup de dirigeants ignorent. Le problème n'est presque jamais la volonté. C'est l'absence d'un dossier professionnel pour démarrer la conversation.

Find A Sponsor répond à ça. Vous entrez votre profil, l'IA rédige le dossier, vous repartez avec un PDF prêt à envoyer.

## Ce que ça fait

- Vous renseignez votre profil : sport, niveau, palmarès, ville, ce que vous êtes prêt à offrir en échange d'un partenariat.
- L'IA (Claude, avec vision) rédige un dossier structuré : accroche, présentation, argument de valeur pour l'entreprise, et 3 paliers de partenariat. Les montants sont calculés à partir de votre niveau et de votre audience, pas devinés au hasard.
- Un PDF professionnel en sort, prêt à envoyer, avec photo et un encart sur le cadre fiscal du sponsoring.
- Une page "Découvrir les athlètes" permet de parcourir les profils inscrits. Seule la bio publique est visible. Le dossier complet, avec les prix et le contact, reste privé.
- Un compte par email permet de retrouver ses Bilans, de les recevoir par mail, ou d'en générer un nouveau.
- Un module de prospection cherche de vraies entreprises locales sur le web via Tavily, au lieu d'en inventer. Chaque suggestion vient avec sa source, pour vérification avant contact.

## Ce qu'on a choisi de ne pas faire, et pourquoi

Cette nuit a été pleine d'idées testées puis écartées. Pas par manque de temps, mais parce qu'elles ne passaient pas un test de rigueur simple. Je le documente ici parce que c'est aussi ça, un vrai travail de produit.

- **Pas de génération automatique de contrat ni de paiement séquestré.** C'est la vision à terme (voir plus bas). Ça touche au droit et à la régulation financière. Ce n'est pas quelque chose qu'on bricole en une nuit sans avocat.
- **Pas de liste d'entreprises avec emails et numéros de téléphone inventés.** Une IA à qui on demande de trouver des contacts invente des choses qui sonnent vrai mais ne le sont pas. On a préféré une version plus lente mais honnête : de vrais résultats de recherche web, avec la source affichée, jamais un contact fabriqué.
- **Pas de calcul de rétrocessions ni de comptabilité.** Des outils métier existent déjà pour ça (VEGA, Self-med). Pas la peine de mal refaire ce qui est déjà bien fait ailleurs.
- **L'argument fiscal dans le PDF est un texte fixe, pas généré par l'IA.** Un modèle de langage qui invente un chiffre ou un seuil fiscal peut coûter cher à quelqu'un. Cette partie est écrite une fois, vérifiée, et ne change pas.

## Stack technique, et pourquoi Streamlit

- Interface : Streamlit
- PDF : ReportLab
- IA : API Anthropic, Claude Sonnet 5, texte et vision
- Recherche web : Tavily, pour ancrer la prospection sur des résultats réels

Streamlit n'est pas l'architecture qu'aurait ce produit s'il devait scaler à des milliers d'utilisateurs. Une vraie version grand public serait plutôt en Next.js sur Vercel, avec de vraies URLs par profil et une gestion de compte plus robuste. Mais Streamlit permet de construire, tester et itérer très vite. C'est exactement ce dont on avait besoin cette nuit pour valider l'idée avant d'investir dans une vraie architecture. Ce n'est pas un compromis honteux. C'est le bon outil pour la question qu'on se posait ce soir : est-ce que ça a de la valeur, avant de se demander si ça scale.

## Faire tourner le projet en local

Vous trouverez le site à l'adresse suivante : 

## Après le hackathon

Ce MVP est la première brique d'un projet plus large : une infrastructure de sponsoring sportif sans paperasse, avec contrat standardisé, paiement séquestré, et certificat de prestation généré automatiquement pour sécuriser fiscalement l'entreprise. Cette nuit, on a validé la brique la plus simple à tester en 24h : est-ce qu'un athlète gagne vraiment du temps, et est-ce qu'un dossier généré par IA est assez bon pour être envoyé à un vrai dirigeant. La partie juridique et financière est la suite logique, pas une case cochée à la va-vite.

## Pour finir

Ce projet a changé de forme plusieurs fois cette nuit avant d'arriver là. Ce n'est pas un aveu de faiblesse. C'est le signe qu'on a pris le temps de vérifier que l'idée tenait la route avant de foncer dedans. Ce qui reste constant du début à la fin, c'est le problème : des athlètes qui méritent d'être soutenus, et qui n'ont jamais eu le bon outil pour le demander correctement.

Louis
