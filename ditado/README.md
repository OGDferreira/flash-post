# Ditado: segure Ctrl+Shift e fale

Programa que fica rodando em segundo plano no computador. Funciona assim:

1. Clique na caixa de texto onde quer escrever (Claude, ChatGPT, Gemini,
   Google, WhatsApp Web, Word, qualquer app).
2. **Segure Ctrl+Shift** e fale. Um bipe agudo indica que começou a gravar
   e o ícone na bandeja fica vermelho.
3. **Solte** as teclas. O texto transcrito é colado na caixa selecionada.

A transcrição usa o **Whisper rodando no seu próprio computador**: é grátis,
funciona sem internet (depois de baixar o modelo uma vez) e seu áudio não sai
da máquina.

## Instalação no Windows

1. Instale o [Python 3.10 ou mais novo](https://www.python.org/downloads/).
   Na instalação, marque **"Add python.exe to PATH"**.
2. Baixe esta pasta `ditado/` para o seu computador.
3. Dê dois cliques em **`instalar.bat`**. Ele instala tudo e baixa o modelo de
   voz (~500 MB, só na primeira vez).
4. Dê dois cliques em **`iniciar.bat`**. Um ícone de microfone aparece perto do
   relógio (pode estar escondido na setinha `^`). Verde quer dizer pronto.
5. (Opcional) Dê dois cliques em **`iniciar_com_windows.bat`** para o Ditado
   abrir sozinho toda vez que ligar o PC.

## Instalação no macOS / Linux

```bash
./instalar.sh
```

```bash
.venv/bin/python ditado.py
```

- **macOS:** em Ajustes do Sistema → Privacidade e Segurança, libere o Terminal
  (ou o app que roda o Python) em **Acessibilidade**, **Monitoramento de
  Entrada** e **Microfone**.
- **Linux:** funciona em sessões X11. No Wayland a captura global de teclado é
  bloqueada pelo sistema. Pode ser preciso instalar `libportaudio2`.

## Cores do ícone

| Cor      | Significado                          |
|----------|--------------------------------------|
| Cinza    | Carregando o modelo, pausado ou erro |
| Verde    | Pronto: segure Ctrl+Shift            |
| Vermelho | Gravando                             |
| Amarelo  | Transcrevendo                        |

Clique com o botão direito no ícone para pausar, abrir as configurações, ver o
log ou sair.

## Configurações

Na primeira execução é criado o arquivo `~/.ditado/config.json`
(no Windows: `C:\Users\SEU_USUARIO\.ditado\config.json`). Edite e reinicie o
Ditado.

| Opção               | Padrão                     | O que faz |
|---------------------|----------------------------|-----------|
| `model`             | `small`                    | Modelo do Whisper. `base` é mais rápido e erra mais; `medium` é mais preciso e mais lento. Com placa NVIDIA, use `large-v3-turbo`. |
| `language`          | `pt`                       | Idioma falado. Deixe `""` para detectar sozinho. |
| `device`            | `auto`                     | `cpu`, `cuda` (placa NVIDIA) ou `auto`. |
| `hold_delay_ms`     | `250`                      | Quanto tempo segurar Ctrl+Shift antes de valer. Evita disparar em atalhos como Ctrl+Shift+T. |
| `min_audio_ms`      | `400`                      | Gravações mais curtas são ignoradas. |
| `trailing_space`    | `true`                     | Põe um espaço no fim, para emendar vários ditados. |
| `beeps`             | `true`                     | Bipes de início e fim. |
| `restore_clipboard` | `true`                     | Devolve o que estava copiado antes. |
| `microphone`        | `""`                       | Parte do nome do microfone. Liste com `python ditado.py --list-mics`. |
| `initial_prompt`    | frase em pt-BR             | Dica para o Whisper. Coloque nomes que ele erra, ex.: `"Claude, Gemini, ChatGPT, Flash Post."` |
| `engine`            | `local`                    | `openai` usa a API da OpenAI no lugar do modelo local (pago, mas leve para PCs fracos). Precisa de `pip install openai` e da variável `OPENAI_API_KEY`. |

## Dicas e problemas comuns

- **O atalho não funciona em alguns apps (Windows).** Se o app foi aberto
  "como administrador", o Ditado também precisa rodar como administrador.
- **Ctrl+Shift troca o idioma do teclado (Windows).** Isso acontece se você tem
  mais de um layout de teclado. Desative em Configurações → Hora e idioma →
  Digitação → Teclas de atalho de idioma de entrada.
- **Demora para aparecer o texto.** Troque `model` para `base`, ou use
  `large-v3-turbo` com `device: cuda` se tiver placa NVIDIA.
- **Usar fone Bluetooth** como microfone pode baixar a qualidade do som do fone
  enquanto grava. Isso é normal do Bluetooth.
- **Ver o que está acontecendo:** rode `python ditado.py --no-tray -v` em um
  terminal, ou abra o log em `~/.ditado/ditado.log`.

## Como funciona

- `pynput` escuta o teclado. O atalho só vale se Ctrl e Shift estiverem
  pressionados **sozinhos**: se outra tecla entrar no meio, a gravação é
  descartada.
- A gravação começa no instante em que você aperta, para não cortar o começo da
  fala. O bipe só toca depois de `hold_delay_ms`.
- Ao soltar, `faster-whisper` transcreve o áudio e o texto é colado com Ctrl+V
  (Cmd+V no Mac). Colar em vez de "digitar" garante acentos corretos e é
  instantâneo em qualquer app.

## Testes

```bash
pip install pytest
```

```bash
python -m pytest tests
```
