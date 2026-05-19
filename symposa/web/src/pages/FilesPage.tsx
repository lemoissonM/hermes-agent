import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  UserFile,
  deleteUserFile,
  fetchUserFileBlob,
  getToken,
  listUserFiles,
  uploadUserFile,
  userFileContentUrl,
} from "../api/client";

function formatSize(bytes?: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isHtml(file: UserFile): boolean {
  return (file.content_type || "").includes("html") || file.name.toLowerCase().endsWith(".html");
}

function isImage(file: UserFile): boolean {
  return (file.content_type || "").startsWith("image/");
}

async function downloadWithAuth(file: UserFile): Promise<void> {
  const token = getToken();
  const resp = await fetch(userFileContentUrl(file.id, "attachment"), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error("Download failed");
  const blob = await resp.blob();
  const a = document.createElement("a");
  const url = URL.createObjectURL(blob);
  a.href = url;
  a.download = file.name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function FilesPage() {
  const [files, setFiles] = useState<UserFile[]>([]);
  const [error, setError] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<UserFile | null>(null);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      setFiles(await listUserFiles());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  useEffect(() => {
    if (!previewId) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      setPreviewFile(null);
      return;
    }
    const file = files.find((f) => f.id === previewId);
    if (!file) return;
    setPreviewFile(file);
    let revoked: string | null = null;
    fetchUserFileBlob(previewId)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        revoked = url;
        setPreviewUrl(url);
      })
      .catch((e) => setError(String(e)));
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [previewId, files]);

  async function handleDelete(fileId: string) {
    if (!confirm("Delete this file?")) return;
    try {
      await deleteUserFile(fileId);
      if (previewId === fileId) setPreviewId(null);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    if (!picked) return;
    setUploading(true);
    setError("");
    try {
      await uploadUserFile(picked);
      await load();
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div className="files-page">
      <header className="settings-header">
        <Link to="/">← Chat</Link>
        <h1>Your files</h1>
        <p className="muted">
          Reports and downloads from the assistant. Only you can view or delete these files.
        </p>
        <label className="files-upload">
          <span className="files-upload-btn">{uploading ? "Uploading…" : "Upload file"}</span>
          <input type="file" hidden onChange={handleUpload} disabled={uploading} />
        </label>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <div className="files-layout">
        <table className="files-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {files.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  No files yet. Ask the assistant to save a report under user/outputs/, or upload
                  here.
                </td>
              </tr>
            ) : (
              files.map((f) => (
                <tr key={f.id} className={previewId === f.id ? "active" : ""}>
                  <td>{f.name}</td>
                  <td>{f.content_type || f.source}</td>
                  <td>{formatSize(f.size_bytes)}</td>
                  <td className="files-actions">
                    <button type="button" onClick={() => setPreviewId(f.id)}>
                      Open
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadWithAuth(f).catch((err) => setError(String(err)))}
                    >
                      Download
                    </button>
                    <button type="button" className="danger" onClick={() => handleDelete(f.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {previewFile && previewUrl ? (
          <aside className="files-preview">
            <h2>{previewFile.name}</h2>
            {isHtml(previewFile) ? (
              <iframe
                title={previewFile.name}
                sandbox=""
                src={previewUrl}
                className="files-preview-frame"
              />
            ) : isImage(previewFile) ? (
              <img src={previewUrl} alt={previewFile.name} className="files-preview-img" />
            ) : (
              <p className="muted">
                Preview not available for this type. Use Download or open in a new tab.
              </p>
            )}
            <p>
              <button
                type="button"
                className="link"
                onClick={() =>
                  fetchUserFileBlob(previewFile.id)
                    .then((blob) => {
                      window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
                    })
                    .catch((err) => setError(String(err)))
                }
              >
                Open in new tab
              </button>
            </p>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
