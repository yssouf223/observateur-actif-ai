"""Observateur Actif - agent quotidien de YouTube Shorts (histoires insolites d'Afrique)."""
import os, json, asyncio, textwrap, random, urllib.parse, glob, wave
from datetime import datetime

import feedparser, requests, edge_tts
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy import (VideoFileClip, AudioFileClip, ImageClip, ColorClip,
                     CompositeVideoClip, CompositeAudioClip, concatenate_videoclips)
from moviepy.audio.fx import AudioLoop

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
VOICE = os.getenv("TTS_VOICE", "fr-FR-HenriNeural")
PRIVACY = os.getenv("PRIVACY_STATUS", "private")  # passer à "public" quand tout marche
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920
USED_FILE = "used.json"
QUERIES = ["mystère Afrique", "phénomène étrange Afrique",
           "légende africaine insolite", "découverte insolite Afrique",
           "histoire étrange Afrique"]


def load_used():
    if os.path.exists(USED_FILE):
        return json.load(open(USED_FILE, encoding="utf-8"))
    return []


def fetch_candidates():
    items, seen = [], set()
    for q in QUERIES:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=fr&gl=FR&ceid=FR:fr")
        for e in feedparser.parse(url).entries[:8]:
            if e.title in seen:
                continue
            seen.add(e.title)
            items.append({"title": e.title, "link": e.link,
                          "summary": getattr(e, "summary", "")[:300]})
    return items


def write_script(candidates, used_titles):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"""Tu es le scénariste de la chaîne YouTube « Observateur Actif ».
Voici des titres d'actualité récents sur l'Afrique :
{json.dumps(candidates, ensure_ascii=False)}

Histoires déjà publiées (à éviter) : {json.dumps(used_titles[-40:], ensure_ascii=False)}

Choisis UNE histoire étrange, mystérieuse ou insolite. Règles strictes :
- Ne t'appuie que sur les faits présents dans les titres/résumés. N'invente rien.
- Si c'est une légende ou une croyance, dis-le (« selon la légende »).
- Script en français, 90 à 110 mots (environ 40 secondes), accroche choc dès la 1re phrase,
  phrases courtes, termine par une question qui pousse à commenter.
Réponds UNIQUEMENT en JSON avec ces clés :
title (max 70 caractères), script, keywords_en (liste de 5 mots-clés anglais
pour chercher des vidéos de fond verticales : ambiances, paysages, pas de personnes précises),
description (2 phrases), hashtags (liste de 4 hashtags), source_url."""
    resp = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config={"response_mime_type": "application/json"})
    return json.loads(resp.text)


def make_voice(text, path="voice.mp3"):
    asyncio.run(edge_tts.Communicate(text, VOICE, rate="+5%").save(path))
    return path


def fetch_stock(keywords, max_files=8):
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    paths = []
    for kw in keywords:
        r = requests.get("https://api.pexels.com/videos/search", headers=headers,
                         params={"query": kw, "orientation": "portrait", "per_page": 5},
                         timeout=30)
        vids = r.json().get("videos", [])
        random.shuffle(vids)
        for v in vids[:2]:
            files = [f for f in v["video_files"] if f.get("width") and f["width"] < f["height"]]
            if not files:
                continue
            best = sorted(files, key=lambda f: abs(f["height"] - H))[0]
            p = f"stock_{len(paths)}.mp4"
            with open(p, "wb") as fh:
                fh.write(requests.get(best["link"], timeout=120).content)
            paths.append(p)
            if len(paths) >= max_files:
                return paths
    return paths


def make_music(dur, path="music_gen.wav"):
    """Génère une ambiance sombre/mystérieuse 100 % libre de droits (aucun téléchargement)."""
    sr = 44100
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sig = np.zeros_like(t)
    for f, a in [(55, 1.0), (82.4, 0.7), (110, 0.5), (164.8, 0.3), (220.5, 0.15)]:
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * random.uniform(0.05, 0.15) * t
                                 + random.uniform(0, 6.28))
        sig += a * lfo * np.sin(2 * np.pi * f * t)
    sig += 0.02 * np.random.randn(len(t))
    sig *= np.minimum(1, np.minimum(t / 2, (dur - t) / 2))
    sig = sig / np.max(np.abs(sig)) * 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())
    return path


def get_music(dur):
    """Utilise vos fichiers du dossier music/ s'il y en a, sinon génère une ambiance."""
    mine = glob.glob("music/*.mp3") + glob.glob("music/*.wav")
    if mine:
        clip = AudioFileClip(random.choice(mine)).with_effects([AudioLoop(duration=dur)])
    else:
        clip = AudioFileClip(make_music(dur))
    return clip.with_volume_scaled(0.10)


def notify(text):
    """Alerte Telegram (optionnelle, gratuite)."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=20)
    except Exception as e:
        print("Alerte non envoyée :", e)


def caption_clip(text, start, dur):
    font = ImageFont.truetype(FONT, 74)
    lines = textwrap.wrap(text.upper(), 16)
    img = Image.new("RGBA", (W, 130 * len(lines) + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        w = d.textlength(line, font=font)
        d.text(((W - w) / 2, 10 + i * 130), line, font=font, fill="white",
               stroke_width=8, stroke_fill="black")
    return (ImageClip(np.array(img)).with_start(start).with_duration(dur)
            .with_position(("center", 1200)))


def build_video(script, voice_path, keywords, out="short.mp4"):
    audio = AudioFileClip(voice_path)
    dur = audio.duration
    base = []
    for p in fetch_stock(keywords):
        c = VideoFileClip(p).without_audio().resized(height=H)
        if c.w < W:
            c = c.resized(width=W)
        c = c.cropped(x_center=c.w / 2, y_center=c.h / 2, width=W, height=H)
        base.append(c.subclipped(0, min(c.duration, 6)))
    if not base:
        raise RuntimeError("Aucune vidéo de fond trouvée")
    seq, total, i = [], 0, 0
    while total < dur:
        c = base[i % len(base)]
        seq.append(c); total += c.duration; i += 1
    bg = concatenate_videoclips(seq, method="compose").subclipped(0, dur)
    dark = ColorClip((W, H), color=(0, 0, 0)).with_opacity(0.3).with_duration(dur)

    words = script.split()
    chunks = [" ".join(words[k:k + 4]) for k in range(0, len(words), 4)]
    weights = [len(c) for c in chunks]
    t, caps = 0.0, []
    for c, w in zip(chunks, weights):
        d = dur * w / sum(weights)
        caps.append(caption_clip(c, t, d))
        t += d

    mixed = CompositeAudioClip([audio, get_music(dur)]).with_duration(dur)
    final = CompositeVideoClip([bg, dark] + caps, size=(W, H)).with_audio(mixed)
    final.write_videofile(out, fps=30, codec="libx264", audio_codec="aac",
                          preset="veryfast", threads=2)
    return out


def upload(path, data):
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"],
                        client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    tags = [h.lstrip("#") for h in data.get("hashtags", [])] + ["Shorts", "Afrique", "mystère"]
    desc = (data["description"] + "\n\nSource : " + data.get("source_url", "") + "\n\n"
            + " ".join(data.get("hashtags", [])) + " #Shorts\n\n"
            "Vidéo réalisée avec l'aide de l'IA (voix et montage automatisés).")
    body = {"snippet": {"title": data["title"][:90], "description": desc,
                        "tags": tags, "categoryId": "24", "defaultLanguage": "fr"},
            "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    url = "https://youtube.com/shorts/" + resp["id"]
    print("Publié :", url)
    return url


def main():
    used = load_used()
    cands = fetch_candidates()
    if not cands:
        raise SystemExit("Aucune actualité trouvée")
    data = write_script(cands, [u["title"] for u in used])
    print("Sujet :", data["title"])
    voice = make_voice(data["script"])
    video = build_video(data["script"], voice, data["keywords_en"])
    url = upload(video, data)
    notify(f"✅ Observateur Actif : nouveau Short ({PRIVACY})\n{data['title']}\n{url}")
    used.append({"title": data["title"], "url": data.get("source_url", ""),
                 "date": datetime.utcnow().isoformat()})
    json.dump(used, open(USED_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
