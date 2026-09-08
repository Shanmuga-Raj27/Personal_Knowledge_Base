/**
 * frontend/src/services/ragService.js
 *
 * Phase 8 RAG business logic — selection rules, max-5 cap, INDEXED filter,
 * file_id mapping. No JSX, no network calls, no React state.
 *
 * This is the single source of truth for the selection contract (Phase 8 §5.3).
 * The page calls these functions; components never re-implement the rules.
 */

export const MAX_SELECTED_FILES = 5

/**
 * Check whether a document has completed indexing and is queryable.
 * Handles both casing conventions returned by the backend alias layer.
 * @param {object} doc Document from fetchFiles() (has indexingStatus / indexing_status)
 * @returns {boolean}
 */
export const isIndexed = (doc) => {
  const status = (doc.indexingStatus || doc.indexing_status || '').toUpperCase()
  return status === 'INDEXED'
}

/**
 * Return only documents that have completed indexing.
 * @param {Array<object>} documents Raw list from fetchFiles()
 * @returns {Array<object>}
 */
export const selectableDocuments = (documents) =>
  documents.filter(isIndexed)

/**
 * Add a document to the selection, enforcing the max-5 hard cap.
 * Returns a new array (immutable update). Throws on the 6th selection so
 * the caller can surface the error via a Snackbar.
 * @param {Array<object>} selection Current selected docs (max 5)
 * @param {object} doc Document to add
 * @returns {Array<object>} Updated selection (new reference)
 * @throws {Error} When selection is already at MAX_SELECTED_FILES
 */
export const addToSelection = (selection, doc) => {
  if (selection.some((d) => d.fileId === doc.fileId)) return selection
  if (selection.length >= MAX_SELECTED_FILES) {
    throw new Error(`You can select at most ${MAX_SELECTED_FILES} documents per conversation.`)
  }
  return [...selection, doc]
}

/**
 * Remove a document from the selection by fileId.
 * @param {Array<object>} selection Current selected docs
 * @param {number} fileId The fileId to remove
 * @returns {Array<object>} Updated selection (new reference)
 */
export const removeFromSelection = (selection, fileId) =>
  selection.filter((d) => d.fileId !== fileId)

/**
 * Map a selection array to the file_ids number[] the backend accepts.
 * S3 keys are never included — only numeric file IDs.
 * @param {Array<object>} selection
 * @returns {number[]}
 */
export const toFileIds = (selection) => selection.map((d) => d.fileId)

/**
 * Friendly display label for a document (title preferred, filename fallback).
 * @param {object} doc
 * @returns {string}
 */
export const formatSelectionLabel = (doc) => doc.title || doc.filename

/**
 * Merge a list of candidate docs into the current selection.
 * - Keeps only INDEXED docs.
 * - Skips duplicates (by fileId).
 * - Caps the result at MAX_SELECTED_FILES (5) — overflow is silently skipped.
 * Returns a new array and a small summary so callers can show banners.
 * @param {Array<object>} current Current shared selection (max 5)
 * @param {Array<object>} candidates Docs to merge in (from Vault)
 * @returns {{ next: Array<object>, added: number, skippedAlreadyPresent: number, skippedNotIndexed: number, skippedCap: number }}
 */
export const mergeSelection = (current, candidates) => {
  let next = [...current]
  let added = 0
  let skippedAlreadyPresent = 0
  let skippedNotIndexed = 0
  let skippedCap = 0
  for (const doc of candidates || []) {
    if (!isIndexed(doc)) {
      skippedNotIndexed += 1
      continue
    }
    if (next.some((d) => d.fileId === doc.fileId)) {
      skippedAlreadyPresent += 1
      continue
    }
    if (next.length >= MAX_SELECTED_FILES) {
      skippedCap += 1
      continue
    }
    next = [...next, doc]
    added += 1
  }
  return { next, added, skippedAlreadyPresent, skippedNotIndexed, skippedCap }
}
