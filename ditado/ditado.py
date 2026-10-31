"""Ditado: segure Ctrl+Shift, fale, solte, e o texto aparece onde o cursor está.

Roda em segundo plano (ícone na bandeja). Enquanto Ctrl+Shift estiver
pressionado (sem nenhuma outra tecla), grava o microfone. Ao soltar, transcreve
a fala e cola o texto no campo selecionado do app aberto (Claude, ChatGPT,
Gemini, Google, Word, etc.).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable, Optional

APP_DIR = Path.home() / ".ditado"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "ditado.log"
SAMPLE_RATE = 16_000
STALE_KEY_SECONDS = 60

log = logging.getLogger("ditado")


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    # "local" usa o Whisper no seu computador (grátis, offline).
    # "openai" usa a API da OpenAI (precisa de OPENAI_API_KEY, é pago).
    engine: str = "local"
    # Modelos locais: tiny, base, small, medium, large-v3, large-v3-turbo.
    # "small" é um bom equilíbrio para CPU; com placa NVIDIA use "large-v3-turbo".
    model: str = "small"
    openai_model: str = "gpt-4o-mini-transcribe"
    language: str = "pt"
    # "auto", "cpu" ou "cuda".
    device: str = "auto"
    # Tempo segurando Ctrl+Shift antes de começar a valer, para não disparar
    # quando você usa atalhos como Ctrl+Shift+T.
    hold_delay_ms: int = 250
    # Gravações mais curtas que isso são ignoradas.
    min_audio_ms: int = 400
    # Adiciona um espaço no fim do texto, para emendar ditados seguidos.
    trailing_space: bool = True
    beeps: bool = True
    # Restaura o que estava na área de transferência depois de colar.
    restore_clipboard: bool = True
    # Nome (ou parte do nome) do microfone. Vazio = microfone padrão.
    microphone: str = ""
    # Palavras/nomes que o Whisper deve reconhecer melhor (ex.: "Claude, Gemini").
    initial_prompt: str = "Transcrição em português do Brasil, com pontuação."

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                known = {f.name for f in fields(cls)}
                for key, value in data.items():
                    if key in known:
                        setattr(cfg, key, value)
            except (OSError, ValueError) as exc:
                log.warning("Não consegui ler %s: %s", CONFIG_PATH, exc)
        else:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return cfg


# --------------------------------------------------------------------------- #
# Detecção do atalho (segurar Ctrl+Shift sozinhos)
# --------------------------------------------------------------------------- #
class HoldDetector:
    """Máquina de estados do "segure Ctrl+Shift para falar".

    - Ctrl e Shift pressionados, sem outra tecla -> ``on_arm`` (começa a gravar).
    - Depois de ``hold_delay`` segundos ainda assim -> ``on_confirm``.
    - Qualquer outra tecla durante o atalho -> ``on_cancel`` (era um atalho
      normal, como Ctrl+Shift+T).
    - Soltou Ctrl ou Shift -> ``on_release`` se já confirmado, senão ``on_cancel``.

    Independe do pynput para poder ser testada: recebe nomes de tecla
    normalizados ("ctrl", "shift" ou qualquer outra string).
    """

    def __init__(
        self,
        hold_delay: float,
        on_arm: Callable[[], None],
        on_confirm: Callable[[], None],
        on_release: Callable[[], None],
        on_cancel: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hold_delay = hold_delay
        self.on_arm = on_arm
        self.on_confirm = on_confirm
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.clock = clock
        self.down: set[str] = set()
        self.down_at: dict[str, float] = {}
        self.state = "idle"  # idle | armed | active | blocked
        self.armed_at = 0.0

    def key_down(self, key: str) -> None:
        if key in self.down:  # repetição automática do teclado
            return
        self.down.add(key)
        self.down_at[key] = self.clock()
        if key not in ("ctrl", "shift"):
            if self.state in ("armed", "active"):
                self.state = "blocked"
                self.on_cancel()
            elif self.state == "idle" and self.down & {"ctrl", "shift"}:
                self.state = "blocked"
            return
        if self.state == "idle" and self.down == {"ctrl", "shift"}:
            self.state = "armed"
            self.armed_at = self.clock()
            self.on_arm()

    def key_up(self, key: str) -> None:
        self.down.discard(key)
        self.down_at.pop(key, None)
        if key in ("ctrl", "shift"):
            if self.state == "active":
                self.on_release()
            elif self.state == "armed":
                self.on_cancel()
            if self.state != "blocked" or not (self.down & {"ctrl", "shift"}):
                self.state = "idle"
        if not self.down:
            self.state = "idle"

    def tick(self) -> None:
        """Chamado periodicamente; confirma o atalho após o atraso."""
        now = self.clock()
        if self.state != "active":
            # Se um "soltar tecla" se perdeu (ex.: tela bloqueada), esquece a
            # tecla depois de um tempo para o atalho não ficar travado.
            for key, since in list(self.down_at.items()):
                if now - since > STALE_KEY_SECONDS:
                    self.down.discard(key)
                    del self.down_at[key]
            if not self.down:
                self.state = "idle"
        if self.state == "armed" and self.clock() - self.armed_at >= self.hold_delay:
            self.state = "active"
            self.on_confirm()


# --------------------------------------------------------------------------- #
# Áudio
# --------------------------------------------------------------------------- #
class Recorder:
    def __init__(self, microphone: str = "") -> None:
        import sounddevice as sd  # importação tardia: só necessária em runtime

        self.sd = sd
        self.device = self._find_device(microphone) if microphone else None
        self.stream = None
        self.chunks: list = []
        self.lock = threading.Lock()

    def _find_device(self, name: str):
        for idx, dev in enumerate(self.sd.query_devices()):
            if dev["max_input_channels"] > 0 and name.lower() in dev["name"].lower():
                log.info("Usando microfone: %s", dev["name"])
                return idx
        log.warning("Microfone '%s' não encontrado; usando o padrão.", name)
        return None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("Áudio: %s", status)
        with self.lock:
            self.chunks.append(indata.copy())

    def start(self) -> None:
        with self.lock:
            self.chunks = []
        if self.stream is not None:
            return
        self.stream = self.sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self.stream.start()

    def stop(self):
        import numpy as np

        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
        with self.lock:
            chunks, self.chunks = self.chunks, []
        if not chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(chunks)[:, 0]


def beep(kind: str) -> None:
    """Bipe curto (sobe = começou, desce = parou, grave = erro)."""
    try:
        import numpy as np
        import sounddevice as sd

        freqs = {"start": (660, 880), "stop": (880, 660), "error": (300, 220)}[kind]
        sr = 44_100
        parts = []
        for f in freqs:
            t = np.linspace(0, 0.06, int(sr * 0.06), endpoint=False)
            env = np.minimum(1, np.minimum(t, 0.06 - t) / 0.01)
            parts.append(0.15 * np.sin(2 * np.pi * f * t) * env)
        sd.play(np.concatenate(parts).astype("float32"), sr)
    except Exception as exc:  # som nunca deve derrubar o app
        log.debug("Bipe falhou: %s", exc)


# --------------------------------------------------------------------------- #
# Transcrição
# --------------------------------------------------------------------------- #
class LocalTranscriber:
    def __init__(self, cfg: Config) -> None:
        from faster_whisper import WhisperModel

        device = cfg.device
        if device == "auto":
            device = "cuda" if _has_cuda() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        log.info("Carregando modelo Whisper '%s' em %s (%s)...", cfg.model, device, compute)
        self.model = WhisperModel(cfg.model, device=device, compute_type=compute)
        self.cfg = cfg
        log.info("Modelo pronto.")

    def transcribe(self, audio) -> str:
        segments, _info = self.model.transcribe(
            audio,
            language=self.cfg.language or None,
            beam_size=5,
            vad_filter=True,
            initial_prompt=self.cfg.initial_prompt or None,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()


class OpenAITranscriber:
    def __init__(self, cfg: Config) -> None:
        from openai import OpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Defina a variável de ambiente OPENAI_API_KEY.")
        self.client = OpenAI()
        self.cfg = cfg

    def transcribe(self, audio) -> str:
        import io
        import wave

        import numpy as np

        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        buf.seek(0)
        buf.name = "fala.wav"
        result = self.client.audio.transcriptions.create(
            model=self.cfg.openai_model,
            file=buf,
            language=self.cfg.language or None,
            prompt=self.cfg.initial_prompt or None,
        )
        return (result.text or "").strip()


def _has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


# Frases que o Whisper "alucina" quando recebe silêncio.
HALLUCINATIONS = {
    "",
    "obrigado.",
    "obrigada.",
    "obrigado por assistir.",
    "legendas pela comunidade amara.org",
    "transcrição em português do brasil, com pontuação.",
}


def clean_text(text: str, cfg: Config) -> str:
    text = " ".join(text.split())
    if text.lower() in HALLUCINATIONS:
        return ""
    if text and cfg.trailing_space:
        text += " "
    return text


# --------------------------------------------------------------------------- #
# Colar o texto no app em foco
# --------------------------------------------------------------------------- #
class Typer:
    def __init__(self, restore_clipboard: bool) -> None:
        from pynput.keyboard import Controller

        self.kb = Controller()
        self.restore_clipboard = restore_clipboard
        self.busy = threading.Event()  # ignora as teclas que nós mesmos enviamos

    def paste(self, text: str) -> None:
        import pyperclip
        from pynput.keyboard import Key

        previous = None
        if self.restore_clipboard:
            try:
                previous = pyperclip.paste()
            except Exception:
                previous = None
        pyperclip.copy(text)
        time.sleep(0.05)
        modifier = Key.cmd if sys.platform == "darwin" else Key.ctrl
        self.busy.set()
        try:
            with self.kb.pressed(modifier):
                self.kb.press("v")
                self.kb.release("v")
            time.sleep(0.25)  # dá tempo do app ler a área de transferência
        finally:
            self.busy.clear()
        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Aplicativo
# --------------------------------------------------------------------------- #
class DictationApp:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.status = "carregando"
        self.status_listeners: list[Callable[[str], None]] = []
        self.jobs: "queue.Queue" = queue.Queue()
        self.recorder = Recorder(cfg.microphone)
        self.typer = Typer(cfg.restore_clipboard)
        self.transcriber = None
        self.recording = False
        self.enabled = True
        self.detector = HoldDetector(
            hold_delay=cfg.hold_delay_ms / 1000,
            on_arm=self._arm,
            on_confirm=self._confirm,
            on_release=self._release,
            on_cancel=self._cancel,
        )
        self.det_lock = threading.Lock()

    # --- status -------------------------------------------------------------
    def set_status(self, status: str) -> None:
        self.status = status
        for fn in self.status_listeners:
            try:
                fn(status)
            except Exception:
                log.exception("Erro ao atualizar status")

    # --- callbacks do detector ---------------------------------------------
    def _arm(self) -> None:
        if not self.enabled or self.transcriber is None:
            return
        try:
            self.recorder.start()  # já grava, para não perder o início da fala
            self.recording = True
        except Exception:
            log.exception("Não consegui abrir o microfone")
            beep("error")

    def _confirm(self) -> None:
        if not self.recording:
            return
        if self.cfg.beeps:
            beep("start")
        self.set_status("gravando")
        log.info("Gravando...")

    def _cancel(self) -> None:
        if self.recording:
            self.recording = False
            self.recorder.stop()
            self.set_status("pronto")

    def _release(self) -> None:
        if not self.recording:
            return
        self.recording = False
        audio = self.recorder.stop()
        if self.cfg.beeps:
            beep("stop")
        if len(audio) < SAMPLE_RATE * self.cfg.min_audio_ms / 1000:
            log.info("Gravação curta demais, ignorada.")
            self.set_status("pronto")
            return
        self.set_status("transcrevendo")
        self.jobs.put(audio)

    # --- teclado ------------------------------------------------------------
    @staticmethod
    def _normalize(key) -> str:
        from pynput.keyboard import Key

        if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
            return "ctrl"
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            return "shift"
        vk = getattr(key, "vk", None)
        return f"vk{vk}" if vk is not None else str(key)

    def _on_press(self, key) -> None:
        if self.typer.busy.is_set():
            return
        with self.det_lock:
            self.detector.key_down(self._normalize(key))

    def _on_release(self, key) -> None:
        if self.typer.busy.is_set():
            return
        with self.det_lock:
            self.detector.key_up(self._normalize(key))

    def _ticker(self) -> None:
        while True:
            time.sleep(0.03)
            with self.det_lock:
                self.detector.tick()

    # --- trabalho pesado ---------------------------------------------------
    def _worker(self) -> None:
        try:
            if self.cfg.engine == "openai":
                self.transcriber = OpenAITranscriber(self.cfg)
            else:
                self.transcriber = LocalTranscriber(self.cfg)
        except Exception:
            log.exception("Falha ao iniciar a transcrição")
            self.set_status("erro")
            return
        self.set_status("pronto")
        log.info("Pronto! Segure Ctrl+Shift e fale.")
        while True:
            audio = self.jobs.get()
            started = time.monotonic()
            try:
                text = clean_text(self.transcriber.transcribe(audio), self.cfg)
                log.info(
                    "Transcrito em %.1fs: %r", time.monotonic() - started, text
                )
                if text:
                    # espera o usuário soltar todas as teclas antes de colar
                    deadline = time.monotonic() + 2
                    while self.detector.down and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.typer.paste(text)
            except Exception:
                log.exception("Erro na transcrição")
                beep("error")
            if self.jobs.empty() and not self.recording:
                self.set_status("pronto")

    def start_background(self) -> None:
        from pynput import keyboard

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._ticker, daemon=True).start()
        self.listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self.listener.daemon = True
        self.listener.start()


# --------------------------------------------------------------------------- #
# Ícone na bandeja
# --------------------------------------------------------------------------- #
COLORS = {
    "carregando": (150, 150, 150),
    "pronto": (40, 170, 90),
    "gravando": (220, 40, 40),
    "transcrevendo": (240, 170, 20),
    "erro": (90, 90, 90),
    "pausado": (90, 90, 90),
}


def make_icon_image(status: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = COLORS.get(status, (150, 150, 150))
    d.ellipse((2, 2, 62, 62), fill=color)
    # microfone estilizado
    d.rounded_rectangle((24, 12, 40, 38), radius=8, fill="white")
    d.arc((18, 22, 46, 46), start=0, end=180, fill="white", width=3)
    d.line((32, 46, 32, 52), fill="white", width=3)
    d.line((24, 52, 40, 52), fill="white", width=3)
    return img


def run_tray(app: DictationApp) -> None:
    import pystray

    def toggle(icon, _item):
        app.enabled = not app.enabled
        app.set_status("pronto" if app.enabled else "pausado")

    def open_config(_icon, _item):
        _open_path(CONFIG_PATH)

    def open_log(_icon, _item):
        _open_path(LOG_PATH)

    def quit_app(icon, _item):
        icon.stop()

    icon = pystray.Icon(
        "ditado",
        make_icon_image(app.status),
        "Ditado",
        menu=pystray.Menu(
            pystray.MenuItem(lambda _i: f"Status: {app.status}", None, enabled=False),
            pystray.MenuItem(
                "Ativado", toggle, checked=lambda _i: app.enabled
            ),
            pystray.MenuItem("Abrir configurações", open_config),
            pystray.MenuItem("Abrir log", open_log),
            pystray.MenuItem("Sair", quit_app),
        ),
    )

    def on_status(status: str) -> None:
        icon.icon = make_icon_image(status)
        icon.title = f"Ditado — {status}"
        try:
            icon.update_menu()
        except Exception:
            pass

    app.status_listeners.append(on_status)
    icon.run()


def _open_path(path: Path) -> None:
    import subprocess

    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# --------------------------------------------------------------------------- #
def setup_logging(verbose: bool) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(LOG_PATH, encoding="utf-8")
    ]
    if sys.stderr is not None:  # pythonw não tem console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ditado por voz com Ctrl+Shift.")
    parser.add_argument("--no-tray", action="store_true", help="sem ícone na bandeja")
    parser.add_argument("--model", help="modelo Whisper (ex.: small, large-v3-turbo)")
    parser.add_argument("--engine", choices=["local", "openai"])
    parser.add_argument("--list-mics", action="store_true", help="lista os microfones")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.list_mics:
        import sounddevice as sd

        for idx, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                print(f"[{idx}] {dev['name']}")
        return

    cfg = Config.load()
    if args.model:
        cfg.model = args.model
    if args.engine:
        cfg.engine = args.engine
    log.info("Config: %s (arquivo: %s)", asdict(cfg), CONFIG_PATH)

    app = DictationApp(cfg)
    app.start_background()

    use_tray = not args.no_tray
    if use_tray:
        try:
            run_tray(app)  # bloqueia até "Sair"
            return
        except Exception as exc:
            log.warning("Bandeja indisponível (%s); rodando sem ícone.", exc)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
