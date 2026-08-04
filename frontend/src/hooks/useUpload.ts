"use client";

import { useUploadContext } from "@/context/UploadContext";

export function useUpload() {
  return useUploadContext();
}
