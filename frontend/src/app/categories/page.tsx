"use client";

import { useEffect, useState } from "react";
import { Loader2, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Category } from "@/lib/types";

export default function CategoriesPage() {
  const { t } = useI18n();
  const [cats, setCats] = useState<Category[] | null>(null);
  const [editing, setEditing] = useState<Category | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [keywords, setKeywords] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null);

  const load = () => api.categories().then(setCats).catch((e) => toast.error(e.message));
  useEffect(() => {
    load();
  }, []);

  const openForm = (c?: Category) => {
    setName(c?.name ?? "");
    setDescription(c?.description ?? "");
    setKeywords(c?.keywords ?? "");
    if (c) setEditing(c);
    else setCreating(true);
  };

  const closeForm = () => {
    setEditing(null);
    setCreating(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      if (editing) {
        await api.updateCategory(editing.id, { name, description, keywords });
        toast.success(t("toast.updated"));
      } else {
        await api.createCategory({ name, description, keywords });
        toast.success(t("toast.updated"));
      }
      closeForm();
      load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (c: Category) => {
    if (c.is_seed) {
      toast.error(t("categories.deleteBlocked"));
      return;
    }
    try {
      await api.deleteCategory(c.id);
      toast.success(t("toast.deleted"));
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="min-h-screen">
      <Header active="/categories" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight">{t("categories.title")}</h1>
            <p className="mt-1 text-muted-foreground">{t("categories.subtitle")}</p>
          </div>
          <Button variant="press" onClick={() => openForm()}>
            <Plus /> {t("categories.new")}
          </Button>
        </div>

        <Card className="animate-fade-in-up">
          <CardContent className="p-0">
            {cats === null ? (
              <div className="space-y-3 p-6">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-11" />
                ))}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.name")}</TableHead>
                    <TableHead>{t("common.description")}</TableHead>
                    <TableHead className="w-28">Tipo</TableHead>
                    <TableHead className="text-right">{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cats.map((c) => (
                    <TableRow key={c.id} className="group">
                      <TableCell className="font-bold">{c.name}</TableCell>
                      <TableCell className="max-w-md">
                        <p className="truncate text-sm text-muted-foreground">{c.description}</p>
                      </TableCell>
                      <TableCell>
                        {c.is_seed ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="secondary" className="gap-1">
                                <Lock className="h-3 w-3" /> {t("categories.seed")}
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent>{t("categories.deleteBlocked")}</TooltipContent>
                          </Tooltip>
                        ) : (
                          <Badge variant="info">{t("categories.custom")}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1 opacity-60 transition-opacity group-hover:opacity-100">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openForm(c)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive disabled:opacity-30"
                            disabled={c.is_seed}
                            onClick={() => remove(c)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      <Dialog open={creating || !!editing} onOpenChange={(v) => !v && closeForm()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? t("common.edit") : t("categories.new")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t("common.name")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>{t("common.description")}</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Ex.: Pães, bolos, biscoitos, torradas..."
              />
            </div>
            <div className="space-y-2">
              <Label>{t("categories.keywords")}</Label>
              <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="separadas por vírgula" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeForm}>
              {t("common.cancel")}
            </Button>
            <Button variant="press" onClick={save} disabled={saving || !name.trim()}>
              {saving && <Loader2 className="animate-spin" />}
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}