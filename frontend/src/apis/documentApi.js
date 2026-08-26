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
