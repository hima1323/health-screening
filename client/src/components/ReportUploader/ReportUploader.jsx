import { useRef, useState } from 'react';
import { FileText, Image as ImageIcon, Trash2, UploadCloud } from 'lucide-react';
import styles from './ReportUploader.module.css';

const readableSize = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Uploaded reports are either a picture of a printout or a document. */
const iconFor = (mimeType) => (mimeType?.startsWith('image/') ? ImageIcon : FileText);

/** Drag-and-drop (or browse) for past clinic reports, with the list of what is attached. */
export default function ReportUploader({ reports = [], busy = false, error, onUpload, onRemove }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const accept = (files) => {
    if (files?.length) onUpload(files);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files);
  };

  return (
    <div className={styles.uploader}>
      <div
        className={`${styles.dropzone} ${dragging ? styles.dragging : ''}`.trim()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && inputRef.current?.click()}
      >
        <UploadCloud size={26} strokeWidth={1.5} aria-hidden="true" />
        <p className={styles.prompt}>{busy ? 'Uploading…' : 'Drop past reports here, or browse'}</p>
        <p className="muted small">PDF, JPG, PNG or text · up to 15 MB each</p>
        <input
          ref={inputRef}
          type="file"
          className={styles.input}
          multiple
          accept="application/pdf,image/*,text/plain"
          onChange={(event) => {
            accept(event.target.files);
            event.target.value = '';
          }}
          aria-label="Choose past reports to upload"
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {reports.length > 0 && (
        <ul className={styles.list}>
          {reports.map((report) => {
            const Icon = iconFor(report.mimeType);
            return (
              <li key={report.id} className={styles.item}>
                <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
                <div className={styles.meta}>
                  <p className={styles.name}>{report.originalName}</p>
                  <p className="muted small">{readableSize(report.sizeBytes)}</p>
                </div>
                <button
                  type="button"
                  className={styles.remove}
                  onClick={() => onRemove(report.id)}
                  aria-label={`Remove ${report.originalName}`}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
