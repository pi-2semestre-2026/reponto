const TOKEN_KEY = "reponto_token";

// Login vindo do caixa: o botão "Reponto" do caixa passa o token depois do "#", parte do
// endereço que nunca é enviada ao servidor. Guardamos e apagamos do endereço na hora.
function consumeHandoffToken() {
  const handoff = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (!handoff) return;
  sessionStorage.setItem(TOKEN_KEY, handoff);
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

// O login vale enquanto a aba estiver aberta (igual ao caixa): fechou, pede de novo.
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  consumeHandoffToken();
  return sessionStorage.getItem(TOKEN_KEY);
}

export function requireToken(): string {
  const t = getToken();
  if (!t && typeof window !== "undefined") {
    window.location.href = "/login";
    throw new Error("unauthenticated");
  }
  return t as string;
}
