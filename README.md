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
