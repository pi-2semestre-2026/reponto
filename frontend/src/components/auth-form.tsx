"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Wordmark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, setToken } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(name, email, password);
      setToken(res.access_token);
      toast.success(mode === "login" ? t("toast.welcome") : t("toast.welcome"));
      router.push("/dashboard");
    } catch (err) {
      toast.error(mode === "login" ? t("toast.loginError") : (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md animate-fade-in-up">
        <div className="mb-8 flex flex-col items-center gap-3">
          <Wordmark markClassName="h-10 w-10" className="[&>span:last-child]:text-2xl" />
        </div>

        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">{mode === "login" ? t("login.title") : t("register.title")}</CardTitle>
            <CardDescription>{mode === "login" ? t("login.subtitle") : t("register.subtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              {mode === "register" && (
                <div className="space-y-2">
                  <Label htmlFor="name">{t("register.name")}</Label>
                  <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="email">{t("login.email")}</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">{t("login.password")}</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>
              <Button variant="press" size="lg" className="w-full" type="submit" disabled={loading}>
                {loading && <Loader2 className="animate-spin" />}
                {mode === "login" ? t("login.submit") : t("register.submit")}
              </Button>
            </form>
            <p className="mt-5 text-center text-sm text-muted-foreground">
              {mode === "login" ? t("login.noAccount") : t("register.hasAccount")}{" "}
              <Link href={mode === "login" ? "/register" : "/login"} className="font-bold text-primary hover:underline">
                {mode === "login" ? t("login.register") : t("register.login")}
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}