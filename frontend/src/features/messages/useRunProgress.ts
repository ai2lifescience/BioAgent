import { useCallback, useRef, useState } from 'react';
import type { ProgressEntry, StreamFrame } from '../../types';

import { advanceProgress, completedProgress } from './progress';

export function useRunProgress() {
  const [entries, setEntries] = useState<ProgressEntry[]>([]);
  const current = useRef<ProgressEntry[]>([]);
  const reset = useCallback(() => { current.current = []; setEntries([]); }, []);
  const onFrame = useCallback((frame: StreamFrame) => {
    const next = advanceProgress(current.current, frame);
    if (next !== current.current) { current.current = next; setEntries(next); }
  }, []);
  const finish = useCallback((answer = '') => {
    const snapshot = completedProgress(current.current, answer);
    reset();
    return snapshot;
  }, [reset]);
  return { entries, reset, onFrame, finish };
}
