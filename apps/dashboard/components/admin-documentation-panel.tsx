"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { Chip, KpiTile, RowActions, type ChipTone } from "@/components/ui/data-cells";
import { friendlyApiError } from "@/lib/api-error";
import type { DocumentationPostRead } from "@/lib/types";

const AUDIENCE_LABELS: Record<string, string> = {
  CUSTOMER: "Solo clienti",
  PROMOTER: "Solo promoter",
  BOTH: "Clienti e promoter",
};
const AUDIENCE_OPTIONS = ["BOTH", "CUSTOMER", "PROMOTER"] as const;
const AUDIENCE_TONES: Record<string, ChipTone> = {
  CUSTOMER: "info",
  PROMOTER: "accent",
  BOTH: "ok",
};
const STATUS_LABELS: Record<string, string> = { PUBLISHED: "Pubblicato", ARCHIVED: "Archiviato" };

async function fetchPosts(): Promise<DocumentationPostRead[]> {
  const res = await fetch("/api/proxy/documentation/admin");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/**
 * Single-file PDF uploader. PhotoUpload is image-only and reads different
 * response fields, so it is not reused.
 */
function PdfUpload({ postId, currentFilename, onUploaded }: { postId: string; currentFilename: string | null; onUploaded: (pdfUrl: string, filename: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/proxy/documentation/${postId}/pdf`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated: DocumentationPostRead = await res.json();
      if (updated.pdf_url) onUploaded(updated.pdf_url, updated.pdf_filename ?? file.name);
    } catch (err: any) {
      setError(err.message || "Caricamento PDF fallito. Riprova.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-1">
      <input ref={inputRef} type="file" accept="application/pdf" onChange={handleFileChange} className="hidden" id={`pdf-input-${postId}`} />
      <label
        htmlFor={`pdf-input-${postId}`}
        className="act cursor-pointer"
      >
        {uploading ? "Caricamento..." : currentFilename ? `Sostituisci PDF (${currentFilename})` : "Carica PDF"}
      </label>
      {error && <p className="text-[11px] text-danger-400">{error}</p>}
    </div>
  );
}

export function AdminDocumentationPanel() {
  const queryClient = useQueryClient();
  const { data: posts, error: loadError } = useQuery({
    queryKey: ["admin", "documentation"],
    queryFn: fetchPosts,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState("BOTH");
  const [videoUrl, setVideoUrl] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingPost, setEditingPost] = useState<DocumentationPostRead | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [editAudience, setEditAudience] = useState("BOTH");
  const [editVideoUrl, setEditVideoUrl] = useState("");
  const [editImageUrl, setEditImageUrl] = useState<string | null>(null);
  const [editPdfUrl, setEditPdfUrl] = useState<string | null>(null);
  const [editPdfFilename, setEditPdfFilename] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deletingPost, setDeletingPost] = useState<DocumentationPostRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openEdit(p: DocumentationPostRead) {
    setEditTitle(p.title);
    setEditBody(p.body ?? "");
    setEditAudience(p.audience);
    setEditVideoUrl(p.video_url ?? "");
    setEditImageUrl(p.image_url);
    setEditPdfUrl(p.pdf_url);
    setEditPdfFilename(p.pdf_filename);
    setEditError(null);
    setEditingPost(p);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/documentation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body: body || null, audience, video_url: videoUrl || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created: DocumentationPostRead = await res.json();
      setShowCreate(false);
      setTitle("");
      setBody("");
      setAudience("BOTH");
      setVideoUrl("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
      // Open in edit mode so attachments can be added right away.
      openEdit(created);
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il post.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingPost) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/documentation/${editingPost.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editTitle,
          body: editBody || null,
          audience: editAudience,
          video_url: editVideoUrl || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingPost(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleToggleStatus(p: DocumentationPostRead) {
    const newStatus = p.status === "PUBLISHED" ? "ARCHIVED" : "PUBLISHED";
    try {
      const res = await fetch(`/api/proxy/documentation/${p.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch {
      // On failure the list reloads unchanged; the admin can simply retry.
    }
  }

  async function handleDelete() {
    if (!deletingPost) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/documentation/${deletingPost.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setDeletingPost(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il post.");
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <div className="kpi-label">Bacheca contenuti</div>
          <h2 className="mt-1 text-2xl font-black tracking-tight text-white">Documentazione e news</h2>
          <p className="mt-2 text-xs text-surface-300">
          Pubblica materiale per i clienti (guide, novità) o per i promoter (listini, materiale formativo) --
          scegli per ognuno chi lo vede. Come un post: testo, e facoltativamente una foto, un PDF da scaricare e un link video.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="shrink-0 px-5 py-2.5 rounded-full text-xs font-black bg-gradient-to-r from-brand-600 to-accent-500 text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer"
        >
          + Nuovo Post
        </button>
      </div>

      {loadError && <p className="text-sm text-danger-400">Impossibile caricare la documentazione.</p>}

      {posts && posts.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <KpiTile label="Post totali" value={posts.length} />
          <KpiTile label="In bacheca" value={posts.filter((p) => p.status === "PUBLISHED").length} hint="Visibili ora" />
          <KpiTile label="In archivio" value={posts.filter((p) => p.status !== "PUBLISHED").length} />
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2 stagger">
        {posts === undefined ? (
          <p className="text-sm text-surface-400 col-span-2 text-center py-8">Caricamento...</p>
        ) : posts.length === 0 ? (
          <div className="panel rounded-3xl col-span-2 flex flex-col items-center gap-3 py-12 text-center">
            <span className="text-3xl float-soft" aria-hidden="true">📰</span>
            <p className="text-sm text-surface-300">Nessun post pubblicato ancora: crea il primo.</p>
          </div>
        ) : (
          posts.map((p, i) => (
            <div key={p.id} className="panel rounded-3xl overflow-hidden flex flex-col" style={{ "--i": i } as React.CSSProperties}>
              {p.image_url && (
                // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
                <img src={p.image_url} alt="" className="w-full h-36 object-cover" />
              )}
              <div className="p-6 flex flex-col gap-2.5 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Chip tone={AUDIENCE_TONES[p.audience] ?? "muted"}>{AUDIENCE_LABELS[p.audience]}</Chip>
                  <Chip tone={p.status === "PUBLISHED" ? "ok" : "muted"} live={p.status === "PUBLISHED"}>
                    {STATUS_LABELS[p.status]}
                  </Chip>
                </div>
                <h3 className="text-lg font-black tracking-tight text-white">{p.title}</h3>
                {p.body && <p className="text-xs text-surface-300 line-clamp-3 whitespace-pre-wrap">{p.body}</p>}
                <div className="flex items-center gap-3 text-[11px] text-surface-400 mt-1">
                  {p.pdf_url && <span>📎 PDF allegato</span>}
                  {p.video_url && <span>🎬 Video allegato</span>}
                  <span className="ml-auto tabular-nums">
                    {new Date(p.created_at).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
                  </span>
                </div>
                <div className="mt-auto pt-4">
                  <RowActions>
                    <button onClick={() => openEdit(p)} className="act act-primary cursor-pointer">
                      Modifica
                    </button>
                    <button onClick={() => handleToggleStatus(p)} className="act cursor-pointer">
                      {p.status === "PUBLISHED" ? "Archivia" : "Ripubblica"}
                    </button>
                    <button onClick={() => setDeletingPost(p)} className="act cursor-pointer text-danger-300">
                      Elimina
                    </button>
                  </RowActions>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-2xl font-black tracking-tight text-white">Nuovo Post</h3>
              <button onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-surface-400 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="kpi-label block">Titolo</label>
                <input required value={title} onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Testo</label>
                <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Chi lo vede</label>
                <div className="subnav" role="radiogroup">
                  {AUDIENCE_OPTIONS.map((key) => (
                    <button key={key} type="button" role="radio" aria-checked={audience === key}
                      data-active={audience === key} onClick={() => setAudience(key)} className="subnav-pill cursor-pointer">
                      {AUDIENCE_LABELS[key]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Link video (opzionale)</label>
                <input type="url" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder="https://youtube.com/..."
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <p className="text-[11px] text-surface-500">Dopo aver creato il post potrai allegare una foto e un PDF.</p>

              {createError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-5 py-2.5 rounded-full bg-white/5 hover:bg-white/10 text-xs font-bold text-surface-200 border border-white/10 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : "Crea Post"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg panel rounded-3xl p-7 border-white/10 bg-surface-950 pop max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-2xl font-black tracking-tight text-white">Modifica Post</h3>
              <button onClick={() => setEditingPost(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-surface-400 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-white/5 space-y-4">
              <div>
                <label className="kpi-label block mb-2">Foto</label>
                <PhotoUpload
                  currentUrl={editImageUrl}
                  uploadPath={`documentation/${editingPost.id}/image`}
                  onUploaded={(url) => {
                    setEditImageUrl(url);
                    queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
                  }}
                  alt={editingPost.title}
                  size={64}
                />
              </div>
              <div>
                <label className="kpi-label block mb-2">PDF</label>
                <PdfUpload
                  postId={editingPost.id}
                  currentFilename={editPdfFilename}
                  onUploaded={(url, filename) => {
                    setEditPdfUrl(url);
                    setEditPdfFilename(filename);
                    queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
                  }}
                />
              </div>
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              <div className="space-y-1">
                <label className="kpi-label block">Titolo</label>
                <input required value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Testo</label>
                <textarea rows={4} value={editBody} onChange={(e) => setEditBody(e.target.value)}
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500 resize-none" />
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Chi lo vede</label>
                <div className="subnav" role="radiogroup">
                  {AUDIENCE_OPTIONS.map((key) => (
                    <button key={key} type="button" role="radio" aria-checked={editAudience === key}
                      data-active={editAudience === key} onClick={() => setEditAudience(key)} className="subnav-pill cursor-pointer">
                      {AUDIENCE_LABELS[key]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <label className="kpi-label block">Link video (opzionale)</label>
                <input type="url" value={editVideoUrl} onChange={(e) => setEditVideoUrl(e.target.value)}
                  placeholder="https://youtube.com/..."
                  className="w-full rounded-xl field px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingPost(null)}
                  className="px-5 py-2.5 rounded-full bg-white/5 hover:bg-white/10 text-xs font-bold text-surface-200 border border-white/10 transition cursor-pointer">
                  Chiudi
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-5 py-2.5 rounded-full bg-gradient-to-r from-brand-600 to-accent-500 text-xs font-black text-white shadow-lg shadow-brand-500/30 hover:brightness-110 transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deletingPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md panel rounded-3xl p-7 border-white/10 bg-surface-950 pop">
            <h3 className="text-2xl font-black tracking-tight text-white mb-2">Eliminare &ldquo;{deletingPost.title}&rdquo;?</h3>
            <p className="text-xs text-surface-400 mb-4">
              Il post sparirà subito dal feed di chi lo vedeva. Questa azione non si può annullare.
            </p>
            {deleteError && (
              <div className="p-3 rounded-lg bg-danger-500/10 border border-danger-500/20 text-danger-400 text-xs mb-4">{deleteError}</div>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeletingPost(null)}
                className="px-5 py-2.5 rounded-full bg-white/5 hover:bg-white/10 text-xs font-bold text-surface-200 border border-white/10 transition cursor-pointer"
              >
                Annulla
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteLoading}
                className="px-4 py-2 rounded-xl bg-danger-600 hover:bg-danger-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {deleteLoading ? "Eliminazione..." : "Elimina"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
