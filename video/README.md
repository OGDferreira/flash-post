# Vídeo promocional do FlashPost (Reels/TikTok)

VSL de ~66 s em 1080×1920 feito 100% em código. As telas são recriadas em React
(Remotion) com as cores, a fonte e os textos reais do app; a música e os efeitos
são sintetizados em `audio/synth.py` (sem direitos de terceiros).

## Como gerar

```bash
npm install
pip install edge-tts numpy scipy
npm run build        # narração → música/SFX → render → mixagem
# saída: out/flashpost-reels.mp4
```

Etapas separadas:

- `audio/script.json`: roteiro (texto de cada cena e efeitos sonoros, ancorados em palavras faladas).
- `npm run narrate`: gera a voz (pt-BR-AntonioNeural) e `src/timeline.json`; a duração de cada cena segue a fala.
- `npm run studio`: abre o editor do Remotion para ajustar as animações.
- `npm run music`: gera `out/audio/music.wav` (batida entra no "Conheça o FlashPost") e `sfx.wav`.
- `npm run render` + `npm run mix`: renderiza o vídeo mudo e mixa voz, música (com ducking) e efeitos em -14 LUFS.

Para usar uma gravação própria, substitua os `.mp3` em `public/voice/` mantendo os nomes.
Os `.json` ao lado guardam o tempo de cada palavra (legendas e efeitos) e precisam ser
refeitos para a nova gravação, por exemplo com Whisper.
