# NOTE: verificação do render (out/flashpost-20s.mp4)

- 1080×1920, 30 fps, 21,0 s, H.264 + AAC, -13,9 LUFS, pico -1,6 dBFS.
- Gates do Motionmaxxing (`look.py`, `lint.mjs`):
  - G0 PASS: duração 21,00 s = esperado; áudio presente.
  - G2 PASS: nenhuma sequência > 3 quadros parados.
  - G3 PASS: final em movimento (0,53 s de pausa); último plano 2,10 s = 10 % do filme.
  - G5 PASS: sem rótulos de canto, contadores, cabeçalhos ou cards genéricos.
  - G1 (legibilidade) e G4 (um destaque por quadro): avaliados a olho na folha `look/sheet.jpg`.
    O texto da interface fica entre 30 e 58 px, menor que o alvo de 0,04 da altura que a skill recomenda.
    A câmera aproxima nas cenas principais, mas os textos pequenos dos cards são de apoio, não de leitura obrigatória.
- Sincronia: a transcrição do MP4 final (Whisper) bate com o roteiro, e as palavras caem nos quadros do `beats.json` (±0,1 s).
- Dados ilustrativos: nomes (Ana, Bia, Carol, Lucas), @contas e números são exemplos, não dados reais.
- Correções feitas durante a revisão: cenas escondidas vazavam cards de vidro (troca de visibilidade por opacidade);
  palavras desalinhadas (fixedSlots:false); três trechos com tela vazia após o corte; "Escale" sobre o card de Aparência;
  a palavra "Escale" saía como "Escalhe", então a frase foi regerada clonando a mesma voz e emendada.
