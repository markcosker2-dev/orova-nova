#!/usr/bin/env node
/**
 * Reads agent markdown files from a source directory and generates
 * a TypeScript data file with all agent templates.
 *
 * Usage:
 *   node scripts/generate-agent-templates.mjs <source-dir>
 *
 * Example:
 *   node scripts/generate-agent-templates.mjs /tmp/agency-agents
 *
 * Output:
 *   src/data/agent-templates.generated.ts
 */
import { existsSync, readFileSync, writeFileSync, readdirSync, statSync } from 'fs';
import { resolve, dirname, basename, extname, relative } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const OUT_PATH = resolve(ROOT, 'src/data/agent-templates.generated.ts');

const CATEGORY_LABELS = {
  academic: 'Academic',
  design: 'Design',
  engineering: 'Engineering',
  finance: 'Finance',
  'game-development': 'Game Development',
  integrations: 'Integrations',
  marketing: 'Marketing',
  'paid-media': 'Paid Media',
  product: 'Product',
  'project-management': 'Project Management',
  sales: 'Sales',
  'spatial-computing': 'Spatial Computing',
  specialized: 'Specialized',
  support: 'Support',
  testing: 'Testing',
};

/**
 * Parse YAML frontmatter from markdown content.
 * Expects `---` delimiters at the start of the file.
 */
function parseFrontmatter(content) {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('---')) return null;

  const endIndex = trimmed.indexOf('---', 3);
  if (endIndex === -1) return null;

  const yamlBlock = trimmed.slice(3, endIndex).trim();
  const body = trimmed.slice(endIndex + 3).trim();

  const meta = {};
  for (const line of yamlBlock.split('\n')) {
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) continue;
    const key = line.slice(0, colonIdx).trim();
    let value = line.slice(colonIdx + 1).trim();
    // Strip surrounding quotes
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    meta[key] = value;
  }

  return { meta, body };
}

/**
 * Recursively collect all .md files from a directory.
 */
function collectMarkdownFiles(dir, rootDir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = resolve(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      // Skip non-agent directories
      const dirName = basename(fullPath);
      if (['.github', 'scripts', 'examples', 'node_modules'].includes(dirName)) continue;
      results.push(...collectMarkdownFiles(fullPath, rootDir));
    } else if (extname(entry) === '.md') {
      // Skip known non-agent files
      const fileName = basename(entry, '.md').toLowerCase();
      if (['readme', 'contributing', 'contributing_zh-cn', 'security',
        'executive-brief', 'quickstart', 'nexus-strategy'].includes(fileName)) continue;

      const rel = relative(rootDir, fullPath).replace(/\\/g, '/');
      // Skip strategy coordination, playbooks, runbooks
      if (rel.startsWith('strategy/coordination/') ||
          rel.startsWith('strategy/playbooks/') ||
          rel.startsWith('strategy/runbooks/')) continue;

      results.push({ path: fullPath, relativePath: rel });
    }
  }
  return results;
}

/**
 * Derive category from the relative path (top-level directory).
 */
function deriveCategory(relativePath) {
  const parts = relativePath.split('/');
  return parts.length > 1 ? parts[0] : 'uncategorized';
}

/**
 * Derive a stable ID from the filename.
 */
function deriveId(relativePath) {
  const fileName = basename(relativePath, '.md');
  return fileName.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-');
}

/**
 * Escape a string for use inside a JS template literal.
 */
function escapeTemplateLiteral(str) {
  return str.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
}

function main() {
  const sourceDir = process.argv[2];
  if (!sourceDir || !existsSync(sourceDir)) {
    console.error('Usage: node scripts/generate-agent-templates.mjs <source-dir>');
    console.error('  source-dir must be the cloned agency-agents repository path');
    process.exit(1);
  }

  const absSourceDir = resolve(sourceDir);
  console.log(`Reading agent templates from: ${absSourceDir}`);

  const files = collectMarkdownFiles(absSourceDir, absSourceDir);
  console.log(`Found ${files.length} markdown files`);

  const templates = [];
  const categoryCount = {};

  for (const file of files) {
    const content = readFileSync(file.path, 'utf-8');
    const parsed = parseFrontmatter(content);

    // Only include files with valid frontmatter containing a name
    if (!parsed || !parsed.meta.name) {
      console.log(`  Skipping (no frontmatter/name): ${file.relativePath}`);
      continue;
    }

    const category = deriveCategory(file.relativePath);
    const id = deriveId(file.relativePath);

    templates.push({
      id,
      name: parsed.meta.name,
      description: parsed.meta.description || '',
      color: parsed.meta.color || undefined,
      emoji: parsed.meta.emoji || undefined,
      vibe: parsed.meta.vibe || undefined,
      category,
      soulContent: parsed.body,
    });

    categoryCount[category] = (categoryCount[category] || 0) + 1;
  }

  // Sort templates by category then name
  templates.sort((a, b) => {
    const catCmp = a.category.localeCompare(b.category);
    if (catCmp !== 0) return catCmp;
    return a.name.localeCompare(b.name);
  });

  // Build categories list
  const categories = Object.entries(categoryCount)
    .map(([id, count]) => ({
      id,
      label: CATEGORY_LABELS[id] || id.charAt(0).toUpperCase() + id.slice(1).replace(/-/g, ' '),
      count,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));

  console.log(`\nGenerated ${templates.length} agent templates in ${categories.length} categories:`);
  for (const cat of categories) {
    console.log(`  ${cat.label}: ${cat.count}`);
  }

  // Generate TypeScript file
  const lines = [
    '// Auto-generated by scripts/generate-agent-templates.mjs',
    '// Source: https://github.com/msitarzewski/agency-agents',
    '// Do not edit manually — regenerate with:',
    '//   node scripts/generate-agent-templates.mjs <agency-agents-repo-path>',
    '',
    "import type { AgentTemplate, AgentTemplateCategory } from '@/types/agent-template';",
    '',
    'export const AGENT_TEMPLATES: AgentTemplate[] = [',
  ];

  for (const t of templates) {
    lines.push('  {');
    lines.push(`    id: ${JSON.stringify(t.id)},`);
    lines.push(`    name: ${JSON.stringify(t.name)},`);
    lines.push(`    description: ${JSON.stringify(t.description)},`);
    if (t.color) lines.push(`    color: ${JSON.stringify(t.color)},`);
    if (t.emoji) lines.push(`    emoji: ${JSON.stringify(t.emoji)},`);
    if (t.vibe) lines.push(`    vibe: ${JSON.stringify(t.vibe)},`);
    lines.push(`    category: ${JSON.stringify(t.category)},`);
    lines.push(`    soulContent: \`${escapeTemplateLiteral(t.soulContent)}\`,`);
    lines.push('  },');
  }

  lines.push('];');
  lines.push('');
  lines.push('export const TEMPLATE_CATEGORIES: AgentTemplateCategory[] = [');
  for (const cat of categories) {
    lines.push(`  { id: ${JSON.stringify(cat.id)}, label: ${JSON.stringify(cat.label)}, count: ${cat.count} },`);
  }
  lines.push('];');
  lines.push('');

  writeFileSync(OUT_PATH, lines.join('\n'), 'utf-8');
  console.log(`\nWritten to: ${OUT_PATH}`);
}

main();
