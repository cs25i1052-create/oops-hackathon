"use client";
import { useState, useRef, useEffect } from "react";

const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];

interface ImageUploaderProps {
  onScan: (file: File) => void;
  isScanning: boolean;
}

export default function ImageUploader({ onScan, isScanning }: ImageUploaderProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const handleFile = (file: File) => {
    setErrorMsg(null);
    if (!ALLOWED_TYPES.includes(file.type)) {
      setErrorMsg("Unsupported format. Please upload a PNG, JPG, or WebP image.");
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      setErrorMsg("File exceeds 4MB limit. Please choose a compressed asset.");
      return;
    }

    if (preview) URL.revokeObjectURL(preview);
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);
    setSelectedFile(file);
    onScan(file);
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
        }}
        className={`relative w-full h-80 flex flex-col items-center justify-center border-2 border-dashed rounded-xl transition-all overflow-hidden ${
          isDragging
            ? "border-indigo-500 bg-indigo-50/50"
            : "border-slate-300 bg-slate-50/50 hover:bg-slate-50"
        }`}
      >
        {preview ? (
          <div className="relative w-full h-full flex items-center justify-center p-4 bg-slate-900/5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={preview}
              alt="Uploaded marketing asset"
              className="max-h-full max-w-full object-contain rounded-lg shadow-sm"
            />
            <div className="absolute top-3 right-3 flex gap-2">
              <button
                type="button"
                disabled={isScanning}
                onClick={() => {
                  setPreview(null);
                  setSelectedFile(null);
                }}
                className="bg-slate-900/80 hover:bg-slate-900 text-white text-xs font-medium px-3 py-1.5 rounded-lg backdrop-blur-sm transition cursor-pointer disabled:opacity-50"
              >
                Replace Image
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center p-6 max-w-xs">
            <div className="mx-auto w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-3">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.75}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-800">
              Drop promotional visual here
            </p>
            <p className="text-xs text-slate-500 mt-1">
              PNG, JPG, or WebP • Checks WCAG contrast & brand hex palette (Max 4MB)
            </p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="mt-4 inline-flex items-center px-4 py-2 rounded-lg bg-white border border-slate-200 shadow-sm text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
            >
              Select Asset File
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </div>
        )}
      </div>

      {errorMsg && (
        <p className="text-xs font-medium text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
          {errorMsg}
        </p>
      )}

      {selectedFile && (
        <button
          type="button"
          onClick={() => onScan(selectedFile)}
          disabled={isScanning}
          className="w-full bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white py-3 rounded-xl font-semibold text-sm shadow-sm transition cursor-pointer"
        >
          {isScanning ? "Analyzing Visual Compliance..." : "Re-Scan Visual Asset"}
        </button>
      )}
    </div>
  );
}