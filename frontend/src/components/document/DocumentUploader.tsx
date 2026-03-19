import { useCallback, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, CheckCircle2 } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { uploadDocument } from '../../services/api'
import type { DocumentUploadResponse } from '../../types'

interface DocumentUploaderProps {
  onUploaded: (doc: DocumentUploadResponse) => void
  onUseSynthetic: () => void
}

function fmtBytes(b: number) {
  if (b > 1_048_576) return `${(b / 1_048_576).toFixed(1)} MB`
  return `${(b / 1_024).toFixed(0)} KB`
}

export default function DocumentUploader({ onUploaded, onUseSynthetic }: DocumentUploaderProps) {
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState<DocumentUploadResponse | null>(null)

  const onDrop = useCallback(
    async (files: File[]) => {
      const file = files[0]
      if (!file) return
      setUploading(true)
      try {
        const result = await uploadDocument(file)
        setUploaded(result)
        onUploaded(result)
        toast.success(`Uploaded ${file.name}`)
      } catch {
        toast.error('Upload failed. Check the backend connection.')
      } finally {
        setUploading(false)
      }
    },
    [onUploaded]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'text/plain': ['.txt'], 'text/markdown': ['.md'] },
    maxFiles: 1,
    disabled: uploading,
  })

  return (
    <div className="card space-y-4">
      <p className="text-sm font-semibold text-white">Document Source</p>

      {/* Drag-and-drop zone */}
      {!uploaded ? (
        <div
          {...getRootProps()}
          className={clsx(
            'border-2 border-dashed rounded-xl px-6 py-10 text-center cursor-pointer transition-colors duration-150',
            isDragActive
              ? 'border-primary-400 bg-primary/5'
              : 'border-border hover:border-border-subtle hover:bg-surface-700/50',
            uploading && 'opacity-50 cursor-not-allowed'
          )}
        >
          <input {...getInputProps()} />
          <div className="flex flex-col items-center gap-3">
            {uploading ? (
              <>
                <div className="w-10 h-10 rounded-full border-2 border-primary-400 border-t-transparent animate-spin" />
                <p className="text-sm text-gray-400">Uploading…</p>
              </>
            ) : (
              <>
                <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary-400 flex items-center justify-center">
                  <Upload size={22} />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">
                    {isDragActive ? 'Drop your document here' : 'Drag & drop or click to upload'}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">PDF, TXT or MD — max 50 MB</p>
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success/5 px-4 py-3">
          <CheckCircle2 size={18} className="text-success-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{uploaded.filename}</p>
            <p className="text-xs text-gray-400">{fmtBytes(uploaded.size_bytes)}</p>
          </div>
          <button
            onClick={() => setUploaded(null)}
            className="text-gray-500 hover:text-gray-300 transition-colors"
            title="Remove"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Divider */}
      <div className="flex items-center gap-3">
        <span className="flex-1 h-px bg-border" />
        <span className="text-xs text-gray-500">or</span>
        <span className="flex-1 h-px bg-border" />
      </div>

      {/* Synthetic document button */}
      <button
        onClick={onUseSynthetic}
        className="w-full flex items-center gap-3 rounded-xl border border-border bg-surface-700 hover:bg-surface-600 px-4 py-3 transition-colors text-left"
      >
        <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary-400 flex items-center justify-center shrink-0">
          <FileText size={16} />
        </div>
        <div>
          <p className="text-sm font-medium text-white">Use Synthetic Demo Document</p>
          <p className="text-xs text-gray-400">EU Securitisation CLO Offering Circular — 150 pages, ~1765 provisions</p>
        </div>
      </button>
    </div>
  )
}
