import { apiClient } from './apiClient';

export const documentsApi = {
  async upload(file, authorizationId, documentType) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('authorizationId', authorizationId);
    formData.append('documentType', documentType);
    return apiClient.postForm('/documents', formData);
  },
  async listForAuthorization(authorizationId) {
    return apiClient.get(`/documents?authorizationId=${encodeURIComponent(authorizationId)}`);
  },
  // Real file bytes for viewing/downloading a submitted document (2026-08-20+)
  // — GET /api/documents/:id/file, authenticated + ownership-checked
  // server-side. Returns a Blob; the caller turns it into an object URL
  // (see components/documents/DocumentRow.jsx) since <img>/<iframe> can't
  // attach an Authorization header themselves.
  async getFileBlob(documentId) {
    return apiClient.getBlob(`/documents/${encodeURIComponent(documentId)}/file`);
  },
};
