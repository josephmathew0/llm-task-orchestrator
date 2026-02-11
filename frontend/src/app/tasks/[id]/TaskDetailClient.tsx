// frontend/src/app/tasks/[id]/TaskDetailClient.tsx
'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

type Task = {
  id: string;
  name: string;
  prompt: string;
  status:
    | 'scheduled'
    | 'queued'
    | 'running'
    | 'completed'
    | 'failed'
    | 'cancelled'
    | string;
  scheduled_for: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  output: string | null;
  error: string | null;
  parent_task_id: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  latency_ms: number | null;

  attempts?: number;
  max_attempts?: number;
};

type ChainPayload = {
  name: string;
  instruction: string;
  scheduled_for: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

/**
 * Convert an API datetime string (UTC ISO) into a readable local string.
 * If the value is missing or invalid, we show a fallback.
 */
function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString();
}

/**
 * Convert <input type="datetime-local"> value into a UTC ISO string.
 *
 * Important:
 * - datetime-local has no timezone info; JS Date(...) interprets it as local time.
 * - toISOString() converts that local time into a UTC timestamp.
 */
function toUtcIsoFromDatetimeLocal(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    throw new Error('Invalid datetime');
  }
  return d.toISOString();
}

/**
 * Task statuses that should be treated as "in progress" from a UI perspective.
 * (We poll while a task is in one of these states.)
 */
function isActiveStatus(status: string) {
  return status === 'queued' || status === 'running' || status === 'scheduled';
}

/**
 * Task statuses that are terminal and should not transition anymore.
 * (Cancel is idempotent, but we still disable the button for better UX.)
 */
function isTerminalStatus(status: string) {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

function statusBadgeStyle(status: string) {
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 14px',
    borderRadius: 999,
    fontSize: 13,
    fontWeight: 600,
    border: '1px solid rgba(255,255,255,0.10)',
    background: 'rgba(255,255,255,0.06)',
    color: 'rgba(255,255,255,0.92)',
    backdropFilter: 'blur(10px)',
  };

  if (status === 'completed')
    return {
      ...base,
      background: 'rgba(34,197,94,0.14)',
      borderColor: 'rgba(34,197,94,0.30)',
    };
  if (status === 'failed')
    return {
      ...base,
      background: 'rgba(239,68,68,0.14)',
      borderColor: 'rgba(239,68,68,0.30)',
    };
  if (status === 'cancelled')
    return {
      ...base,
      background: 'rgba(148,163,184,0.14)',
      borderColor: 'rgba(148,163,184,0.30)',
    };
  if (status === 'running')
    return {
      ...base,
      background: 'rgba(59,130,246,0.14)',
      borderColor: 'rgba(59,130,246,0.30)',
    };
  if (status === 'queued' || status === 'scheduled')
    return {
      ...base,
      background: 'rgba(234,179,8,0.14)',
      borderColor: 'rgba(234,179,8,0.30)',
    };

  return base;
}

function statusDotColor(status: string) {
  if (status === 'completed') return 'rgb(34,197,94)';
  if (status === 'failed') return 'rgb(239,68,68)';
  if (status === 'cancelled') return 'rgb(148,163,184)';
  if (status === 'running') return 'rgb(59,130,246)';
  if (status === 'queued') return 'rgb(234,179,8)';
  if (status === 'scheduled') return 'rgb(234,179,8)';
  return 'rgba(255,255,255,0.55)';
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export default function TaskDetailClient({ id }: { id: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Chaining state
  const [chainName, setChainName] = useState('Chained Task');
  const [instruction, setInstruction] = useState(
    'Summarize the parent output into exactly 2 bullet points.'
  );
  const [isChaining, setIsChaining] = useState(false);
  const [chainError, setChainError] = useState<string | null>(null);

  // Scheduling UI state for chained task
  const [chainRunMode, setChainRunMode] = useState<'now' | 'later'>('now');
  const [chainScheduledLocal, setChainScheduledLocal] = useState<string>('');

  // Cancellation state
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const shouldPoll = useMemo(() => {
    if (!task) return false;
    return isActiveStatus(task.status);
  }, [task]);

  const fetchTask = useCallback(async () => {
    const res = await fetch(`${API_BASE}/tasks/${id}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to fetch task (${res.status})`);
    const data = (await res.json()) as Task;
    setTask(data);
    setErrorMsg(null);
  }, [id]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        setLoading(true);
        await fetchTask();
      } catch (e: unknown) {
        if (!cancelled) setErrorMsg(getErrorMessage(e, 'Unknown error'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [fetchTask]);

  // Poll while task is active (queued/running/scheduled)
  useEffect(() => {
    if (!shouldPoll) return;

    const interval = setInterval(() => {
      fetchTask().catch(() => {});
    }, 1200);

    return () => clearInterval(interval);
  }, [shouldPoll, fetchTask]);

  async function chainTask(payload: ChainPayload) {
    setIsChaining(true);
    setChainError(null);

    try {
      const res = await fetch(`${API_BASE}/tasks/${id}/chain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let detail = `Failed to chain task (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail) detail = body.detail;
        } catch {}
        throw new Error(detail);
      }

      const child = (await res.json()) as Task;
      window.location.href = `/tasks/${child.id}`;
    } catch (e: unknown) {
      setChainError(getErrorMessage(e, 'Unknown error'));
    } finally {
      setIsChaining(false);
    }
  }

  /**
   * Cancel the current task.
   *
   * Notes:
   * - Backend cancellation is idempotent; calling cancel multiple times is safe.
   * - "running" cancellation is best-effort: the worker may finish the LLM call before it observes cancellation.
   */
  async function cancelTask() {
    setIsCancelling(true);
    setCancelError(null);

    try {
      const res = await fetch(`${API_BASE}/tasks/${id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // We don't require a body today, but leaving room for future "reason" support:
        body: JSON.stringify({}),
      });

      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`Cancel failed (${res.status})${txt ? `: ${txt}` : ''}`);
      }

      const updated = (await res.json()) as Task;
      setTask(updated);

      // Pull fresh state shortly after, in case the backend updates timestamps or worker races.
      setTimeout(() => {
        fetchTask().catch(() => {});
      }, 400);
    } catch (e: unknown) {
      setCancelError(getErrorMessage(e, 'Unknown error'));
    } finally {
      setIsCancelling(false);
    }
  }

  if (loading) return <p style={{ padding: 20 }}>Loading task…</p>;
  if (errorMsg)
    return (
      <p style={{ padding: 20, color: 'rgb(239,68,68)' }}>Error: {errorMsg}</p>
    );
  if (!task) return <p style={{ padding: 20 }}>Task not found.</p>;

  const attemptsText =
    typeof task.attempts === 'number' && typeof task.max_attempts === 'number'
      ? `${task.attempts} / ${task.max_attempts}`
      : '—';

  const canUseOutputAsInput = task.status === 'completed' && !!task.output;

  const chainDisabled =
    isChaining ||
    !instruction.trim() ||
    task.status !== 'completed' ||
    !task.output;

  const cancelDisabled =
    isCancelling || isTerminalStatus(task.status);

  function buildScheduledFor(): string | null {
    if (chainRunMode === 'now') return null;
    if (!chainScheduledLocal)
      throw new Error('Please pick a date/time for scheduling.');
    return toUtcIsoFromDatetimeLocal(chainScheduledLocal);
  }

  return (
    <div style={pageWrap}>
      <div style={pageInner}>
        <header style={headerRow}>
          <Link href="/" style={backLink}>
            ← Back to tasks
          </Link>

          <span style={statusBadgeStyle(task.status)}>
            <span style={{ ...dot, background: statusDotColor(task.status) }} />
            {task.status}
          </span>
        </header>

        <section style={card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0 }}>
              <h1 style={title}>{task.name}</h1>
              <div style={{ marginTop: 8, opacity: 0.8, fontSize: 12 }}>
                Task ID:{' '}
                <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace' }}>
                  {task.id}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => fetchTask().catch(() => {})}
                style={secondaryButton}
                type="button"
              >
                Refresh
              </button>

              <button
                onClick={() => cancelTask().catch(() => {})}
                style={{
                  ...dangerButton,
                  opacity: cancelDisabled ? 0.55 : 1,
                  cursor: cancelDisabled ? 'not-allowed' : 'pointer',
                }}
                disabled={cancelDisabled}
                title={
                  isTerminalStatus(task.status)
                    ? 'This task is already finished.'
                    : task.status === 'running'
                      ? 'Best-effort cancel: the worker may finish before it observes cancellation.'
                      : 'Cancel this task so it will not run.'
                }
                type="button"
              >
                {isCancelling ? 'Cancelling…' : 'Cancel task'}
              </button>
            </div>
          </div>

          {cancelError && (
            <p style={{ marginTop: 12, color: 'rgb(239,68,68)', marginBottom: 0 }}>
              Error: {cancelError}
            </p>
          )}

          {task.status === 'running' && (
            <p style={{ marginTop: 12, marginBottom: 0, fontSize: 12, opacity: 0.75 }}>
              Note: cancelling a <b>running</b> task is best-effort. If the mock/LLM call finishes before the worker
              sees the cancelled status, it may still complete.
            </p>
          )}

          <div style={grid2}>
            <Info label="Created" value={formatDate(task.created_at)} />
            <Info label="Scheduled for" value={formatDate(task.scheduled_for)} />
            <Info label="Started" value={formatDate(task.started_at)} />
            <Info label="Finished" value={formatDate(task.finished_at)} />
            <Info
              label="Latency"
              value={task.latency_ms != null ? `${task.latency_ms} ms` : '—'}
            />
            <Info label="Attempts" value={attemptsText} />

            <Info label="LLM Provider" value={task.llm_provider ?? '—'} />
            <Info label="LLM Model" value={task.llm_model ?? '—'} />

            <Info
              label="Chained from"
              value={
                task.parent_task_id ? (
                  <Link href={`/tasks/${task.parent_task_id}`} style={idLink}>
                    {task.parent_task_id}
                  </Link>
                ) : (
                  '—'
                )
              }
            />
          </div>
        </section>

        <section style={card}>
          <h2 style={sectionTitle}>Chain this task</h2>
          <p style={muted}>
            Create a new task using this task’s output as context.
          </p>

          <div style={{ display: 'grid', gap: 12 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={labelText}>Child task name</span>
              <input
                value={chainName}
                onChange={(e) => setChainName(e.target.value)}
                style={inputStyle}
                placeholder="Chained Task"
              />
            </label>

            <label style={{ display: 'grid', gap: 6 }}>
              <span style={labelText}>Instruction for the child task</span>
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                style={{ ...inputStyle, minHeight: 90, resize: 'vertical' }}
                placeholder="Tell the child task what to do with the parent output..."
              />
            </label>

            {/* Schedule toggle + datetime-local */}
            <div style={{ display: 'grid', gap: 8 }}>
              <span style={labelText}>Run time</span>

              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
                <label style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 12, opacity: 0.9 }}>
                  <input
                    type="radio"
                    name="chainRunMode"
                    checked={chainRunMode === 'now'}
                    onChange={() => setChainRunMode('now')}
                  />
                  Run now
                </label>

                <label style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 12, opacity: 0.9 }}>
                  <input
                    type="radio"
                    name="chainRunMode"
                    checked={chainRunMode === 'later'}
                    onChange={() => setChainRunMode('later')}
                  />
                  Schedule for later
                </label>
              </div>

              {chainRunMode === 'later' && (
                <div style={{ display: 'grid', gap: 6, maxWidth: 360 }}>
                  <input
                    style={inputStyle}
                    type="datetime-local"
                    value={chainScheduledLocal}
                    onChange={(e) => setChainScheduledLocal(e.target.value)}
                  />
                  <div style={{ fontSize: 12, opacity: 0.75 }}>
                    We convert this local time to UTC before sending to the API.
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() => {
                  try {
                    const scheduled_for = buildScheduledFor();
                    chainTask({
                      name: chainName.trim() || 'Chained Task',
                      instruction: instruction.trim(),
                      scheduled_for,
                    });
                  } catch (e: unknown) {
                    setChainError(getErrorMessage(e, 'Invalid schedule time'));
                  }
                }}
                disabled={chainDisabled}
                style={{
                  ...primaryButton,
                  opacity: chainDisabled ? 0.55 : 1,
                  cursor: chainDisabled ? 'not-allowed' : 'pointer',
                }}
                title={
                  task.status !== 'completed' || !task.output
                    ? 'This button becomes available after the task is completed with output.'
                    : chainRunMode === 'later'
                      ? 'Create a scheduled child task'
                      : 'Create a child task'
                }
                type="button"
              >
                {isChaining
                  ? 'Creating…'
                  : chainRunMode === 'later'
                    ? 'Schedule Chained Task'
                    : 'Use Output as New Task Input'}
              </button>

              <button
                onClick={() => fetchTask().catch(() => {})}
                style={secondaryButton}
                type="button"
              >
                Refresh
              </button>
            </div>

            {chainError && (
              <p style={{ color: 'rgb(239,68,68)', margin: 0 }}>
                Error: {chainError}
              </p>
            )}

            {!canUseOutputAsInput && (
              <p style={{ margin: 0, fontSize: 12, opacity: 0.75 }}>
                Use Output as New Task Input becomes available after the task is{' '}
                <b>completed</b> with output.
              </p>
            )}
          </div>
        </section>

        <TwoCol title="Prompt" value={task.prompt} />
        <TwoCol title="Output" value={task.output ?? '—'} />
        {task.error && <TwoCol title="Error" value={task.error} tone="error" />}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={infoCard}>
      <div style={infoLabel}>{label}</div>
      <div style={infoValue}>{value}</div>
    </div>
  );
}

function TwoCol({
  title,
  value,
  tone,
}: {
  title: string;
  value: string;
  tone?: 'error';
}) {
  return (
    <section
      style={{
        ...card,
        borderColor:
          tone === 'error' ? 'rgba(239,68,68,0.25)' : 'rgba(255,255,255,0.10)',
        background:
          tone === 'error'
            ? 'rgba(239,68,68,0.08)'
            : 'rgba(255,255,255,0.04)',
      }}
    >
      <h2 style={sectionTitle}>{title}</h2>
      <pre style={preStyle}>{value}</pre>
    </section>
  );
}

/** ---------- styles (match main page dark scheme) ---------- */

const pageWrap: React.CSSProperties = {
  minHeight: '100vh',
  background:
    'radial-gradient(900px 400px at 15% 0%, rgba(56,189,248,0.18), transparent 55%), radial-gradient(900px 500px at 70% 10%, rgba(34,197,94,0.10), transparent 60%), radial-gradient(1200px 800px at 50% 110%, rgba(59,130,246,0.10), transparent 60%), linear-gradient(180deg, rgba(8,12,18,1), rgba(7,10,16,1))',
  color: 'rgba(255,255,255,0.92)',
  padding: 24,
};

const pageInner: React.CSSProperties = {
  maxWidth: 1040,
  margin: '0 auto',
  display: 'grid',
  gap: 16,
};

const headerRow: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
};

const backLink: React.CSSProperties = {
  textDecoration: 'none',
  color: 'rgba(255,255,255,0.85)',
  padding: '8px 10px',
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.10)',
  background: 'rgba(255,255,255,0.04)',
};

const idLink: React.CSSProperties = {
  textDecoration: 'none',
  color: 'rgba(255,255,255,0.90)',
  borderBottom: '1px dashed rgba(255,255,255,0.25)',
};

const dot: React.CSSProperties = {
  width: 9,
  height: 9,
  borderRadius: 999,
  boxShadow: '0 0 0 3px rgba(255,255,255,0.06) inset',
};

const card: React.CSSProperties = {
  border: '1px solid rgba(255,255,255,0.10)',
  borderRadius: 18,
  padding: 18,
  background: 'rgba(255,255,255,0.04)',
  backdropFilter: 'blur(10px)',
  boxShadow: '0 10px 30px rgba(0,0,0,0.25)',
};

const title: React.CSSProperties = {
  margin: 0,
  fontSize: 30,
  letterSpacing: '-0.02em',
};

const sectionTitle: React.CSSProperties = {
  marginTop: 0,
  marginBottom: 10,
  fontSize: 16,
  letterSpacing: '0.01em',
  opacity: 0.95,
};

const muted: React.CSSProperties = {
  marginTop: 0,
  opacity: 0.8,
};

const labelText: React.CSSProperties = {
  fontSize: 12,
  opacity: 0.8,
};

const grid2: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
  gap: 12,
  marginTop: 14,
};

const infoCard: React.CSSProperties = {
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 14,
  padding: 12,
  background: 'rgba(0,0,0,0.18)',
};

const infoLabel: React.CSSProperties = {
  fontSize: 12,
  opacity: 0.72,
};

const infoValue: React.CSSProperties = {
  marginTop: 6,
  wordBreak: 'break-word',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(150,150,150,0.22)',
  color: 'rgba(255,255,255,0.92)',
  outline: 'none',
};

const primaryButton: React.CSSProperties = {
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.14)',
  background:
    'linear-gradient(135deg, rgba(59,130,246,0.35), rgba(34,197,94,0.25))',
  color: 'rgba(255,255,255,0.92)',
  fontWeight: 700,
  boxShadow: '0 10px 20px rgba(0,0,0,0.25)',
};

const secondaryButton: React.CSSProperties = {
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.06)',
  color: 'rgba(255,255,255,0.92)',
  fontWeight: 700,
  cursor: 'pointer',
};

const dangerButton: React.CSSProperties = {
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(239,68,68,0.22)',
  background: 'rgba(239,68,68,0.10)',
  color: 'rgba(255,255,255,0.92)',
  fontWeight: 800,
  boxShadow: '0 10px 20px rgba(0,0,0,0.25)',
};

const preStyle: React.CSSProperties = {
  margin: 0,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  fontSize: 13,
  lineHeight: 1.55,
  opacity: 0.95,
  background: 'rgba(0,0,0,0.18)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 14,
  padding: 14,
};
