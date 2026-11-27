# Observateur Actif AI

Studio automatisé de documentaires vidéo pour la chaîne Observateur Actif.

## Objectif éditorial
- Documentaires de 10 à 15 minutes, en 16:9.
- Scènes réellement animées par génération vidéo IA : aucune image fixe utilisée comme substitut à une scène vidéo.
- Narration française masculine.
- Distinguer clairement faits établis, hypothèses, témoignages, traditions orales et légendes.
- Publication visée : chaque samedi à 16 h (heure du Mali, UTC+0), après contrôle qualité.

## État du projet
Cette première version pose les fondations : configuration, format de projet, validation des scènes et diagnostic local. Le connecteur vidéo n'est pas encore activé : nous ne coderons pas d'URL d'API ni de paramètres Agnes supposés. Ils seront ajoutés après vérification de la documentation officielle et d'un test réel de l'API.

## Architecture
1. Recherche et registre des sources.
2. Vérification éditoriale et classement des affirmations.
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

Pour le moment, la commande `doctor` vérifie l'environnement. Elle ne génère pas encore de vidéo.

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

Le moteur Flash gratuit renvoie du 720p. Les erreurs de file pleine (HTTP 503) sont signalées sans relance agressive. La génération réelle nécessite une clé valide et n'est pas simulée par les tests automatiques.
