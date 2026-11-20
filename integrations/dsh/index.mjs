import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';

export const name = 'agentping-notifications';
export const inject = ['agents', 'sessions'];

/** Observe committed root-turn events and human interaction entry points. */
export function apply(ctx, config) {
  if (!config?.receiver || !config?.python) throw new Error('AgentPing requires receiver and python paths');
  const children = new Set();
  const send = (payload) => {
    const child = spawn(config.python, [config.receiver, 'dsh'], { stdio: ['pipe', 'ignore', 'ignore'] });
    children.add(child);
    const timer = setTimeout(() => child.kill(), 5000);
    child.on('error', () => { clearTimeout(timer); children.delete(child); });
    child.on('close', () => { clearTimeout(timer); children.delete(child); });
    child.stdin.on('error', () => {}); // Receiver exit / timeout must not affect a source task.
    child.stdin.end(JSON.stringify(payload));
  };
  const rootAgent = (agent) => agent && ctx.agents.get(agent.id) !== undefined && agent.session.header.origin !== 'subagent';
  const rootSession = (session) => ctx.agents.get(session.id) !== undefined && session.header.origin !== 'subagent';
  const observe = (callback) => {
    try { callback(); }
    catch (error) { console.error('AgentPing observer failed:', error instanceof Error ? error.name : 'Error'); }
  };

  ctx.on('session/event', (session, event) => {
    if (event.type !== 'turn/end' || !rootSession(session)) return;
    const reason = event.data.reason?.kind;
    if (reason !== 'completed' && reason !== 'error' && reason !== 'max-tokens') return;
    send({ hook_event_name: reason === 'completed' ? 'TurnCompleted' : 'TurnFailed',
      session_id: String(session.id), turn_id: String(event.data.turn),
      event_id: `dsh:turn:${session.id}:${event.data.turn}:${event.seq}` });
  }, { global: true });

  ctx.on('user-questions/request', (request, next) => {
    observe(() => {
      if (rootAgent(request.agent)) {
        send({ hook_event_name: 'QuestionRequested', session_id: String(request.agent.id),
          event_id: `dsh:question:${request.agent.id}:${randomUUID()}` });
      }
    });
    return next();
  }, { global: true, prepend: true });

  ctx.on('approval/request', (request, next) => {
    observe(() => {
      if (rootAgent(request.agent)) {
        send({ hook_event_name: 'ApprovalRequested', session_id: String(request.agent.id),
          event_id: `dsh:approval:${request.agent.id}:${randomUUID()}` });
      }
    });
    return next(); // Preserve the original UI answerer and all approval decisions.
  }, { global: true, prepend: true });

  ctx.effect(() => () => { for (const child of children) child.kill(); }, 'AgentPing receiver cleanup');
  send({ hook_event_name: 'Ready' });
}
