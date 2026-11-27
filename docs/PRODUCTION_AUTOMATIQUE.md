# Mise en production automatique

## Calendrier

- Mercredi 14:00 UTC : collecte RSS, ouverture des sources et création d'un storyboard brouillon avec Gemini.
- Vendredi 20:00 UTC : contrôle des prérequis, génération des clips Agnes, voix Edge-TTS, sous-titres, montage FFmpeg, contrôle ffprobe et envoi à YouTube.
- YouTube reçoit une vidéo privée programmée pour samedi 16:00 UTC (heure du Mali).

Les workflows sont :
- `.github/workflows/weekly-research-draft.yml`
- `.github/workflows/weekly-production.yml`

## Configuration GitHub Actions

Secrets à configurer dans Settings > Secrets and variables > Actions > Secrets :

- `GEMINI_API_KEY` : clé Google AI Studio pour le brouillon de script.
- `AGNES_API_KEY` : clé du fournisseur de vidéo.
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `YOUTUBE_CHANNEL_ID`

Variables à configurer dans Settings > Secrets and variables > Actions > Variables :

- `GEMINI_FREE_TIER_CONFIRMED=true` : confirme que le projet Gemini utilisé reste sur le palier gratuit.
- `AGNES_FREE_QUOTA_CONFIRMED=true` : confirme que les générations vidéo prévues sont couvertes par un quota gratuit disponible.
- `EDGE_TTS_COMMERCIAL_RIGHTS_CONFIRMED=true` : ne doit être activé qu'après confirmation écrite des droits d'utilisation commerciale de la voix Edge-TTS.

Le client YouTube demande les autorisations OAuth `youtube.upload` et `youtube.readonly` et vérifie l'identifiant de chaîne configuré avant de lancer la génération vidéo. L'application Google Cloud doit avoir l'API YouTube Data activée et disposer d'un OAuth autorisé. Depuis le 2 novembre 2026, YouTube indique que les téléversements de projets API non vérifiés ne sont plus limités au mode privé. La programmation est envoyée avec `privacyStatus=private` et un `publishAt` futur, conformément aux règles YouTube. Voir [OAuth YouTube](https://developers.google.com/youtube/data/guides/authentication) et [ressource vidéo / publishAt](https://developers.google.com/youtube/data/reference/rest/v3/videos).

Les workflows arrêtent le traitement si les variables de gratuité ne sont pas explicitement confirmées. Le code ne peut pas lire de façon fiable le solde ou le statut de facturation privé des comptes fournisseurs. Agnes publie actuellement une promotion gratuite temporaire pour Video 2.5 Flash en 720p, mais ses conditions et quotas peuvent changer ; la file partagée peut aussi renvoyer HTTP 503 « queue full ». Vérifier les conditions dans le [catalogue Agnes](https://github.com/AgnesAI-Labs/skills/blob/main/agnes-ai-models/references/model_catalog.md) et le [suivi des erreurs de file](https://github.com/AgnesAI-Labs/AgnesAI-Models/issues/142) avant chaque activation.

## Contrôle éditorial obligatoire

Le workflow du mercredi produit un brouillon et un dossier Markdown de revue qui rassemble les scènes, les narrations et les liens vers leurs sources. Il force toujours :

- `review_approved=false` pour chaque scène ;
- `release_approved=false` pour le projet ;
- les affirmations à `unconfirmed`, `hypothesis`, `testimony`, `oral_tradition` ou `legend`, jamais à `verified` par le modèle.

La production du samedi refuse un projet tant que chaque scène n'a pas un réviseur et une date d'approbation. La publication YouTube exige en plus `release_approved=true`, `release_reviewer` et `release_approved_at`. Cette barrière ne doit pas être supprimée : un modèle de langage ne prouve pas la vérité d'un récit historique ou mystérieux.

## Résolution et formats

- Les clips Agnes sont demandés en 720p.
- FFmpeg assemble le documentaire en H.264/AAC, 1280×720, 25 fps.
- Le SRT issu des événements temporels Edge-TTS est inclus comme piste sélectionnable.
- La voix est normalisée par FFmpeg autour de -16 LUFS avec un plafond de -1,5 dBTP ; la musique facultative est mixée à bas niveau sous la narration.
- ffprobe vérifie les flux, les codecs, la résolution et la durée.
- Le contrôle technique ne remplace pas l'écoute, le visionnage complet, le contrôle des sources et le contrôle des droits.

## Commandes

Le moteur de brouillon utilise Gemini 3.8 Flash via la Developer API. Le palier gratuit dépend des quotas et de l'éligibilité du projet ; sur le palier gratuit, Google indique que le contenu peut être utilisé pour améliorer ses produits. N'envoyer que des documents publics, jamais des données confidentielles. Voir [tarifs Gemini](https://ai.google.dev/gemini-api/docs/pricing).


```bash
observateur research-rss
observateur fetch-leads --input projects/research_leads.json --output projects/source_documents.json --limit 20
observateur draft-project --sources projects/source_documents.json --output projects/weekly_documentary.json
observateur review-project projects/weekly_documentary.json --output projects/editorial_review.md
observateur produce projects/weekly_documentary.json --output-dir output
observateur quality-check output/documentary.mp4
observateur publish-youtube projects/weekly_documentary.json --video output/documentary.mp4
```

## Limites externes connues

- L'API Agnes a déjà renvoyé HTTP 503 « queue full » pendant les essais. Le client réessaie, mais aucune génération API complète n'est considérée comme validée tant qu'un vrai MP4 n'a pas été obtenu.
- Edge-TTS a généré un MP3 réel et un SRT avec événements `WordBoundary` lors du test réel GitHub Actions du 27 novembre 2026. Le test vérifie la présence des horodatages ; une écoute et une relecture éditoriale du résultat complet restent nécessaires. Les droits commerciaux du service Edge-TTS ne sont pas confirmés dans ce projet.
- La publication YouTube exige un OAuth valide et le bon identifiant de chaîne. La programmation utilise le statut privé avec `publishAt`; Google n'autorise ce champ que pour une vidéo privée jamais publiée et une date future.
- Le quota gratuit Gemini et le quota gratuit Agnes dépendent des comptes. Les variables de confirmation sont des garde-fous déclaratifs, pas une lecture automatique du solde.
- Le workflow du samedi ne démarre pas si `projects/weekly_documentary.json` est absent ou non approuvé. Aucun contenu non vérifié ne sera publié automatiquement.
