import { describe, it, expect } from 'vitest'
import {
  MAX_SELECTED_FILES,
  isIndexed,
  selectableDocuments,
  addToSelection,
  removeFromSelection,
  toFileIds,
  formatSelectionLabel,
} from '../ragService'

/**
 * Unit tests for the RAG selection logic (Phase 8 §8.1).
 * These pin the hard contracts the UI obeys: max-5 cap, INDEXED-only
 * selectability, and file_id mapping (never S3 keys).
 */

const makeDoc = (fileId, { indexingStatus = 'INDEXED', title = '', filename = `file-${fileId}.pdf` } = {}) => ({
  fileId,
  indexingStatus,
  title,
  filename,
})

describe('isIndexed', () => {
  it('returns true for uppercase INDEXED', () => {
    expect(isIndexed(makeDoc(1))).toBe(true)
  })

  it('handles lowercase status casing', () => {
    expect(isIndexed({ fileId: 1, indexingStatus: 'indexed' })).toBe(true)
  })

  it('handles snake_case indexing_status field', () => {
    expect(isIndexed({ fileId: 1, indexing_status: 'INDEXED' })).toBe(true)
  })

  it('returns false for non-INDEXED statuses and missing values', () => {
    expect(isIndexed(makeDoc(1, { indexingStatus: 'PENDING' }))).toBe(false)
    expect(isIndexed(makeDoc(1, { indexingStatus: 'FAILED' }))).toBe(false)
    expect(isIndexed({ fileId: 1 })).toBe(false)
  })
})

describe('selectableDocuments', () => {
  it('filters out non-INDEXED documents', () => {
    const docs = [
      makeDoc(1),
      makeDoc(2, { indexingStatus: 'PENDING' }),
      makeDoc(3, { indexingStatus: 'indexed' }),
      makeDoc(4, { indexingStatus: 'FAILED' }),
    ]

    const result = selectableDocuments(docs)

    expect(result.map((d) => d.fileId)).toEqual([1, 3])
  })

  it('returns an empty array when nothing is indexed', () => {
    expect(selectableDocuments([makeDoc(1, { indexingStatus: 'PENDING' })])).toEqual([])
    expect(selectableDocuments([])).toEqual([])
  })
})

describe('addToSelection', () => {
  it('appends a new document to the selection', () => {
    const result = addToSelection([makeDoc(1)], makeDoc(2))
    expect(result.map((d) => d.fileId)).toEqual([1, 2])
  })

  it('returns the same reference (unchanged) for a duplicate', () => {
    const selection = [makeDoc(1)]
    const result = addToSelection(selection, makeDoc(1))
    expect(result).toBe(selection)
    expect(result).toHaveLength(1)
  })

  it('throws when a 6th document is added', () => {
    const selection = Array.from({ length: MAX_SELECTED_FILES }, (_, i) => makeDoc(i + 1))
    expect(() => addToSelection(selection, makeDoc(99))).toThrow(
      `You can select at most ${MAX_SELECTED_FILES} documents per conversation.`,
    )
  })

  it('allows exactly MAX_SELECTED_FILES', () => {
    let next = []
    for (let i = 1; i <= MAX_SELECTED_FILES; i++) {
      next = addToSelection(next, makeDoc(i))
    }
    expect(next).toHaveLength(MAX_SELECTED_FILES)
  })
})

describe('removeFromSelection', () => {
  it('removes a document by fileId and keeps order', () => {
    const selection = [makeDoc(1), makeDoc(2), makeDoc(3)]
    const result = removeFromSelection(selection, 2)
    expect(result.map((d) => d.fileId)).toEqual([1, 3])
  })

  it('is a no-op (new array) when the fileId is absent', () => {
    const selection = [makeDoc(1)]
    const result = removeFromSelection(selection, 999)
    expect(result.map((d) => d.fileId)).toEqual([1])
    expect(result).not.toBe(selection)
  })
})

describe('toFileIds', () => {
  it('maps selection objects to a numeric file_ids array', () => {
    const selection = [makeDoc(7), makeDoc(42)]
    expect(toFileIds(selection)).toEqual([7, 42])
  })

  it('returns an empty array for no selection', () => {
    expect(toFileIds([])).toEqual([])
  })
})

describe('formatSelectionLabel', () => {
  it('prefers title over filename', () => {
    const doc = makeDoc(1, { title: 'My Report' })
    expect(formatSelectionLabel(doc)).toBe('My Report')
  })

  it('falls back to filename when title is empty', () => {
    expect(formatSelectionLabel(makeDoc(1))).toBe('file-1.pdf')
  })
})