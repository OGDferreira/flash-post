# FlashPost: vídeo de 20 s (Reels/TikTok, 1080×1920)

Feito com a skill **Motionmaxxing** (motor de animação GSAP, captura da marca, verificadores de qualidade)
e narração gerada localmente com o **VoiceStudio** (VoxCPM2, voz criada do zero, licença Apache-2.0).

## Estrutura

| Caminho | O que é |
|---|---|
| `film/index.html` | O filme. Cada animação está presa ao quadro de uma palavra falada (`film/beats.js`). |
| `film/vo/` | Narração: `script.txt`, `take1.wav` (voz), `fix11.wav` (frase "Escale sua oferta" refeita), `vo_fast.wav` (versão final, 7% mais rápida), `words.json` (tempos das palavras). |
| `film/beats.json` | Tabela de sincronia gerada pelo `sync.mjs` do Motionmaxxing. |
| `film/brand/` | Cores, fonte e logo capturados de flashpost.onrender.com (`brand.mjs`). |
| `film/audio/` | Trilha, efeitos e `events.json` (quadro de cada efeito) e a mixagem `mix.wav`. |
| `audio/build_audio.py` | Gera trilha e efeitos por código (sem direitos de terceiros). |
| `out/flashpost-20s.mp4` | Vídeo final. |

## Refazer

```bash
SK=~/.claude/skills/motionmaxxing
# 1. voz (VoiceStudio rodando em localhost:3900)
curl -X POST localhost:3900/generate -F "text=$(cat film/vo/script.txt)" -F language=pt -F engine=voxcpm2 \
  -F "instruct=Homem brasileiro de uns 30 anos, voz grave, calorosa e confiante..." -F seed=7 -o film/vo/take1.wav
# 2. tempos das palavras (Whisper do VoiceStudio) -> film/vo/words.json, depois:
node $SK/scripts/sync.mjs film/vo/words.json --fps 30 --lead 2 --out film/beats.json
# 3. áudio e mixagem
python3 audio/build_audio.py
(cd film && python3 $SK/scripts/mix.py --duration 21 --out audio/mix.wav --vo vo/vo_fast.wav@0.30 \
  --music audio/music.wav --music-gain -17 --events audio/events.json --duck --duck-db 9 --lufs -14)
# 4. render (como root, o Chrome precisa de --no-sandbox: CHROME_PATH aponta para um wrapper)
(cd film && CHROME_PATH=~/.local/bin/chrome-nosandbox node $SK/scripts/render.mjs index.html ../out/flashpost-20s.mp4 \
  --audio audio/mix.wav --grain 0.035)
```

Para ajustar uma cena, edite `film/index.html` e confira quadros soltos com
`node $SK/scripts/render.mjs index.html --still 2.7,8.3,16.8 stills`.
