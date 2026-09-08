import { describe, it, expect } from 'vitest'
import { partitionForKnowledgeBase } from '../vaultSelectionService'

const makeDoc = (fileId, indexingStatus = 'INDEXED') => ({
  fileId,
  filename: `file-${fileId}.pdf`,
  indexingStatus,
})

describe('partitionForKnowledgeBase', () => {
  it('splits indexed vs non-indexed', () => {
    const docs = [
      makeDoc(1, 'INDEXED'),
      makeDoc(2, 'PENDING'),
      makeDoc(3, 'INDEXED'),
      makeDoc(4, 'FAILED'),
    ]
    const { toIndex, alreadyIndexed } = partitionForKnowledgeBase(docs)
    expect(alreadyIndexed.map((d) => d.fileId)).toEqual([1, 3])
    expect(toIndex.map((d) => d.fileId)).toEqual([2, 4])
  })

  it('handles empty and null inputs', () => {
    expect(partitionForKnowledgeBase([])).toEqual({ toIndex: [], alreadyIndexed: [] })
    expect(partitionForKnowledgeBase(null)).toEqual({ toIndex: [], alreadyIndexed: [] })
    expect(partitionForKnowledgeBase(undefined)).toEqual({ toIndex: [], alreadyIndexed: [] })
  })

  it('is case-insensitive via isIndexed (lowercase indexed)', () => {
    const docs = [makeDoc(1, 'indexed'), makeDoc(2, 'pending')]
    const { toIndex, alreadyIndexed } = partitionForKnowledgeBase(docs)
    expect(alreadyIndexed).toHaveLength(1)
    expect(toIndex).toHaveLength(1)
  })
})
