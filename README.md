# Observateur Actif AI

Studio automatisé de documentaires vidéo pour la chaîne Observateur Actif.

## Objectif éditorial
- Documentaires de 10 à 15 minutes, en 16:9.
- Scènes réellement animées par génération vidéo IA : aucune image fixe utilisée comme substitut à une scène vidéo.
- Narration française masculine.
- Distinguer clairement faits établis, hypothèses, témoignages, traditions orales et légendes.
- Publication visée : chaque samedi à 16 h (heure du Mali, UTC+0), après contrôle qualité.

## État du projet
Cette version comprend la configuration, le schéma de storyboard, le chargement et la validation de projets JSON, le client vidéo Agnes expérimental et les tests automatisés. La génération réelle reste dépendante de la disponibilité et des paramètres effectifs de l'API Agnes.

## Architecture
1. Collecte de pistes depuis des flux RSS/Atom configurables.
2. Ouverture et vérification des sources originales ; classement des affirmations.
3. Script et storyboard structurés.
4. Fournisseur vidéo interchangeable (Agnes candidat à tester).
5. Narration, montage FFmpeg et sous-titres.
6. Contrôle qualité, puis publication YouTube.

## Démarrage local
Python 3.11 ou supérieur recommandé.

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m observateur_actif doctor
```

La commande `doctor` vérifie l'environnement. `research-rss` collecte des pistes dans les flux configurés. `validate-project chemin/vers/projet.json` valide un projet documentaire JSON sans appeler de service externe.


## Collecter des pistes documentaires

Le fichier `config/research_feeds.json` contient les flux RSS/Atom à consulter. Tu peux ajouter ou retirer des éditeurs en modifiant cette liste.

```bash
observateur research-rss
```

Le résultat est écrit dans `projects/research_leads.json`. Chaque élément porte le statut `lead_unverified` : un titre RSS ou un résumé ne constitue jamais une preuve. Il faut ouvrir la publication originale, vérifier les affirmations, dater les informations et recouper avec d'autres sources indépendantes avant de rédiger le documentaire.

Pour utiliser un autre fichier ou choisir le résultat :
```bash
observateur research-rss --feeds config/research_feeds.json --output projects/pistes.json
```

Les URL de flux peuvent changer selon les éditeurs ; si un flux échoue, remplace son URL par celle publiée dans la page officielle de l'éditeur. Le collecteur ne contourne aucun paywall et ne considère pas automatiquement un éditeur comme fiable pour toutes les affirmations.

## Configuration
Copier `.env.example` vers `.env`. Ne jamais publier le fichier `.env`, les clés API ou les jetons YouTube.

## Gratuité
Aucun service payant ni aucune carte bancaire ne sont requis pour exécuter les outils locaux de cette première étape. Les quotas et conditions des services externes doivent être confirmés avant leur activation.

## Tester le moteur vidéo Agnes (local)

1. Créer une clé API gratuite depuis le portail Agnes : https://platform.agnes-ai.com
2. Sous Windows PowerShell, créer et activer l’environnement puis installer le projet :
   ```powershell
   py -m venv .venv
   .venv\\Scripts\\Activate.ps1
   pip install -e .
   Copy-Item .env.example .env
   notepad .env
   ```
3. Dans `.env`, définir :
   ```dotenv
   VIDEO_PROVIDER=agnes
   AGNES_API_KEY=COLLER_LA_CLE_ICI
   ```
4. Installer les dépendances et lancer un clip de test :
   ```bash
   pip install -e .
   observateur video-test --prompt "A slow cinematic aerial shot over a misty African valley at sunrise, trees moving gently in the wind" --seconds 5
   ```
5. Le résultat est enregistré dans `output/agnes_test.mp4`.

Ne jamais envoyer la clé API dans une conversation, un commit, une capture d'écran ou un fichier suivi par Git. Le fichier `.env` est exclu par `.gitignore`.

Le client vidéo est configuré pour demander du 720p. En cas de réponse HTTP 503 indiquant explicitement que la file est pleine, il effectue au maximum deux nouvelles tentatives (30 puis 60 secondes). Les tests automatisés simulent l'API et ne prouvent pas qu'une génération réelle aboutira. Le coût et les quotas du fournisseur doivent être vérifiés dans le compte Agnes.


## Vérifier le registre des affirmations

Le registre JSON sépare le statut éditorial de la décision de revue. Une affirmation ne peut être déclarée `verified` que si :
- une personne responsable a explicitement approuvé la revue et indiqué son nom et la date ;
- au moins deux sources favorables sont référencées ;
- ces sources ont des éditeurs et des domaines distincts.

Exemple de structure (à adapter avec de vraies références) :

```json
{
  "sources": [
    {
      "id": "archive-1",
      "title": "Titre du document d'archive",
      "url": "https://archives.example.org/document",
      "publisher": "Archives A",
      "accessed_at": "2026-11-27",
      "supports_claim": true
    }
  ],
  "claims": [
    {
      "id": "claim-1",
      "statement": "Texte précis de l'affirmation à examiner.",
      "status": "unconfirmed",
      "source_ids": ["archive-1"],
      "notes": "À recouper avant utilisation.",
      "review_decision": "pending"
    }
  ]
}
```

Lancer le contrôle :

```bash
observateur validate-claims projects/claims.json
```

Cette commande contrôle la structure, les liens entre affirmations et sources, et les exigences minimales de revue. Elle ne télécharge pas les pages et ne prouve pas que les sources sont exactes, indépendantes dans leur contenu ou correctement interprétées. Deux domaines différents ne suffisent pas, à eux seuls, à établir la vérité : la vérification humaine des documents originaux reste obligatoire. Les affirmations non examinées doivent rester `unconfirmed`, `hypothesis`, `testimony`, `oral_tradition` ou `legend` selon leur nature.


## Ouvrir une source originale

Après avoir repéré une piste avec `research-rss`, extraire le texte d'un article public :

```bash
observateur fetch-source "https://exemple.org/article" --output projects/article.json
```

Le module refuse les hôtes résolus vers des adresses privées ou locales, les ports non standards, les redirections et les contenus qui ne sont pas HTML. Le téléchargement est limité à 2 Mio et utilise un délai maximal de 15 secondes. Il n'exécute pas le JavaScript, ne contourne pas les paywalls et n'essaie pas de télécharger les images ou autres ressources de la page.

Le résultat contient le titre, le texte extrait, l'URL et la date de collecte. Son statut reste toujours `source_text_unverified` : l'extraction ne confirme ni la véracité, ni la fiabilité, ni l'indépendance de la source. Vérifier le document original et recouper chaque affirmation avant toute utilisation.


## Ouvrir automatiquement un petit lot de pistes RSS

Après la collecte, l'agent peut ouvrir les articles originaux, un par un, sans interrompre le lot lorsqu'un article est inaccessible :

```bash
observateur research-rss
observateur fetch-leads --input projects/research_leads.json --output projects/source_documents.json --limit 5
```

La limite est comprise entre 1 et 20 articles par exécution (5 par défaut). Les doublons d'URL sont ignorés. Chaque résultat indique `fetch_status` (`success` ou `failed`) et conserve les erreurs éventuelles. Les textes obtenus portent toujours le statut `source_text_unverified` : cette étape prépare le travail de vérification, elle ne valide aucun fait.


## Extraire des phrases candidates à vérifier

Après la lecture des articles, l'outil peut repérer des phrases factuelles potentielles dans les textes collectés :

```bash
observateur extract-claims --input projects/source_documents.json --output projects/claim_candidates.json --max-per-source 30
```

Cette extraction est déterministe et locale : elle n'appelle aucun modèle externe. Elle conserve les phrases candidates et leur source d'origine, avec les statuts `unconfirmed` et `pending`. La source d'où provient une phrase est enregistrée avec `supports_claim: false` : elle atteste que la publication contient cette phrase, mais ne compte pas comme corroboration indépendante pour déclarer l'affirmation vérifiée. Les phrases doivent être contrôlées dans leur contexte, puis recoupées avec des documents indépendants. Le moteur peut manquer des formulations ou sélectionner des phrases qui ne sont pas des affirmations pertinentes ; une revue humaine reste indispensable.

Le registre produit peut être contrôlé avec :

```bash
observateur validate-claims projects/claim_candidates.json
```

Aucune phrase n'est automatiquement transformée en fait établi.


## Préparer la revue humaine

Pour transformer le registre de phrases candidates en dossier de travail lisible, générer une file de revue Markdown :

```bash
observateur review-queue --input projects/claim_candidates.json --output projects/editorial_review.md
```

Le rapport regroupe chaque affirmation en attente, ses liens vers les sources, leur éditeur et une liste de contrôles à effectuer : contexte complet, dates, lieux, chiffres, indépendance des publications et catégorie éditoriale. Le rapport ne modifie pas le registre et n'approuve aucune affirmation. Après enquête, les décisions doivent être saisies dans le registre JSON puis contrôlées avec `validate-claims`. Une source extraite automatiquement est marquée non favorable par défaut ; le réviseur doit examiner le document et renseigner honnêtement les éléments de preuve avant de la considérer comme favorable.


## Exporter la narration et les sous-titres

À partir d'un projet JSON dont le storyboard est validé, générer un texte de voix off et un fichier de sous-titres SRT :

```bash
observateur export-narration projects/documentary.json --text output/narration.txt --subtitles output/subtitles.srt
```

Le texte rassemble les répliques dans l'ordre des scènes et rappelle la direction vocale prévue : voix française masculine, grave et posée. Le fichier SRT utilise les durées de chaque scène pour calculer les horodatages. Cet export prépare les fichiers pour une future étape de synthèse vocale ; il ne crée pas encore de voix audio et la synchronisation devra être ajustée après le montage réel.
