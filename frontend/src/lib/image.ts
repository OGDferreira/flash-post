/** Downscale an avatar client-side (max edge 512px, WebP/JPEG) so uploads stay small. */
export async function resizeAvatar(file: File, maxEdge = 512): Promise<File> {
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file;
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  for (const type of ["image/webp", "image/jpeg"]) {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.86));
    if (blob && blob.type === type && blob.size < file.size) {
      return new File([blob], `avatar.${type === "image/webp" ? "webp" : "jpg"}`, { type });
    }
  }
  return file;
}
