import axiosClient from './axiosClient'

/**
 * Generate a presigned S3 PUT URL for uploading a document.
 * @param {string} filename Name of the file.
 * @param {string} contentType MIME type of the file.
 * @returns {Promise<{ uploadUrl: string, key: string, expires_in: number }>}
 */
export const getUploadUrl = (filename, contentType) => {
  return axiosClient.post('/files/upload-url', {
    filename,
    contentType,
  })
}

/**
 * Verify S3 upload completion with backend.
 * @param {string} key S3 object key.
 * @param {string} filename Original filename.
 * @returns {Promise<{ verified: boolean, key: string, message: string }>}
 */
export const completeUpload = (key, filename = '') => {
  return axiosClient.post('/files/upload-complete', {
    key,
    filename,
  })
}

/**
 * Request a presigned S3 GET URL to view or download a file.
 * @param {string} key S3 object key.
 * @returns {Promise<{ viewUrl: string, key: string, expires_in: number }>}
 */
export const getViewUrl = (key) => {
  return axiosClient.post('/files/view-url', {
    key,
  })
}

/**
 * Fetch all verified document metadata records from the backend.
 * @returns {Promise<Array<object>>}
 */
export const fetchFiles = () => {
  return axiosClient.get('/files')
}

/**
 * Update custom metadata fields (title, description, tags) for a file.
 * @param {number} fileId The primary key ID of the file.
 * @param {{ title?: string, description?: string, tags?: string }} payload Metadata updates.
 * @returns {Promise<object>} The updated file metadata.
 */
export const updateFileMetadata = (fileId, payload) => {
  return axiosClient.patch(`/files/${fileId}`, payload)
}


