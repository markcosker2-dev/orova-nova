import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useTeamsStore } from '@/stores/teams';
import { useAgentsStore } from '@/stores/agents';
import { inputClasses, labelClasses, selectClasses } from './styles';

export function CreateTeamDialog() {
  const { t } = useTranslation('agents');
  const navigate = useNavigate();
  const { createTeam } = useTeamsStore();
  const { agents } = useAgentsStore();
  
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [orchestratorId, setOrchestratorId] = useState('');
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [delegationMode, setDelegationMode] = useState<'auto' | 'manual'>('auto');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || !orchestratorId) return;
    setSaving(true);
    try {
      await createTeam({
        name: name.trim(),
        description: description.trim(),
        orchestratorId,
        memberIds,
        config: {
          delegationMode
        }
      });
      navigate('/agents');
    } catch (error) {
      toast.error(t('teams.createFailed', { error: String(error) }));
      setSaving(false);
    }
  };

  const handleMemberToggle = (id: string) => {
    setMemberIds(prev => 
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <Card className="w-full max-w-lg rounded-3xl border-0 shadow-2xl bg-[#f3f1e9] dark:bg-card overflow-hidden max-h-[90vh] flex flex-col">
        <CardHeader className="pb-2 shrink-0">
          <CardTitle className="text-2xl font-serif font-normal tracking-tight">
            {t('teams.createTitle')}
          </CardTitle>
          <CardDescription className="text-[15px] mt-1 text-foreground/70">
            {t('teams.createDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6 pt-4 p-6 overflow-y-auto flex-1">
          <div className="space-y-2.5">
            <Label htmlFor="team-name" className={labelClasses}>{t('teams.nameLabel')}</Label>
            <Input
              id="team-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('teams.namePlaceholder')}
              className={inputClasses}
            />
          </div>

          <div className="space-y-2.5">
            <Label htmlFor="team-description" className={labelClasses}>{t('teams.descriptionLabel')}</Label>
            <Input
              id="team-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t('teams.descriptionPlaceholder')}
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
              <option value="">{t('teams.selectOrchestrator')}</option>
              {agents.map(agent => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2.5">
            <Label className={labelClasses}>{t('teams.membersLabel')}</Label>
            <div className="border border-black/10 dark:border-white/10 rounded-xl p-3 bg-[#eeece3] dark:bg-muted max-h-40 overflow-y-auto space-y-2">
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
              {agents.length <= 1 && <p className="text-[13px] text-muted-foreground">{t('teams.noOtherAgents')}</p>}
            </div>
          </div>

          <div className="flex items-center justify-between">
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

          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={() => navigate('/agents')}
              className="h-9 text-[13px] font-medium rounded-full px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none text-foreground/80 hover:text-foreground"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              onClick={() => void handleSubmit()}
              disabled={saving || !name.trim() || !orchestratorId}
              className="h-9 text-[13px] font-medium rounded-full px-4 shadow-none"
            >
              {saving ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  {t('common:actions.saving')}
                </>
              ) : (
                t('common:actions.create')
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
