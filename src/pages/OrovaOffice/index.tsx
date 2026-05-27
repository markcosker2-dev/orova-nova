import { useEffect, useState, useRef } from 'react';
import { useOrovaStore } from '@/stores/orova';
import type { OrovaAgent } from '@/stores/orova';
import { useChatStore } from '@/stores/chat';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { MessageSquare, Cpu, Terminal, Users } from 'lucide-react';
import { toast } from 'sonner';

export default function OrovaOffice() {
  const { agents, fetchAgents } = useOrovaStore();
  const { switchSession } = useChatStore();
  const navigate = useNavigate();
  const [activeConsole, setActiveConsole] = useState<string | null>(null);

  const fetchAgentsRef = useRef(fetchAgents);
  fetchAgentsRef.current = fetchAgents;

  useEffect(() => {
    fetchAgents();
    const interval = setInterval(() => {
      fetchAgentsRef.current();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleLaunchChat = (agentId: string) => {
    // Session keys are in format agent:agentId:session-xxx, 
    // or simply switchSession to the agent's main session key
    const sessionKey = `agent:${agentId}:main`;
    switchSession(sessionKey);
    navigate('/chat');
    toast.success(`Connected to ${agentId.toUpperCase()} session`);
  };

  // Group agents by department
  const depts: string[] = Array.from(new Set(agents.map(a => a.dept).filter(Boolean)));

  const getLogLinesForAgent = (id: string) => {
    switch (id) {
      case 'nova':
        return [
          '[SWARM] CEO orchestrator active.',
          '[WORKER] Fast Lane scheduler synchronized.',
          '[Nova] All 10 lanes confirmed healthy.'
        ];
      case 'atlas':
        return [
          '[COMPILE] Composio gateway active.',
          '[SYSTEM] Crawler framework mounted.',
          '[Atlas] Awaiting system integration.'
        ];
      case 'pixel':
        return [
          '[ASSET] Dall-E 3 image pipeline ready.',
          '[Pixel] Instagram grid visual assets drafted.',
          '[Pixel] Brand guides applied successfully.'
        ];
      case 'quill':
        return [
          '[COPY] PAS outreach sequence complete.',
          '[Quill] 5-day email escalation drafted.',
          '[Quill] Marketing content calendar ready.'
        ];
      case 'hawk':
        return [
          '[HUNT] Slow Lane crawler active.',
          '[Hawk] Scraped 5 leads from Yelp.',
          '[Hawk] Validating high-ticket companies.'
        ];
      case 'closer':
        return [
          '[SALES] Outreach inbox active.',
          '[Closer] Escalating cold leads to call lane.',
          '[Closer] Retell call triggered successfully.'
        ];
      case 'sentinel':
        return [
          '[HEARTBEAT] Memory limits check: PASS.',
          '[Sentinel] Swarm API wallet drain guard active.',
          '[Sentinel] Uptime continuous monitoring.'
        ];
      case 'echo':
        return [
          '[TELEGRAM] Liaison queue active.',
          '[Echo] Forwarded approval status to admin.',
          '[Echo] Telegram Webhook registered.'
        ];
      case 'oracle':
        return [
          '[ANALYTICS] Pipeline report exported.',
          '[Oracle] Mapped sales funnel conversions.',
          '[Oracle] Performance report synchronized.'
        ];
      case 'viper':
        return [
          '[STEALTH] Scrapling anti-bot bypass active.',
          '[Viper] Bypassed Cloudflare shield.',
          '[Viper] Deep contact extraction completed.'
        ];
      default:
        return ['[AGENT] Online and idle.', '[AGENT] Swarm active.'];
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2.5rem)] overflow-hidden bg-background">
      <div className="w-full max-w-6xl mx-auto p-10 pt-16 flex-1 overflow-y-auto space-y-10">
        
        {/* Header */}
        <div>
          <h1 className="text-5xl font-serif tracking-tight text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
            OROVA swarm office
          </h1>
          <p className="text-[16px] text-muted-foreground mt-2 font-medium">
            Monitor the autonomous AI operations, departments, and active consoles.
          </p>
        </div>

        {/* Office Grid */}
        <div className="space-y-10">
          {depts.map((dept: string) => (
            <div key={dept} className="space-y-4">
              <div className="flex items-center gap-2 border-b border-black/5 dark:border-white/5 pb-2">
                <Users className="h-5 w-5 text-muted-foreground" />
                <h3 className="text-md font-bold tracking-wide uppercase text-muted-foreground">{dept}</h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {agents.filter(a => a.dept === dept).map((agent: OrovaAgent) => (
                  <div 
                    key={agent.id}
                    className={`p-6 bg-[#eeece3]/20 dark:bg-card border border-black/5 dark:border-white/5 rounded-3xl flex flex-col justify-between space-y-6 shadow-sm hover:shadow-md transition-all ${
                      activeConsole === agent.id ? 'ring-2 ring-blue-500/30' : ''
                    }`}
                  >
                    
                    {/* Upper row: Avatar and meta */}
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-4">
                        <div
                          className="h-12 w-12 rounded-2xl flex items-center justify-center text-white font-bold text-lg shadow-inner shrink-0"
                          style={{ backgroundColor: agent.color }}
                        >
                          {agent.initial}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-lg font-bold text-foreground">{agent.name}</h4>
                            <Badge className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-bold">
                              {agent.status}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <p className="text-[12px] text-muted-foreground font-semibold">{agent.role}</p>
                            <Badge variant="outline" className="px-2 py-0 text-[10px] rounded-full bg-black/[0.03] dark:bg-white/[0.05] text-foreground/60 border-0 font-medium">
                              {agent.model}
                            </Badge>
                          </div>
                        </div>
                      </div>

                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleLaunchChat(agent.id)}
                        className="h-8 border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl text-[12px] font-semibold gap-1.5 shadow-none"
                      >
                        <MessageSquare className="h-3.5 w-3.5" />
                        Chat
                      </Button>
                    </div>

                    {/* Middle: Current task */}
                    <div className="p-4 bg-background border border-black/5 dark:border-white/5 rounded-2xl space-y-1">
                      <div className="flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground uppercase tracking-wide">
                        <Cpu className="h-3.5 w-3.5" />
                        Active Assignment
                      </div>
                      <p className="text-[13px] text-foreground font-medium leading-relaxed mt-1">
                        {agent.task}
                      </p>
                    </div>

                    {/* Terminal logs toggle section */}
                    <div className="space-y-2">
                      <button 
                        onClick={() => setActiveConsole(activeConsole === agent.id ? null : agent.id)}
                        className="flex items-center gap-1.5 text-[11.5px] font-bold text-blue-500 hover:text-blue-600 transition-colors uppercase tracking-wider outline-none"
                      >
                        <Terminal className="h-3.5 w-3.5" />
                        {activeConsole === agent.id ? 'Close Terminal Console' : 'View Terminal Console'}
                      </button>
                      
                      {activeConsole === agent.id && (
                        <div className="p-4 bg-black dark:bg-[#090909] text-emerald-400 font-mono text-[11.5px] rounded-2xl border border-black/20 space-y-1 shadow-inner h-28 overflow-y-auto">
                          {getLogLinesForAgent(agent.id).map((line, i) => (
                            <div key={i} className="flex items-start gap-1.5">
                              <span className="text-emerald-600 shrink-0">&gt;</span>
                              <span className="leading-normal">{line}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Footer: Skills list */}
                    <div className="flex items-center gap-1.5 flex-wrap pt-2">
                      {agent.skills?.slice(0, 3).map((skill: string) => (
                        <Badge key={skill} variant="secondary" className="px-2 py-0.5 rounded-full text-[10px] bg-black/[0.04] dark:bg-white/[0.06] text-foreground/70 border-0 font-medium">
                          {skill}
                        </Badge>
                      ))}
                      {(agent.skills?.length ?? 0) > 3 && (
                        <span className="text-[10px] text-muted-foreground font-semibold pl-1">
                          +{agent.skills.length - 3} skills
                        </span>
                      )}
                    </div>

                  </div>
                ))}
              </div>
            </div>
          ))}
          {agents.length === 0 && (
            <p className="text-[13px] text-muted-foreground italic text-center py-10">Deploying swarm agent desks in digital workspace...</p>
          )}
        </div>

      </div>
    </div>
  );
}
