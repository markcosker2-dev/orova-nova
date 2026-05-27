#!/usr/bin/env zx

import 'zx/globals';
import {
  createWriteStream,
  readFileSync,
  existsSync,
  mkdirSync,
  rmSync,
  cpSync,
  writeFileSync,
} from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { createArchiveFileName, createRepoDirName, normalizeRepoPath } from './preinstalled-helpers.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const MANIFEST_PATH = join(ROOT, 'resources', 'skills', 'preinstalled-manifest.json');
const OUTPUT_ROOT = join(ROOT, 'build', 'preinstalled-skills');
const TMP_ROOT = join(ROOT, 'build', '.tmp-preinstalled-skills');

function loadManifest() {
  if (!existsSync(MANIFEST_PATH)) {
    throw new Error(`Missing manifest: ${MANIFEST_PATH}`);
  }
  const raw = readFileSync(MANIFEST_PATH, 'utf8');
  const parsed = JSON.parse(raw);
  if (!parsed || !Array.isArray(parsed.skills)) {
    throw new Error('Invalid preinstalled-skills manifest format');
  }
  for (const item of parsed.skills) {
    if (!item.slug || !item.repo || !item.repoPath) {
      throw new Error(`Invalid manifest entry: ${JSON.stringify(item)}`);
    }
  }
  return parsed.skills;
}

function groupByRepoRef(entries) {
  const grouped = new Map();
  for (const entry of entries) {
    const ref = entry.ref || 'main';
    const key = `${entry.repo}#${ref}`;
    if (!grouped.has(key)) grouped.set(key, { repo: entry.repo, ref, entries: [] });
    grouped.get(key).entries.push(entry);
  }
  return [...grouped.values()];
}

function shouldCopySkillFile(srcPath) {
  const base = basename(srcPath);
  if (base === '.git') return false;
  if (base === '.subset.tar') return false;
  return true;
}

async function extractArchive(archivePath, cwd) {
  const archiveFileName = createArchiveFileName(archivePath);
  const prevCwd = $.cwd;
  $.cwd = cwd;
  try {
    try {
      await $`tar -xf ${archiveFileName}`;
      return;
    } catch (tarError) {
      if (process.platform === 'win32') {
        // Some Windows images expose bsdtar instead of tar.
        await $`bsdtar -xf ${archiveFileName}`;
        return;
      }
      throw tarError;
    }
  } finally {
    $.cwd = prevCwd;
  }
}

function runArchiveToFile(args, cwd, outputPath) {
  return new Promise((resolve, reject) => {
    const output = createWriteStream(outputPath, { flags: 'w' });
    let settled = false;

    const fail = (error) => {
      if (settled) return;
      settled = true;
      output.destroy();
      reject(error);
    };

    output.on('error', fail);

    const child = spawn('git', args, {
      cwd,
      stdio: ['ignore', 'pipe', 'inherit'],
      windowsHide: true,
    });

    child.on('error', fail);
    child.stdout.pipe(output);
    child.on('close', (code) => {
      output.end(() => {
        if (settled) return;
        settled = true;
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`git ${args.join(' ')} exited with code ${code}`));
        }
      });
    });
  });
}

function runGit(args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn('git', args, {
      cwd,
      stdio: 'inherit',
      windowsHide: true,
    });

    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`git ${args.join(' ')} exited with code ${code}`));
      }
    });
  });
}

function readGit(args, cwd) {
  return new Promise((resolve, reject) => {
    let stdout = '';
    const child = spawn('git', args, {
      cwd,
      stdio: ['ignore', 'pipe', 'inherit'],
      windowsHide: true,
    });

    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(`git ${args.join(' ')} exited with code ${code}`));
      }
    });
  });
}

async function fetchSparseRepo(repo, ref, paths, checkoutDir) {
  const remote = `https://github.com/${repo}.git`;
  mkdirSync(checkoutDir, { recursive: true });
  const archiveFileName = '.subset.tar';
  const archivePath = join(checkoutDir, archiveFileName);
  const archivePaths = [...new Set(paths.map(normalizeRepoPath))];

  await runGit(['init'], checkoutDir);
  await runGit(['remote', 'add', 'origin', remote], checkoutDir);
  await runGit(['fetch', '--depth', '1', 'origin', ref], checkoutDir);
  // Do not checkout working tree on Windows: upstream repos may contain
  // Windows-invalid paths. Export only requested directories via git archive.
  // Do not use `git archive --output` from zx/bash on Windows. Git/MSYS can
  // reinterpret even relative output paths as a drive-prefixed archive member
  // and extract `D/...` into the project parent. Stream stdout into a Node
  // file handle instead so the archive file is created exactly under TMP_ROOT.
  await runArchiveToFile(['archive', '--format=tar', 'FETCH_HEAD', ...archivePaths], checkoutDir, archivePath);
  if (!existsSync(archivePath)) {
    throw new Error(`Expected archive was not created: ${archivePath}`);
  }
  await extractArchive(archivePath, checkoutDir);
  rmSync(archivePath, { force: true });

  const commit = await readGit(['rev-parse', 'FETCH_HEAD'], checkoutDir);
  return commit;
}

echo`Bundling preinstalled skills...`;

if (process.env.SKIP_PREINSTALLED_SKILLS === '1') {
  echo`⏭  SKIP_PREINSTALLED_SKILLS=1 set, skipping skills fetch.`;
  process.exit(0);
}

const manifestSkills = loadManifest();

rmSync(OUTPUT_ROOT, { recursive: true, force: true });
mkdirSync(OUTPUT_ROOT, { recursive: true });
rmSync(TMP_ROOT, { recursive: true, force: true });
mkdirSync(TMP_ROOT, { recursive: true });

const lock = {
  generatedAt: new Date().toISOString(),
  skills: [],
};

try {
  const groups = groupByRepoRef(manifestSkills);
  for (const group of groups) {
    const repoDir = join(TMP_ROOT, createRepoDirName(group.repo, group.ref));
    const sparsePaths = [...new Set(group.entries.map((entry) => entry.repoPath))];

    echo`Fetching ${group.repo} @ ${group.ref}`;
    const commit = await fetchSparseRepo(group.repo, group.ref, sparsePaths, repoDir);
    echo`   commit ${commit}`;

    for (const entry of group.entries) {
      const sourceDir = join(repoDir, entry.repoPath);
      const targetDir = join(OUTPUT_ROOT, entry.slug);

      if (!existsSync(sourceDir)) {
        throw new Error(`Missing source path in repo checkout: ${entry.repoPath}`);
      }

      rmSync(targetDir, { recursive: true, force: true });
      cpSync(sourceDir, targetDir, { recursive: true, dereference: true, filter: shouldCopySkillFile });

      const skillManifest = join(targetDir, 'SKILL.md');
      if (!existsSync(skillManifest)) {
        throw new Error(`Skill ${entry.slug} is missing SKILL.md after copy`);
      }

      const requestedVersion = (entry.version || '').trim();
      const resolvedVersion = !requestedVersion || requestedVersion === 'main'
        ? commit
        : requestedVersion;
      lock.skills.push({
        slug: entry.slug,
        version: resolvedVersion,
        repo: entry.repo,
        repoPath: entry.repoPath,
        ref: group.ref,
        commit,
      });

      echo`   OK ${entry.slug}`;
    }
  }

  writeFileSync(join(OUTPUT_ROOT, '.preinstalled-lock.json'), `${JSON.stringify(lock, null, 2)}\n`, 'utf8');
  echo`Preinstalled skills ready: ${OUTPUT_ROOT}`;
} finally {
  rmSync(TMP_ROOT, { recursive: true, force: true });
}
