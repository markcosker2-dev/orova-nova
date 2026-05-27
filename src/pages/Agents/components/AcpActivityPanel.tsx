import { useState } from 'react';
import { ChevronRight, ChevronDown, Check, AlertCircle, MessageSquare, Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AcpActivity } from '@/types/team';

export function AcpActivityPanel({ activities }: { activities: AcpActivity[] }) {
  const { t } = useTranslation('agents');
  const [expanded, setExpanded] = useState(false);

  if (activities.length === 0) return null;

  return (
    <div className="border border-black/10 dark:border-white/10 rounded-2xl bg-[#eeece3] dark:bg-muted overflow-hidden mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
      >
        <span className="text-[14px] font-semibold text-foreground/80 flex items-center gap-2">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {t('teams.acpActivity')} ({activities.length})
        </span>
      </button>
      
      {expanded && (
        <div className="p-3 border-t border-black/10 dark:border-white/10 max-h-60 overflow-y-auto space-y-3">
          {activities.map((activity, idx) => (
            <div key={idx} className="flex gap-3 text-[13px]">
              <div className="shrink-0 mt-0.5">
                {activity.type === 'spawn' && <Bot className="h-4 w-4 text-blue-500" />}
                {activity.type === 'message' && <MessageSquare className="h-4 w-4 text-primary" />}
                {activity.type === 'complete' && <Check className="h-4 w-4 text-green-500" />}
                {activity.type === 'error' && <AlertCircle className="h-4 w-4 text-destructive" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground/90">
                    {t(`teams.activity_${activity.type}`)}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {new Date(activity.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                {activity.content && (
                  <div className="mt-1 text-muted-foreground break-words line-clamp-2">
                    {activity.content}
                  </div>
                )}
                <div className="mt-1 text-[11px] font-mono text-muted-foreground/60">
                  {activity.parentAgentId} → {activity.childAgentId}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
