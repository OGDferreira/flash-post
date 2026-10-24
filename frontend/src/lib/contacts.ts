/** Official Flash channels. Set a url to turn a "Em breve" card into a live link. */
export const SUPPORT_WHATSAPP = "5527999384259"; // +55 27 99938-4259
export const SUPPORT_WHATSAPP_LABEL = "+55 27 99938-4259";

export const contactChannels = {
  instagram: { url: null as string | null, handle: null as string | null },
  // WhatsApp community group: paste the invite link here when the group exists.
  community: { url: null as string | null },
  // Telegram bot (planned): paste https://t.me/<bot> when it goes live.
  telegram: { url: null as string | null },
};

export function whatsappLink(message: string) {
  return `https://wa.me/${SUPPORT_WHATSAPP}?text=${encodeURIComponent(message)}`;
}
