export function readResetToken(hash: string, search: string): string {
  const fromHash = new URLSearchParams(hash.replace(/^#/, "")).get("token");

  if (fromHash) return fromHash.trim();

  return (new URLSearchParams(search).get("token") ?? "").trim();
}
