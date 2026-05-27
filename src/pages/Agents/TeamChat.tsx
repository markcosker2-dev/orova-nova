import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bot, Send, User, Loader2, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTeamsStore } from '@/stores/teams';
import { useAgentsStore } from '@/stores/agents';
import { useChatStore, type RawMessage } from '@/stores/chat';
import { subscribeHostEvent } from '@/lib/host-events';
import { extractText } from '@/pages/Chat/message-utils';
import { AcpActivityPanel } from './components/AcpActivityPanel';
import type { AcpActivity } from '@/types/team';

export function TeamChatPage() {
  const { teamId } = useParams<{ teamId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('agents');
  const { teams, acpActivities, pushAcpActivity } = useTeamsStore();
  const { agents } = useAgentsStore();

  const team = teams.find((tm) => tm.id === teamId);
  const orchestrator = agents.find((a) => a.id === team?.orchestratorId);

  // Resolve session key for the orchestrator agent
  const orchestratorSessionKey = useMemo(() => {
    if (!orchestrator) return null;
    return orchestrator.mainSessionKey || `agent:${orchestrator.id}:main`;
  }, [orchestrator]);

  // Chat store selectors
  const messages = useChatStore((s) => s.messages);
  const sending = useChatStore((s) => s.sending);
  const loading = useChatStore((s) => s.loading);
  const streamingMessage = useChatStore((s) => s.streamingMessage);
  const error = useChatStore((s) => s.error);
  const currentSessionKey = useChatStore((s) => s.currentSessionKey);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const switchSession = useChatStore((s) => s.switchSession);
  const abortRun = useChatStore((s) => s.abortRun);
  const clearError = useChatStore((s) => s.clearError);

  // Switch to orchestrator's session on mount
  useEffect(() => {
    if (orchestratorSessionKey && currentSessionKey !== orchestratorSessionKey) {
      switchSession(orchestratorSessionKey);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- avoid loop: only trigger on key/fn change
  }, [orchestratorSessionKey, switchSession]);

  // Extract streaming text for partial display
  const streamText = useMemo(() => {
    if (!streamingMessage) return '';
    if (typeof streamingMessage === 'object') {
      return extractText(streamingMessage as RawMessage);
    }
    return typeof streamingMessage === 'string' ? streamingMessage : '';
  }, [streamingMessage]);

  // ACP activity subscription
  useEffect(() => {
    const unsubscribe = subscribeHostEvent<AcpActivity>('acp:activity', (activity) => {
      if (activity.teamId === teamId) {
        pushAcpActivity(activity);
      }
    });
    return () => {
      if (typeof unsubscribe === 'function') {
        unsubscribe();
      }
    };
  }, [teamId, pushAcpActivity]);

  // Auto-scroll on new content
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamText, acpActivities]);

  // Input state & send handler
  const [input, setInput] = useState('');

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    sendMessage(text, undefined, orchestrator?.id);
  }, [input, sending, sendMessage, orchestrator?.id]);

  if (!team || !orchestrator) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-10">
        <p className="text-muted-foreground">{t('teams.notFound')}</p>
        <Button onClick={() => navigate('/agents')} className="mt-4 rounded-full">
          {t('common:actions.back')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col -m-6 dark:bg-background h-[calc(100vh-2.5rem)] overflow-hidden">
      {/* Header */}
      <div className="w-full shrink-0 border-b border-black/10 dark:border-white/10 bg-[#f3f1e9] dark:bg-card p-4 px-6 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            onClick={() => navigate('/agents')}
            className="h-8 text-[13px] rounded-full"
          >
            {t('common:actions.back')}
          </Button>
          <div>
            <h2 className="text-lg font-serif font-medium">{team.name}</h2>
            <p className="text-[12px] text-muted-foreground">
              {orchestrator.name} (Orchestrator)
            </p>
          </div>
        </div>
        {sending && (
          <Button
            variant="ghost"
            size="sm"
            onClick={abortRun}
            className="h-8 text-[13px] rounded-full text-destructive hover:text-destructive"
          >
            <Square className="h-3 w-3 mr-1.5 fill-current" />
            {t('common:actions.stop', 'Stop')}
          </Button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-white dark:bg-background">
        <div className="max-w-3xl mx-auto w-full space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : messages.length === 0 && !streamText ? (
            <div className="text-center text-muted-foreground py-10 mt-10">
              <Bot className="h-12 w-12 mx-auto mb-4 opacity-20" />
              <p>{t('teams.chatEmpty')}</p>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                <MessageBubble key={msg.id ?? idx} message={msg} />
              ))}
              {/* Streaming partial response */}
              {sending && streamText && (
                <div className="flex gap-4">
                  <div className="h-8 w-8 shrink-0 rounded-full flex items-center justify-center bg-muted text-foreground">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex flex-col gap-2 max-w-[80%] items-start">
                    <div className="px-4 py-3 rounded-2xl text-[14px] bg-muted text-foreground rounded-tl-sm whitespace-pre-wrap">
                      {streamText}
                      <span className="inline-block w-1.5 h-4 bg-foreground/60 ml-0.5 animate-pulse" />
                    </div>
                  </div>
                </div>
              )}
              {/* Thinking indicator (no stream text yet) */}
              {sending && !streamText && (
                <div className="flex gap-4">
                  <div className="h-8 w-8 shrink-0 rounded-full flex items-center justify-center bg-muted text-foreground">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex items-center gap-2 px-4 py-3 rounded-2xl bg-muted text-foreground rounded-tl-sm">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span className="text-[13px] text-muted-foreground">
                      {t('teams.thinking', 'Thinking...')}
                    </span>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Error display */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 text-destructive text-[13px]">
              <span>{error}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearError}
                className="h-6 text-[11px] rounded-full ml-auto"
              >
                {t('common:actions.dismiss', 'Dismiss')}
              </Button>
            </div>
          )}

          {/* ACP activity overlay */}
          {acpActivities.length > 0 && (
            <AcpActivityPanel activities={acpActivities} />
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="w-full shrink-0 border-t border-black/10 dark:border-white/10 bg-[#f3f1e9] dark:bg-card p-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={t('teams.chatPlaceholder')}
            className="flex-1 h-[44px] rounded-full px-5 font-mono text-[14px] bg-white dark:bg-background border border-black/10 dark:border-white/10 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all shadow-sm"
            disabled={sending}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="h-[44px] w-[44px] rounded-full shrink-0 p-0"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Single message bubble — extracted for clarity */
function MessageBubble({ message }: { message: RawMessage }) {
  const text = extractText(message);
  if (!text) return null;

  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`h-8 w-8 shrink-0 rounded-full flex items-center justify-center ${isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`flex flex-col gap-2 max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}
      >
        <div
          className={`px-4 py-3 rounded-2xl text-[14px] whitespace-pre-wrap ${isUser ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-muted text-foreground rounded-tl-sm'}`}
        >
          {text}
        </div>
      </div>
    </div>
  );
}
