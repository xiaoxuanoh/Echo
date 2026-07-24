export type ListeningLanguage = "cantonese" | "mandarin" | "english";

export const listeningLanguages: {
  id: ListeningLanguage;
  label: string;
  voice: string;
}[] = [
  {
    id: "cantonese",
    label: "Cantonese",
    voice: "zh-HK-HiuMaanNeural",
  },
  {
    id: "mandarin",
    label: "Mandarin",
    voice: "zh-CN-XiaoxiaoNeural",
  },
  {
    id: "english",
    label: "English",
    voice: "en-US-JennyNeural",
  },
];

export const defaultListeningLanguage: ListeningLanguage = "cantonese";

export function isListeningLanguage(value: string | null | undefined): value is ListeningLanguage {
  return listeningLanguages.some((language) => language.id === value);
}

export function listeningLanguageLabel(
  language: ListeningLanguage | null | undefined,
): string | null {
  return listeningLanguages.find((option) => option.id === language)?.label ?? null;
}

export function languageSummary(
  languages: ListeningLanguage[] | null | undefined,
): string {
  const labels = [...new Set((languages ?? []).map(listeningLanguageLabel).filter(Boolean))];
  if (labels.length === 0) return "No listening language yet";
  if (labels.length <= 2) return labels.join(", ");
  return `${labels.length} languages`;
}
