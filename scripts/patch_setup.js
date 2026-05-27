const fs = require('fs');
const path = 'src/pages/Setup/index.tsx';
let content = fs.readFileSync(path, 'utf8');

// Replace the InstallStatus and add StepInstallState
content = content.replace(
  /type InstallStatus = 'pending' \| 'installing' \| 'completed' \| 'failed';[\s\S]*?interface SkillInstallState \{[\s\S]*?\}/m,
  `type InstallStatus = 'pending' | 'installing' | 'completed' | 'failed' | 'skipped';\n\ninterface StepInstallState {\n  id: string;\n  kind: 'runtime' | 'bridge';\n  label: string;\n  status: InstallStatus;\n}`
);

// Modify InstallingContentProps
content = content.replace(
  /interface InstallingContentProps \{[\s\S]*?installChoice: SetupInstallChoice;\n  skills: DefaultSkill\[\];\n  onComplete: \(installedSkills: string\[\]\) => void;\n  onSkip: \(\) => void;\n\}/m,
  `interface InstallingContentProps {\n  installChoice: SetupInstallChoice;\n  onComplete: (installedSkills: string[]) => void;\n  onSkip: () => void;\n}`
);

// Modify InstallingContent function signature
content = content.replace(
  /function InstallingContent\(\{ installChoice, skills, onComplete, onSkip \}: InstallingContentProps\) \{/m,
  `function InstallingContent({ installChoice, onComplete, onSkip }: InstallingContentProps) {`
);

// Replace hook state
content = content.replace(
  /const \[skillStates, setSkillStates\] = useState<SkillInstallState\[\]>\([\s\S]*?const installStarted = useRef\(false\);/m,
  `const [stepStates, setStepStates] = useState<StepInstallState[]>([]);\n  const [overallProgress, setOverallProgress] = useState(0);\n  const [errorMessage, setErrorMessage] = useState<string | null>(null);\n  const installStarted = useRef(false);`
);

// Modify useEffect content
content = content.replace(
  /useEffect\(\(\) => \{[\s\S]*?runRealInstall\(\);\n  \}, \[installChoice, onComplete, skills\]\);/m,
  `useEffect(() => {
    if (installStarted.current) return;
    installStarted.current = true;

    const runRealInstall = async () => {
      try {
        setOverallProgress(10);
        
        // Call the backend to install and get steps
        const result = await installRuntime(installChoice);

        if (result.success) {
          const initialSteps: StepInstallState[] = result.steps.map(s => ({
            id: s.id,
            kind: s.kind,
            label: s.label,
            status: s.status === 'skipped' ? 'skipped' : 'pending'
          }));
          setStepStates(initialSteps);
          
          let currentSteps = [...initialSteps];
          let pendingCount = currentSteps.filter(s => s.status === 'pending').length;
          let completedCount = 0;

          // Simulate progress for pending steps
          for (let i = 0; i < currentSteps.length; i++) {
            if (currentSteps[i].status === 'pending') {
              currentSteps = currentSteps.map((s, idx) => i === idx ? { ...s, status: 'installing' } : s);
              setStepStates(currentSteps);
              
              // short delay
              await new Promise((resolve) => setTimeout(resolve, 800));
              
              currentSteps = currentSteps.map((s, idx) => i === idx ? { ...s, status: 'completed' } : s);
              setStepStates(currentSteps);
              completedCount++;
              setOverallProgress(10 + Math.floor((completedCount / pendingCount) * 90));
            }
          }

          setOverallProgress(100);
          await new Promise((resolve) => setTimeout(resolve, 800));
          onComplete([]);
        } else {
          setStepStates(prev => prev.map(s => s.status === 'pending' ? { ...s, status: 'failed' } : s));
          setErrorMessage((result as any).error || 'Unknown error during installation');
          toast.error('Environment setup failed');
        }
      } catch (err) {
        setStepStates(prev => prev.map(s => s.status === 'pending' ? { ...s, status: 'failed' } : s));
        setErrorMessage(String(err));
        toast.error('Installation error');
      }
    };

    runRealInstall();
  }, [installChoice, onComplete]);`
);

// getStatusIcon
content = content.replace(
  /const getStatusIcon = \(status: InstallStatus\) => \{[\s\S]*?\}\n  \};/m,
  `const getStatusIcon = (status: InstallStatus) => {
    switch (status) {
      case 'pending':
        return <div className="h-5 w-5 rounded-full border-2 border-slate-500" />;
      case 'installing':
        return <Loader2 className="h-5 w-5 text-primary animate-spin" />;
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-green-400" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-400" />;
      case 'skipped':
        return <div className="h-5 w-5 rounded-full border-2 border-slate-700 flex items-center justify-center"><div className="h-1 w-2 bg-slate-600 rounded" /></div>;
    }
  };`
);

// getStatusText
content = content.replace(
  /const getStatusText = \(skill: SkillInstallState\) => \{[\s\S]*?\}\n  \};/m,
  `const getStatusText = (step: StepInstallState) => {
    switch (step.status) {
      case 'pending':
        return <span className="text-muted-foreground">{t('installing.status.pending')}</span>;
      case 'installing':
        return <span className="text-primary">{t('installing.status.installing')}</span>;
      case 'completed':
        return <span className="text-green-400">{t('installing.status.installed')}</span>;
      case 'failed':
        return <span className="text-red-400">{t('installing.status.failed')}</span>;
      case 'skipped':
        return <span className="text-slate-500">{t('installing.status.skipped', 'Skipped')}</span>;
    }
  };`
);

// Skill list map
content = content.replace(
  /\{skillStates\.map\(\(skill\) => \([\s\S]*?\{getStatusText\(skill\)\}\n          <\/motion\.div>\n        \)\)\}/m,
  `{stepStates.map((step) => (
          <motion.div
            key={step.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              'flex items-center justify-between p-3 rounded-lg',
              step.status === 'installing' ? 'bg-muted' : 'bg-muted/50'
            )}
          >
            <div className="flex items-center gap-3">
              {getStatusIcon(step.status)}
              <div>
                <p className="font-medium">{step.label}</p>
                <p className="text-xs text-muted-foreground capitalize">{step.kind}</p>
              </div>
            </div>
            {getStatusText(step)}
          </motion.div>
        ))}`
);

// Fix call in Setup step
content = content.replace(
  /skills=\{getDefaultSkills\(t\)\}\n                  onComplete=\{handleInstallationComplete\}/m,
  `onComplete={handleInstallationComplete}`
);

// Ensure there's only one argument removed for the component if it existed on the same line
content = content.replace(
  /<InstallingContent\s+installChoice=\{installChoice\}\s+onComplete=\{handleInstallationComplete\}\s+onSkip=\{/m,
  `<InstallingContent\n                  installChoice={installChoice}\n                  onComplete={handleInstallationComplete}\n                  onSkip={`
);

fs.writeFileSync(path, content, 'utf8');
