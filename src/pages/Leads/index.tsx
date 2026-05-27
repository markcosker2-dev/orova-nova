import { useEffect, useState, useCallback } from 'react';
import { useOrovaStore } from '@/stores/orova';
import {
  Search, ShieldCheck, Check, Trash2, ExternalLink, RefreshCw, Filter
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

export default function Leads() {
  const { leads, fetchLeads, approveLead, clearLeads, loading } = useOrovaStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedVertical, setSelectedVertical] = useState('All');
  const [refreshing, setRefreshing] = useState(false);

const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchLeads();
      toast.success('Leads list refreshed');
    } catch {
      toast.error('Failed to refresh leads');
    } finally {
      setRefreshing(false);
    }
  }, [fetchLeads]);

  const handleApprove = useCallback(async (id: number, business: string) => {
    try {
      await approveLead(id);
      toast.success(`Lead "${business}" approved and deep-scanned!`);
    } catch (_e: unknown) {
      toast.error(`Approval failed: ${String(_e)}`);
    }
  }, [approveLead]);

  const handleClear = useCallback(async () => {
    if (!window.confirm('Are you sure you want to clear ALL leads? This cannot be undone.')) return;
    try {
      await clearLeads();
      toast.success('All leads pipeline cleared');
    } catch (_e: unknown) {
      toast.error(`Clear failed: ${String(_e)}`);
    }
  }, [clearLeads]);

  useEffect(() => {
    void handleRefresh();
  }, [handleRefresh]);

  // Get list of unique verticals
  const verticals: string[] = ['All', ...Array.from(new Set(leads.map((l: import('@/stores/orova').OrovaLead) => l.vertical).filter(Boolean)))];

  // Filtering logic
  const filteredLeads = leads.filter((l: import('@/stores/orova').OrovaLead) => {
    const matchesSearch =
      l.business?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      l.owner?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      l.email?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesVertical = selectedVertical === 'All' || l.vertical === selectedVertical;

    return matchesSearch && matchesVertical;
  });

  const getScoreBadgeColor = (score: number) => {
    if (score >= 8) return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
    if (score >= 5) return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
    return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2.5rem)] overflow-hidden bg-background">
      <div className="w-full max-w-6xl mx-auto p-10 pt-16 flex-1 overflow-hidden flex flex-col space-y-6">
        
        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-5xl font-serif tracking-tight text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
              Lead Pipeline
            </h1>
            <p className="text-[16px] text-muted-foreground mt-2 font-medium">
              Validate, qualify, and approve potential CRM business leads.
            </p>
          </div>
          
          <div className="flex items-center gap-3">
            {leads.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClear}
                disabled={loading}
                className="h-9 px-4 text-destructive/80 hover:text-destructive hover:bg-destructive/5 dark:hover:bg-destructive/10 border-destructive/20 hover:border-destructive rounded-xl transition-all shadow-none"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Clear Leads
              </Button>
            )}
            <Button
              variant="outline"
              size="icon"
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="h-9 w-9 border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 shadow-none rounded-xl"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Toolbar & Filters */}
        <div className="flex items-center gap-4 shrink-0 bg-[#eeece3]/20 dark:bg-card border border-black/5 dark:border-white/5 p-3 rounded-2xl">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by company, owner, or email..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-9 h-9 border-black/10 dark:border-white/10 rounded-xl bg-background text-foreground"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              value={selectedVertical}
              onChange={e => setSelectedVertical(e.target.value)}
              className="h-9 px-3 bg-background border border-black/10 dark:border-white/10 text-foreground rounded-xl text-[13px] outline-none"
            >
              {verticals.map((v: string) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Leads Table Card */}
        <div className="flex-1 min-h-0 bg-[#eeece3]/10 dark:bg-card border border-black/5 dark:border-white/5 rounded-2xl overflow-hidden flex flex-col shadow-sm">
          <div className="flex-1 overflow-y-auto min-h-0">
            {filteredLeads.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground p-10">
                <ShieldCheck className="h-12 w-12 opacity-30 mb-4" />
                <p className="font-semibold text-lg">No leads to display</p>
                <p className="text-[13px] mt-1 text-center max-w-xs">Trigger 'Hunt Leads' on the Dashboard or clear search filters to display records.</p>
              </div>
            ) : (
              <table className="w-full border-collapse text-left">
                <thead className="sticky top-0 bg-[#eeece3] dark:bg-muted text-[12px] font-bold text-muted-foreground uppercase tracking-wider border-b border-black/5 dark:border-white/5 z-10">
                  <tr>
                    <th className="py-3.5 px-5">Company / Owner</th>
                    <th className="py-3.5 px-5">Vertical</th>
                    <th className="py-3.5 px-5">Contacts</th>
                    <th className="py-3.5 px-5 text-center">Fit Score</th>
                    <th className="py-3.5 px-5">Status</th>
                    <th className="py-3.5 px-5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 text-[13.5px]">
                  {filteredLeads.map((lead: import('@/stores/orova').OrovaLead) => (
                    <tr key={lead.id} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.01] transition-colors">
                      <td className="py-4 px-5">
                        <div className="font-bold text-foreground">{lead.business}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">{lead.owner || 'Unknown Owner'}</div>
                      </td>
                      <td className="py-4 px-5">
                        <Badge variant="secondary" className="px-2 py-0.5 rounded-full text-[10.5px] border-0 bg-black/5 dark:bg-white/10 text-foreground font-semibold">
                          {lead.vertical || 'Web Search'}
                        </Badge>
                      </td>
                      <td className="py-4 px-5 space-y-0.5">
                        <div className="font-mono text-[11.5px] text-foreground">{lead.email || '-'}</div>
                        <div className="text-[11px] text-muted-foreground">{lead.phone || '-'}</div>
                      </td>
                      <td className="py-4 px-5 text-center">
                        <Badge variant="outline" className={`px-2.5 py-0.5 text-[11.5px] font-bold rounded-full border ${getScoreBadgeColor(lead.score)}`}>
                          {lead.score ? `${lead.score}/10` : 'Pending'}
                        </Badge>
                      </td>
                      <td className="py-4 px-5">
                        <Badge variant="outline" className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                          lead.status === 'Approved'
                            ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                            : lead.status === 'Ready for Call'
                              ? 'bg-orange-500/10 text-orange-600 border-orange-500/20'
                              : 'bg-blue-500/10 text-blue-600 border-blue-500/20'
                        }`}>
                          {lead.status || 'New'}
                        </Badge>
                      </td>
                      <td className="py-4 px-5 text-right space-x-2">
                        {lead.website && (
                          <a
                            href={lead.website.startsWith('http') ? lead.website : `https://${lead.website}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-[#eeece3] dark:bg-muted text-muted-foreground hover:text-foreground border border-black/5 hover:border-black/10 transition-colors"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        )}
                        {lead.status !== 'Approved' && (
                          <Button
                            size="sm"
                            onClick={() => handleApprove(lead.id, lead.business)}
                            className="h-8 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-semibold shadow-sm border-0 transition-all hover:scale-[1.02]"
                          >
                            <Check className="h-3.5 w-3.5 mr-1" />
                            Approve
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}