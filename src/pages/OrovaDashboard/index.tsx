import { useEffect, useState, useCallback, useRef } from 'react';
import { useOrovaStore, type OrovaLane } from '@/stores/orova';
import {
  Zap, Mail, MessageSquare, Calendar, Phone, FileText,
  RefreshCw, AlertTriangle, ShieldCheck, Cpu
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

export default function OrovaDashboard() {
  const {
    metrics, lanes, health, fetchMetrics, fetchTasksAndLanes, fetchHealth, triggerAction, loading
  } = useOrovaStore();

  const fetchMetricsRef = useRef(fetchMetrics);
  const fetchTasksAndLanesRef = useRef(fetchTasksAndLanes);
  const fetchHealthRef = useRef(fetchHealth);

  fetchMetricsRef.current = fetchMetrics;
  fetchTasksAndLanesRef.current = fetchTasksAndLanes;
  fetchHealthRef.current = fetchHealth;

  const [refreshing, setRefreshing] = useState(false);

const handleRefresh = useCallback(async () => {
      setRefreshing(true);
      try {
        await Promise.all([fetchMetrics(), fetchTasksAndLanes(), fetchHealth()]);
        toast.success('Dashboard metrics refreshed');
      } catch {
        toast.error('Failed to refresh metrics');
      } finally {
        setRefreshing(false);
      }
    }, [fetchMetrics, fetchTasksAndLanes, fetchHealth]);

    useEffect(() => {
      void handleRefresh();
      const interval = setInterval(() => {
        void fetchHealthRef.current();
        void fetchMetricsRef.current();
      }, 15000);
      return () => clearInterval(interval);
    }, [handleRefresh]);

const handleAction = useCallback(async (action: 'hunt-leads' | 'send-emails' | 'generate-report', label: string) => {
     toast.promise(triggerAction(action), {
       loading: `Triggering ${label}...`,
       success: (res) => res.message || `${label} triggered successfully!`,
       error: (_err) => `Failed to trigger ${label}: ${_err.message || _err}`
     });
   }, [triggerAction]);

  const cards = [
    { label: 'Leads Found', value: metrics?.leads_found ?? 0, icon: Cpu, color: 'from-blue-500 to-indigo-500' },
    { label: 'Emails Sent', value: metrics?.emails_sent ?? 0, icon: Mail, color: 'from-amber-500 to-orange-500' },
    { label: 'Replies Received', value: metrics?.replies_received ?? 0, icon: MessageSquare, color: 'from-emerald-500 to-teal-500' },
    { label: 'Meetings Booked', value: metrics?.meetings_booked ?? 0, icon: Calendar, color: 'from-pink-500 to-rose-500' },
    { label: 'Calls Made', value: metrics?.calls_made ?? 0, icon: Phone, color: 'from-cyan-500 to-blue-500' },
    { label: 'Proposals Sent', value: metrics?.proposals_sent ?? 0, icon: FileText, color: 'from-purple-500 to-violet-500' }
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-2.5rem)] overflow-hidden bg-background">
      <div className="w-full max-w-6xl mx-auto p-10 pt-16 flex-1 overflow-y-auto space-y-8">
        
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-5xl font-serif tracking-tight text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
              OROVA Dashboard
            </h1>
            <p className="text-[16px] text-muted-foreground mt-2 font-medium">
              Real-time multi-agent operations control plane.
            </p>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="h-10 w-10 border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 shadow-none rounded-xl"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {/* Health Panel */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 bg-[#eeece3]/40 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="h-12 w-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground font-semibold uppercase tracking-wider">System State</p>
              <h4 className="text-xl font-bold text-foreground mt-0.5">{health?.status || 'Operational'}</h4>
            </div>
          </div>

          <div className="p-6 bg-[#eeece3]/40 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="h-12 w-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400 border border-blue-500/20">
              <Zap className="h-6 w-6" />
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground font-semibold uppercase tracking-wider">Active Swarms</p>
              <h4 className="text-xl font-bold text-foreground mt-0.5">10 Agents Online Swarm</h4>
            </div>
          </div>

          <div className="p-6 bg-[#eeece3]/40 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="h-12 w-12 rounded-xl bg-orange-500/10 flex items-center justify-center text-orange-600 dark:text-orange-400 border border-orange-500/20">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground font-semibold uppercase tracking-wider">Queue Depth</p>
              <h4 className="text-xl font-bold text-foreground mt-0.5">{health?.queue_depth ?? 0} Messages</h4>
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        <div>
          <h3 className="text-lg font-bold text-foreground mb-4">Operations Metrics</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-5">
            {cards.map((card, i) => {
              const Icon = card.icon;
              return (
                <div key={i} className="p-5 bg-[#eeece3]/20 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl flex flex-col justify-between shadow-sm hover:shadow-md transition-all">
                  <div className={`h-10 w-10 rounded-xl bg-gradient-to-tr ${card.color} flex items-center justify-center text-white shadow-sm`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="mt-4">
                    <p className="text-[12px] text-muted-foreground font-bold leading-none">{card.label}</p>
                    <h2 className="text-3xl font-bold tracking-tight text-foreground mt-1.5">{card.value}</h2>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Quick Actions & Worker Lanes */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* Quick Actions */}
          <div className="p-7 bg-[#eeece3]/30 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl space-y-6">
            <div>
              <h3 className="text-lg font-bold text-foreground">Trigger Swarm Operations</h3>
              <p className="text-[13px] text-muted-foreground mt-1">Manual escalation triggers for Nova's primary lanes.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Button
                onClick={() => handleAction('hunt-leads', 'Lead Hunt')}
                className="h-24 bg-gradient-to-tr from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-2xl flex flex-col items-center justify-center gap-2 border-0 shadow-md font-semibold transition-all hover:scale-[1.02]"
              >
                <Cpu className="h-6 w-6" />
                <span>Hunt Leads</span>
              </Button>
              <Button
                onClick={() => handleAction('send-emails', 'Email Outreach')}
                className="h-24 bg-gradient-to-tr from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white rounded-2xl flex flex-col items-center justify-center gap-2 border-0 shadow-md font-semibold transition-all hover:scale-[1.02]"
              >
                <Mail className="h-6 w-6" />
                <span>Send Emails</span>
              </Button>
              <Button
                onClick={() => handleAction('generate-report', 'CEO Report')}
                className="h-24 bg-gradient-to-tr from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white rounded-2xl flex flex-col items-center justify-center gap-2 border-0 shadow-md font-semibold transition-all hover:scale-[1.02]"
              >
                <FileText className="h-6 w-6" />
                <span>CEO Report</span>
              </Button>
            </div>
          </div>

          {/* Worker Lanes Status */}
          <div className="p-7 bg-[#eeece3]/30 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl space-y-5">
            <div>
              <h3 className="text-lg font-bold text-foreground">Scheduler Autonomous Lanes</h3>
              <p className="text-[13px] text-muted-foreground mt-1">Status of OROVA's 5 parallel automated workflow loops.</p>
            </div>
            <div className="space-y-3.5">
              {Object.entries(lanes).map(([key, lane]: [string, OrovaLane]) => (
                <div key={key} className="flex items-center justify-between p-3.5 bg-background border border-black/5 dark:border-white/5 rounded-xl">
                  <div className="flex items-center gap-3">
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                    </span>
                    <div>
                      <h4 className="text-[13.5px] font-bold text-foreground">{lane.name}</h4>
                      <p className="text-[11.5px] text-muted-foreground font-mono mt-0.5">Interval: {lane.interval}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <Badge variant="secondary" className="px-2.5 py-0.5 text-[11px] font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                      {lane.status}
                    </Badge>
                    <p className="text-[10px] text-muted-foreground mt-1">Last: {lane.last_run}</p>
                  </div>
                </div>
              ))}
              {Object.keys(lanes).length === 0 && (
                <p className="text-[13px] text-muted-foreground italic text-center py-6">Connecting to scheduler thread...</p>
              )}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}