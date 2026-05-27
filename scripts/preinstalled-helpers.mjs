export function createRepoDirName(repo, ref) {
  const safeRepo = repo.replace(/[^a-zA-Z0-9._-]/g, '_').replace(/^_+|_+$/g, '');
  const safeRef = ref.replace(/[^a-zA-Z0-9._-]/g, '_').replace(/^_+|_+$/g, '');
  return `${safeRepo || 'repo'}__${safeRef || 'ref'}`;
}

export function normalizeRepoPath(repoPath) {
  return repoPath.replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');
}

export function createArchiveFileName(archivePath) {
  return archivePath.replace(/\\/g, '/').split('/').pop() || '.subset.tar';
}
