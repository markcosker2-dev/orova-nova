import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTeamsStore } from '@/stores/teams';
import { useAgentsStore } from '@/stores/agents';
import { toast } from 'sonner';
import { inputClasses, labelClasses, selectClasses } from './components/styles';

export function TeamDetailPage() {
  const { teamId } = useParams<{ teamId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('agents');
  const { teams, updateTeam } = useTeamsStore();
  const { agents } = useAgentsStore();
  
  const team = teams.find(t => t.id === teamId);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [orchestratorId, setOrchestratorId] = useState('');
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [delegationMode, setDelegationMode] = useState<'auto' | 'manual'>('auto');
  const [soulTemplate, setSoulTemplate] = useState('');
  const [saving, setSaving] = useState(false);

useEffect(() => {
     if (team) {
       // eslint-disable-next-line react-hooks/set-state-in-effect
       setName(team.name);
       setDescription(team.description || '');
       setOrchestratorId(team.orchestratorId);
       setMemberIds(team.memberIds);
       setDelegationMode(team.config.delegationMode);
       setSoulTemplate(team.config.soulTemplate || '');
     }
   }, [team]);

  if (!team) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-10">
        <p className="text-muted-foreground">{t('teams.notFound')}</p>
        <Button onClick={() => navigate('/agents')} className="mt-4 rounded-full">{t('common:actions.back')}</Button>
      </div>
    );
  }

  const handleMemberToggle = (id: string) => {
    setMemberIds(prev => 
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  const handleSave = async () => {
    if (!name.trim() || !orchestratorId) return;
    setSaving(true);
    try {
      await updateTeam(team.id, {
        name: name.trim(),
        description: description.trim(),
        orchestratorId,
        config: {
          ...team.config,
          delegationMode,
          soulTemplate: soulTemplate.trim() || undefined,
        }
      });
      // also need to handle members update if they changed, though updateTeam can handle it if added to params or via addMember/removeMember
      toast.success(t('teams.updateSuccess'));
    } catch (error) {
      toast.error(t('teams.updateFailed', { error: String(error) }));
    }
    setSaving(false);
  };

  return (
    <div className="flex flex-col -m-6 dark:bg-background h-[calc(100vh-2.5rem)] overflow-hidden">
      <div className="w-full max-w-5xl mx-auto flex flex-col h-full p-10 pt-16">
        <div className="flex flex-col md:flex-row md:items-start justify-between mb-8 shrink-0 gap-4">
          <div>
            <h1 className="text-4xl md:text-5xl font-serif text-foreground mb-3 font-normal tracking-tight">
              {team.name}
            </h1>
            <p className="text-[17px] text-foreground/70 font-medium">{t('teams.settings')}</p>
          </div>
          <div className="flex items-center gap-3 md:mt-2">
            <Button
              variant="outline"
              onClick={() => navigate('/agents')}
              className="h-9 text-[13px] font-medium rounded-full px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none text-foreground/80 hover:text-foreground transition-colors"
            >
              {t('common:actions.back')}
            </Button>
            <Button
              onClick={() => void handleSave()}
              disabled={saving || !name.trim() || !orchestratorId}
              className="h-9 text-[13px] font-medium rounded-full px-4 shadow-none"
            >
              {saving ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : null}
              {t('common:actions.save')}
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 pb-10 space-y-6">
          <div className="space-y-2.5">
            <Label htmlFor="team-name" className={labelClasses}>{t('teams.nameLabel')}</Label>
            <Input
              id="team-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={inputClasses}
            />
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="team-description" className={labelClasses}>{t('teams.descriptionLabel')}</Label>
            <Input
              id="team-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className={inputClasses}
            />
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="orchestrator" className={labelClasses}>{t('teams.orchestratorLabel')}</Label>
            <select
              id="orchestrator"
              value={orchestratorId}
              onChange={(e) => setOrchestratorId(e.target.value)}
              className={selectClasses}
            >
              {agents.map(agent => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2.5">
            <Label className={labelClasses}>{t('teams.membersLabel')}</Label>
            <div className="border border-black/10 dark:border-white/10 rounded-xl p-3 bg-[#eeece3] dark:bg-muted max-h-60 overflow-y-auto space-y-2">
              {agents.filter(a => a.id !== orchestratorId).map(agent => (
                <label key={agent.id} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={memberIds.includes(agent.id)}
                    onChange={() => handleMemberToggle(agent.id)}
                    className="rounded text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-[13px]">{agent.name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between bg-[#eeece3] dark:bg-muted p-4 rounded-xl border border-black/10 dark:border-white/10">
            <div className="space-y-0.5">
              <Label htmlFor="delegation-mode" className={labelClasses}>{t('teams.autoDelegationLabel')}</Label>
              <p className="text-[13px] text-foreground/60">{t('teams.autoDelegationDescription')}</p>
            </div>
            <Switch
              id="delegation-mode"
              checked={delegationMode === 'auto'}
              onCheckedChange={(checked) => setDelegationMode(checked ? 'auto' : 'manual')}
            />
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="soul-template" className={labelClasses}>{t('teams.soulTemplateLabel')}</Label>
            <textarea
              id="soul-template"
              value={soulTemplate}
              onChange={(e) => setSoulTemplate(e.target.value)}
              placeholder={t('teams.soulTemplatePlaceholder')}
              className="w-full min-h-[150px] rounded-xl font-mono text-[13px] bg-[#eeece3] dark:bg-muted border border-black/10 dark:border-white/10 focus-visible:ring-2 focus-visible:ring-blue-500/50 focus-visible:border-blue-500 shadow-sm p-3 text-foreground"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
