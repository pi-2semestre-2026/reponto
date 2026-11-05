export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("reponto_token");
}

export function requireToken(): string {
  const t = getToken();
  if (!t && typeof window !== "undefined") {
    window.location.href = "/login";
    throw new Error("unauthenticated");
  }
  return t as string;
}