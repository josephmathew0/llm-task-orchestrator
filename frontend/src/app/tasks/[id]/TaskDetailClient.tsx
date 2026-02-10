// frontend/src/app/tasks/[id]/TaskDetailClient.tsx
'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

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

function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString();
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
  if (status === 'running')
    return {
      ...base,
      background: 'rgba(59,130,246,0.14)',
      borderColor: 'rgba(59,130,246,0.30)',
    };
  if (status === 'queued')
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
  if (status === 'running') return 'rgb(59,130,246)';
  if (status === 'queued') return 'rgb(234,179,8)';
  return 'rgba(255,255,255,0.55)';
}

export default function TaskDetailClient({ id }: { id: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [chainName, setChainName] = useState('Chained Task');
  const [instruction, setInstruction] = useState(
    'Summarize the parent output into exactly 2 bullet points.'
  );
  const [isChaining, setIsChaining] = useState(false);
  const [chainError, setChainError] = useState<string | null>(null);

  const shouldPoll = useMemo(() => {
    if (!task) return false;
    return (
      task.status === 'queued' ||
      task.status === 'running' ||
      task.status === 'scheduled'
    );
  }, [task]);

  async function fetchTask() {
    const res = await fetch(`${API_BASE}/tasks/${id}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to fetch task (${res.status})`);
    const data = (await res.json()) as Task;
    setTask(data);
    setErrorMsg(null);
  }

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        setLoading(true);
        await fetchTask();
      } catch (e: any) {
        if (!cancelled) setErrorMsg(e?.message ?? 'Unknown error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!shouldPoll) return;

    const interval = setInterval(() => {
      fetchTask().catch(() => {});
    }, 1200);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldPoll, id]);

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
    } catch (e: any) {
      setChainError(e?.message ?? 'Unknown error');
    } finally {
      setIsChaining(false);
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
          <h1 style={title}>{task.name}</h1>

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

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() =>
                  chainTask({
                    name: chainName.trim() || 'Chained Task',
                    instruction: instruction.trim(),
                    scheduled_for: null,
                  })
                }
                disabled={
                  isChaining ||
                  !instruction.trim() ||
                  task.status !== 'completed' ||
                  !task.output
                }
                style={{
                  ...primaryButton,
                  opacity:
                    isChaining ||
                    !instruction.trim() ||
                    task.status !== 'completed' ||
                    !task.output
                      ? 0.55
                      : 1,
                  cursor:
                    isChaining ||
                    !instruction.trim() ||
                    task.status !== 'completed' ||
                    !task.output
                      ? 'not-allowed'
                      : 'pointer',
                }}
                title={
                  task.status !== 'completed' || !task.output
                    ? 'This button becomes available after the task is completed with output.'
                    : 'Create a child task'
                }
              >
                {isChaining ? 'Creating…' : 'Use Output as New Task Input'}
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
  background: 'rgba(0,0,0,0.22)',
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
