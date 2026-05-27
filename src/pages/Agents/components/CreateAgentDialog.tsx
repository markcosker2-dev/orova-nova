import { useState, useMemo } from 'react';
import { RefreshCw, Search, Plus, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { inputClasses, labelClasses } from './styles';

import { AGENT_TEMPLATES, TEMPLATE_CATEGORIES } from '@/data/agent-templates.generated';
import type { AgentTemplate } from '@/types/agent-template';

export function CreateAgentDialog({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string, options: { inheritWorkspace: boolean }, soulContent?: string) => Promise<void>;
}) {
  const { t } = useTranslation('agents');
  
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedTemplate, setSelectedTemplate] = useState<AgentTemplate | 'custom' | null>(null);
  
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  
  const [name, setName] = useState('');
  const [inheritWorkspace, setInheritWorkspace] = useState(false);
  const [saving, setSaving] = useState(false);

  // Filter templates
  const filteredTemplates = useMemo(() => {
    return AGENT_TEMPLATES.filter((template) => {
      const matchesSearch = 
        template.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
        template.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || template.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  const handleNext = () => {
    if (!selectedTemplate) return;
    if (selectedTemplate !== 'custom') {
      setName(selectedTemplate.name);
    } else {
      setName('');
    }
    setStep(2);
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const soulContent = selectedTemplate !== 'custom' && selectedTemplate ? selectedTemplate.soulContent : undefined;
      await onCreate(name.trim(), { inheritWorkspace }, soulContent);
    } catch (error) {
      toast.error(t('toast.agentCreateFailed', { error: String(error) }));
      setSaving(false);
      return;
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <Card className="w-full max-w-4xl max-h-[85vh] rounded-3xl border-0 shadow-2xl bg-[#f3f1e9] dark:bg-card overflow-hidden flex flex-col">
        {step === 1 && (
          <>
            <CardHeader className="pb-2 shrink-0">
              <CardTitle className="text-2xl font-serif font-normal tracking-tight">
                选择智能体模板
              </CardTitle>
              <CardDescription className="text-[15px] mt-1 text-foreground/70">
                从模板快速创建，或从头自定义一个智能体
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden flex flex-col pt-2 p-6 gap-4">
              {/* Search & Categories */}
              <div className="flex flex-col gap-3 shrink-0">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-foreground/50" />
                  <Input 
                    placeholder="搜索模板..." 
                    className={`${inputClasses} pl-9`}
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                  />
                </div>
                <div className="flex gap-2 overflow-x-auto pb-2 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                  <Button
                    variant="outline"
                    onClick={() => setSelectedCategory('all')}
                    className={`h-8 rounded-full whitespace-nowrap px-4 border-black/10 dark:border-white/10 ${selectedCategory === 'all' ? 'bg-black/10 dark:bg-white/10' : 'bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none'}`}
                  >
                    所有分类
                  </Button>
                  {TEMPLATE_CATEGORIES.map(cat => (
                    <Button
                      key={cat.id}
                      variant="outline"
                      onClick={() => setSelectedCategory(cat.id)}
                      className={`h-8 rounded-full whitespace-nowrap px-4 border-black/10 dark:border-white/10 ${selectedCategory === cat.id ? 'bg-black/10 dark:bg-white/10' : 'bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none'}`}
                    >
                      {cat.label} <span className="ml-1 opacity-60 text-xs">{cat.count}</span>
                    </Button>
                  ))}
                </div>
              </div>

              {/* Grid */}
              <div className="flex-1 overflow-y-auto pr-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                <div 
                  className={`cursor-pointer rounded-2xl border-2 p-4 flex items-center gap-3 transition-colors ${selectedTemplate === 'custom' ? 'border-primary bg-primary/5' : 'border-transparent bg-white/50 hover:bg-white/80 dark:bg-black/20 dark:hover:bg-black/40'}`}
                  onClick={() => setSelectedTemplate('custom')}
                >
                  <div className="h-10 w-10 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-center shrink-0">
                    <Plus className="h-5 w-5 opacity-70" />
                  </div>
                  <div>
                    <h3 className="font-bold text-[14px]">自定义智能体</h3>
                    <p className="text-[12px] opacity-70 line-clamp-1">从空白开始创建全新智能体</p>
                  </div>
                </div>

                {filteredTemplates.map(tpl => (
                  <div 
                    key={tpl.id}
                    className={`cursor-pointer rounded-2xl border-2 p-4 flex flex-col gap-2 transition-colors ${selectedTemplate && selectedTemplate !== 'custom' && selectedTemplate.id === tpl.id ? 'border-primary bg-primary/5' : 'border-transparent bg-white/50 hover:bg-white/80 dark:bg-black/20 dark:hover:bg-black/40'}`}
                    onClick={() => setSelectedTemplate(tpl)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="h-10 w-10 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-center shrink-0 text-xl">
                        {tpl.emoji || '🤖'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-[14px] truncate">{tpl.name}</h3>
                        <Badge variant="secondary" className="mt-1 text-[10px] px-1.5 py-0 rounded-md font-normal bg-black/5 dark:bg-white/10 hover:bg-black/5">
                          {tpl.category}
                        </Badge>
                      </div>
                    </div>
                    <p className="text-[12px] opacity-70 line-clamp-2 mt-1 leading-relaxed">
                      {tpl.description}
                    </p>
                  </div>
                ))}
              </div>

              {/* Footer */}
              <div className="flex justify-between items-center shrink-0 pt-4 border-t border-black/5 dark:border-white/5">
                <div className="text-[13px] text-foreground/60">
                  {selectedTemplate === 'custom' ? '已选择：自定义智能体' : selectedTemplate ? `已选择：${selectedTemplate.name}` : '请选择一个模板'}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={onClose}
                    className="h-9 text-[13px] font-medium rounded-full px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none text-foreground/80 hover:text-foreground"
                  >
                    {t('common:actions.cancel')}
                  </Button>
                  <Button
                    onClick={handleNext}
                    disabled={!selectedTemplate}
                    className="h-9 text-[13px] font-medium rounded-full px-6 shadow-none"
                  >
                    下一步
                  </Button>
                </div>
              </div>
            </CardContent>
          </>
        )}

        {step === 2 && (
          <>
            <CardHeader className="pb-2 shrink-0">
              <CardTitle className="text-2xl font-serif font-normal tracking-tight">
                {t('createDialog.title')}
              </CardTitle>
              <CardDescription className="text-[15px] mt-1 text-foreground/70">
                {t('createDialog.description')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 pt-4 p-6 overflow-y-auto">
              
              {selectedTemplate && selectedTemplate !== 'custom' && (
                <div className="p-4 rounded-2xl bg-white/50 dark:bg-black/20 flex gap-4 items-start">
                  <div className="h-12 w-12 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-center shrink-0 text-2xl">
                    {selectedTemplate.emoji || '🤖'}
                  </div>
                  <div>
                    <h3 className="font-bold text-[15px]">{selectedTemplate.name}</h3>
                    <p className="text-[13px] opacity-70 mt-1">{selectedTemplate.description}</p>
                    {selectedTemplate.vibe && (
                      <p className="text-[12px] opacity-60 mt-2 italic">"{selectedTemplate.vibe}"</p>
                    )}
                  </div>
                </div>
              )}

              <div className="space-y-2.5">
                <Label htmlFor="agent-name" className={labelClasses}>{t('createDialog.nameLabel')}</Label>
                <Input
                  id="agent-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={t('createDialog.namePlaceholder')}
                  className={inputClasses}
                  autoFocus
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="inherit-workspace" className={labelClasses}>{t('createDialog.inheritWorkspaceLabel')}</Label>
                  <p className="text-[13px] text-foreground/60">{t('createDialog.inheritWorkspaceDescription')}</p>
                </div>
                <Switch
                  id="inherit-workspace"
                  checked={inheritWorkspace}
                  onCheckedChange={setInheritWorkspace}
                />
              </div>
              <div className="flex justify-between gap-2 pt-4">
                <Button
                  variant="ghost"
                  onClick={() => setStep(1)}
                  className="h-9 text-[13px] font-medium rounded-full px-4 hover:bg-black/5 dark:hover:bg-white/5"
                >
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  上一步
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={onClose}
                    className="h-9 text-[13px] font-medium rounded-full px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5 shadow-none text-foreground/80 hover:text-foreground"
                  >
                    {t('common:actions.cancel')}
                  </Button>
                  <Button
                    onClick={() => void handleSubmit()}
                    disabled={saving || !name.trim()}
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
              </div>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
