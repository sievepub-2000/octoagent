/**
 * API functions for file uploads
 */

import { apiRequest, deleteJSON, getJSON } from "../api/http";

export interface UploadedFileInfo {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  artifact_url: string;
  extension?: string;
  modified?: number;
  markdown_file?: string;
  markdown_path?: string;
  markdown_virtual_path?: string;
  markdown_artifact_url?: string;
}

export interface UploadResponse {
  success: boolean;
  files: UploadedFileInfo[];
  message: string;
}

export interface ListFilesResponse {
  files: UploadedFileInfo[];
  count: number;
}

/**
 * Upload files to a thread
 */
export async function uploadFiles(
  threadId: string,
  files: File[],
): Promise<UploadResponse> {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  return apiRequest<UploadResponse>(`/api/threads/${threadId}/uploads`, {
    method: "POST",
    body: formData,
  });
}

/**
 * List all uploaded files for a thread
 */
export async function listUploadedFiles(
  threadId: string,
): Promise<ListFilesResponse> {
  return getJSON<ListFilesResponse>(`/api/threads/${threadId}/uploads/list`);
}

/**
 * Delete an uploaded file
 */
export async function deleteUploadedFile(
  threadId: string,
  filename: string,
): Promise<{ success: boolean; message: string }> {
  return deleteJSON<{ success: boolean; message: string }>(
    `/api/threads/${threadId}/uploads/${filename}`,
  );
}
