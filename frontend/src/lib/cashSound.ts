/** Sale sound: the chosen clip (public/sounds/venda.mp3), played through Web Audio so it
 * works once the page was touched; falls back to a synthesized "ka-ching". */
let context: AudioContext | null = null;
let clip: AudioBuffer | null = null;
let loading: Promise<void> | null = null;

function loadClip(ctx: AudioContext) {
  loading ??= fetch("/sounds/venda.mp3")
    .then((response) => (response.ok ? response.arrayBuffer() : Promise.reject(new Error("sound"))))
    .then((data) => ctx.decodeAudioData(data))
    .then((buffer) => {
      clip = buffer;
    })
    .catch(() => {
      loading = null; // try again next time; the synthesized sound plays meanwhile
    });
  return loading;
}

function audio(): AudioContext | null {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  context ??= new Ctor();
  return context;
}

/** Browsers only allow sound after the user touched the page once; unlock on the first tap. */
export function unlockCashSound() {
  const resume = () => {
    const ctx = audio();
    void ctx?.resume();
    if (ctx) void loadClip(ctx);
    window.removeEventListener("pointerdown", resume);
    window.removeEventListener("keydown", resume);
  };
  window.addEventListener("pointerdown", resume, { once: true });
  window.addEventListener("keydown", resume, { once: true });
}

function bell(ctx: AudioContext, start: number, frequency: number, length: number, volume: number) {
  for (const [ratio, gainScale] of [[1, 1], [2.76, 0.35], [5.4, 0.15]] as const) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = frequency * ratio;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(volume * gainScale, start + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(start + length + 0.02);
  }
}

function rattle(ctx: AudioContext, start: number) {
  const length = 0.12;
  const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * length), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  const source = ctx.createBufferSource();
  const filter = ctx.createBiquadFilter();
  const gain = ctx.createGain();
  source.buffer = buffer;
  filter.type = "highpass";
  filter.frequency.value = 3500;
  gain.gain.value = 0.18;
  source.connect(filter).connect(gain).connect(ctx.destination);
  source.start(start);
}

export function playCashSound() {
  const ctx = audio();
  if (!ctx || ctx.state === "suspended") return;
  if (clip) {
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = clip;
    gain.gain.value = 0.9;
    source.connect(gain).connect(ctx.destination);
    source.start();
    return;
  }
  void loadClip(ctx);
  const now = ctx.currentTime + 0.01;
  rattle(ctx, now);
  bell(ctx, now + 0.06, 1318.5, 0.5, 0.22); // E6
  bell(ctx, now + 0.16, 1760, 0.9, 0.25); // A6
}
