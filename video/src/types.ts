export type Word = { w: string; s: number; e: number };
export type SceneProps = { dur: number; words: Word[] };

const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]/g, "");

/** Frame (scene-local) at which `word` is first spoken; `nth` picks a later occurrence. */
export const wordAt = (words: Word[], word: string, fps: number, nth = 0) => {
  const hits = words.filter((w) => norm(w.w) === norm(word));
  const hit = hits[Math.min(nth, hits.length - 1)];
  return hit ? Math.round(hit.s * fps) : 0;
};
