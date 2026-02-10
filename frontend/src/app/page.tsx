'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

type Task = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  parent_task_id: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

function formatStatus(s: string) {
  return s?.toLowerCase?.() ?? s;
}

function StatusPill({ status }: { status: string }) {
  const s = formatStatus(status);
  const style: React.CSSProperties = useMemo(() => {
    const base: React.CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      padding: '4px 10px',
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 600,
      border: '1px solid rgba(0,0,0,0.08)',
      background: 'rgba(0,0,0,0.04)',
    };

    if (s === 'completed')
      return { ...base, background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.25)' };
    if (s === 'running')
      return { ...base, background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.25)' };
    if (s === 'queued' || s === 'scheduled')
      return { ...base, background: 'rgba(234,179,8,0.12)', border: '1px solid rgba(234,179,8,0.25)' };
    if (s === 'failed')
      return { ...base, background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)' };

    return base;
  }, [s]);

  const dotStyle: React.CSSProperties = useMemo(() => {
    const base = { width: 8, height: 8, borderRadius: 999 };
    if (s === 'completed') return { ...base, background: 'rgb(34,197,94)' };
    if (s === 'running') return { ...base, background: 'rgb(59,130,246)' };
    if (s === 'queued' || s === 'scheduled') return { ...base, background: 'rgb(234,179,8)' };
    if (s === 'failed') return { ...base, background: 'rgb(239,68,68)' };
    return { ...base, background: 'rgba(0,0,0,0.35)' };
  }, [s]);

  return (
    <span style={style} title={`Status: ${status}`}>
      <span style={dotStyle} />
      {s}
    </span>
  );
}

export default function HomePage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // UI state
  const [query, setQuery] = useState('');
  const [hideCompleted, setHideCompleted] = useState(false);

  async function fetchTasks() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/tasks`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Failed to fetch tasks (${res.status})`);
      const data = await res.json();
      setTasks(data);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tasks.filter(t => {
      if (hideCompleted && formatStatus(t.status) === 'completed') return false;
      if (!q) return true;
      return (
        t.name?.toLowerCase?.().includes(q) ||
        t.id?.toLowerCase?.().includes(q) ||
        (t.parent_task_id?.toLowerCase?.().includes(q) ?? false) ||
        t.status?.toLowerCase?.().includes(q)
      );
    });
  }, [tasks, query, hideCompleted]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);

    const trimmedName = name.trim();
    const trimmedPrompt = prompt.trim();

    if (!trimmedName) {
      setCreateError('Please enter a name.');
      return;
    }
    if (!trimmedPrompt) {
      setCreateError('Please enter a prompt.');
      return;
    }

    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: trimmedName,
          prompt: trimmedPrompt,
          scheduled_for: null,
        }),
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`Create failed (${res.status}): ${txt}`);
      }

      const created: Task = await res.json();

      // Put newest at top immediately (optimistic-ish)
      setTasks(prev => [created, ...prev]);

      // Clear inputs
      setName('');
      setPrompt('');

      // Optionally: auto-navigate to detail page
      // window.location.href = `/tasks/${created.id}`;
    } catch (err: any) {
      setCreateError(err?.message ?? 'Failed to create task');
    } finally {
      setCreating(false);
    }
  }

  const container: React.CSSProperties = {
    minHeight: '100vh',
    padding: '28px 16px',
    background:
      'radial-gradient(1200px 600px at 20% 0%, rgba(59,130,246,0.12), transparent 60%), radial-gradient(1200px 600px at 80% 10%, rgba(34,197,94,0.10), transparent 55%), #0b0f1a',
    color: 'rgba(255,255,255,0.92)',
    fontFamily:
      'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji"',
  };

  const card: React.CSSProperties = {
    maxWidth: 980,
    margin: '0 auto',
    display: 'grid',
    gridTemplateColumns: '1fr',
    gap: 16,
  };

  const panel: React.CSSProperties = {
    background: 'rgba(255,255,255,0.06)',
    border: '1px solid rgba(255,255,255,0.10)',
    borderRadius: 16,
    padding: 18,
    boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
    backdropFilter: 'blur(10px)',
  };

  const input: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    borderRadius: 12,
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(0,0,0,0.28)',
    color: 'rgba(255,255,255,0.92)',
    outline: 'none',
  };

  const textarea: React.CSSProperties = {
    ...input,
    minHeight: 110,
    resize: 'vertical',
    lineHeight: 1.4,
  };

  const button: React.CSSProperties = {
    padding: '10px 14px',
    borderRadius: 12,
    border: '1px solid rgba(255,255,255,0.14)',
    background: 'rgba(255,255,255,0.10)',
    color: 'rgba(255,255,255,0.92)',
    fontWeight: 700,
    cursor: 'pointer',
  };

  const buttonPrimary: React.CSSProperties = {
    ...button,
    background: 'linear-gradient(135deg, rgba(59,130,246,0.55), rgba(34,197,94,0.45))',
    border: '1px solid rgba(255,255,255,0.18)',
  };

  const subtle: React.CSSProperties = { color: 'rgba(255,255,255,0.7)' };

  return (
    <main style={container}>
      <div style={card}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 28, letterSpacing: 0.2 }}>LLM Tasks</h1>
            <p style={{ margin: '6px 0 0', ...subtle }}>
              Create tasks, view status, and chain new tasks from previous outputs.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button style={button} onClick={fetchTasks} disabled={loading}>
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Create */}
        <section style={panel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Create a new task</h2>
            <span style={{ fontSize: 12, ...subtle }}>API: {API_BASE}</span>
          </div>

          <form onSubmit={onCreate} style={{ marginTop: 12, display: 'grid', gap: 10 }}>
            <div style={{ display: 'grid', gap: 6 }}>
              <label style={{ fontSize: 12, ...subtle }}>Task name</label>
              <input
                style={input}
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder='e.g., "Summarize meeting notes"'
                maxLength={200}
              />
            </div>

            <div style={{ display: 'grid', gap: 6 }}>
              <label style={{ fontSize: 12, ...subtle }}>Prompt</label>
              <textarea
                style={textarea}
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="Write your instruction to the model…"
              />
            </div>

            {createError && (
              <div
                style={{
                  padding: '10px 12px',
                  borderRadius: 12,
                  background: 'rgba(239,68,68,0.12)',
                  border: '1px solid rgba(239,68,68,0.22)',
                  color: 'rgba(255,255,255,0.92)',
                  fontSize: 13,
                }}
              >
                {createError}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button type="submit" style={buttonPrimary} disabled={creating}>
                {creating ? 'Creating…' : 'Create task'}
              </button>

              <button
                type="button"
                style={button}
                onClick={() => {
                  setName('');
                  setPrompt('');
                  setCreateError(null);
                }}
                disabled={creating}
              >
                Clear
              </button>

              <span style={{ marginLeft: 'auto', fontSize: 12, ...subtle }}>
                Tip: after it completes, open it and use “Chain this task”.
              </span>
            </div>
          </form>
        </section>

        {/* List controls */}
        <section style={panel}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18 }}>Task history</h2>
              <div style={{ marginTop: 4, fontSize: 12, ...subtle }}>
                Showing <strong style={{ color: 'rgba(255,255,255,0.92)' }}>{filtered.length}</strong> of{' '}
                <strong style={{ color: 'rgba(255,255,255,0.92)' }}>{tasks.length}</strong>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <input
                style={{ ...input, width: 280 }}
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search by name, id, status…"
              />

              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, ...subtle }}>
                <input
                  type="checkbox"
                  checked={hideCompleted}
                  onChange={e => setHideCompleted(e.target.checked)}
                />
                Hide completed
              </label>
            </div>
          </div>

          {/* Loading/error */}
          {loading && <p style={{ marginTop: 12, ...subtle }}>Loading tasks…</p>}
          {error && (
            <p style={{ marginTop: 12, color: 'rgba(239,68,68,0.95)' }}>
              Error: {error}
            </p>
          )}

          {/* List */}
          {!loading && !error && (
            <>
              {filtered.length === 0 ? (
                <p style={{ marginTop: 12, ...subtle }}>No tasks match your filters.</p>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 0', display: 'grid', gap: 10 }}>
                  {filtered.map(task => (
                    <li
                      key={task.id}
                      style={{
                        padding: 14,
                        borderRadius: 14,
                        border: '1px solid rgba(255,255,255,0.10)',
                        background: 'rgba(0,0,0,0.22)',
                        display: 'flex',
                        gap: 12,
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                          <Link
                            href={`/tasks/${task.id}`}
                            style={{
                              color: 'rgba(255,255,255,0.95)',
                              textDecoration: 'none',
                              fontWeight: 800,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: 520,
                            }}
                            title={task.name}
                          >
                            {task.name || '(unnamed)'}
                          </Link>
                          <StatusPill status={task.status} />
                        </div>

                        <div style={{ marginTop: 6, fontSize: 12, ...subtle }}>
                          Created: {new Date(task.created_at).toLocaleString()}
                        </div>

                        {task.parent_task_id && (
                          <div style={{ marginTop: 6, fontSize: 12, ...subtle }}>
                            Chained from:{' '}
                            <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace' }}>
                              {task.parent_task_id}
                            </span>
                          </div>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                        <Link
                          href={`/tasks/${task.id}`}
                          style={{
                            ...button,
                            textDecoration: 'none',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          View →
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        {/* Footer */}
        <div style={{ textAlign: 'center', fontSize: 12, ...subtle }}>
          Tip: A tool for Vinci4D
        </div>
      </div>
    </main>
  );
}
