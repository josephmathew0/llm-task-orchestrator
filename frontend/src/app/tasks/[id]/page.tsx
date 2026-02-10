// frontend/src/app/tasks/[id]/pageToRoute.tsx

import TaskDetailClient from './TaskDetailClient';

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <TaskDetailClient id={id} />;
}
