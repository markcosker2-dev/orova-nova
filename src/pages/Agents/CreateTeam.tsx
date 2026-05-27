import { CreateTeamDialog } from './components/CreateTeamDialog';

export function CreateTeamPage() {
  return (
    <div className="flex flex-col -m-6 dark:bg-background h-[calc(100vh-2.5rem)] overflow-hidden items-center justify-center">
      <CreateTeamDialog />
    </div>
  );
}
