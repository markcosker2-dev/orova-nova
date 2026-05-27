#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import png2icons from 'png2icons';
import { fileURLToPath } from 'url';

// Calculate paths
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');
const ICONS_DIR = path.join(PROJECT_ROOT, 'resources', 'icons');
const PNG_SOURCE = path.join(PROJECT_ROOT, 'logo.png');

console.log('🎨 Generating HermesClaw icons using Node.js...');

// Check if PNG source exists
if (!fs.existsSync(PNG_SOURCE)) {
  console.error(`❌ PNG source not found: ${PNG_SOURCE}`);
  process.exit(1);
}

// Ensure icons directory exists
fs.mkdirSync(ICONS_DIR, { recursive: true });

try {
  // 1. Generate Master PNG Buffer (1024x1024)
  console.log('  Processing PNG source...');
  const masterPngBuffer = await sharp(PNG_SOURCE)
    .resize(1024, 1024, {
      fit: 'contain',
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .png() // Ensure it's PNG
    .toBuffer();

  // Save the main icon.png (typically 512x512 for Electron root icon)
  await sharp(masterPngBuffer)
    .resize(512, 512)
    .toFile(path.join(ICONS_DIR, 'icon.png'));
  console.log('  ✅ Created icon.png (512x512)');

  // 2. Generate Windows .ico
  // png2icons expects a buffer. It returns a buffer (or null).
  // createICO(buffer, scalingAlgorithm, withSize, useMath)
  // scalingAlgorithm: 1 = Bilinear (better), 2 = Hermite (good), 3 = Bezier (best/slowest)
  // Defaulting to Bezier (3) for quality or Hermite (2) for speed. Let's use 2 (Hermite) as it's balanced.
  console.log('🪟 Generating Windows .ico...');
  const icoBuffer = png2icons.createICO(masterPngBuffer, png2icons.HERMITE, 0, false);
  
  if (icoBuffer) {
    fs.writeFileSync(path.join(ICONS_DIR, 'icon.ico'), icoBuffer);
    console.log('  ✅ Created icon.ico');
  } else {
    console.error('  ❌ Failed to create icon.ico');
    // detailed error might not be available from png2icons simple API, often returns null on failure
  }

  // 3. Generate macOS .icns
  console.log('🍎 Generating macOS .icns...');
  const icnsBuffer = png2icons.createICNS(masterPngBuffer, png2icons.HERMITE, 0);
  
  if (icnsBuffer) {
    fs.writeFileSync(path.join(ICONS_DIR, 'icon.icns'), icnsBuffer);
    console.log('  ✅ Created icon.icns');
  } else {
    console.error('  ❌ Failed to create icon.icns');
  }

  // 4. Generate Linux PNGs (various sizes)
  console.log('🐧 Generating Linux PNG icons...');
  const linuxSizes = [16, 32, 48, 64, 128, 256, 512];
  let generatedCount = 0;
  
  for (const size of linuxSizes) {
    await sharp(masterPngBuffer)
      .resize(size, size)
      .toFile(path.join(ICONS_DIR, `${size}x${size}.png`));
    generatedCount++;
  }
  console.log(`  ✅ Created ${generatedCount} Linux PNG icons`);

  // 5. Generate macOS Tray Icon Template
  console.log('📍 Generating macOS tray icon template...');
  await sharp(masterPngBuffer)
    .resize(22, 22, {
      fit: 'contain',
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .tint({ r: 0, g: 0, b: 0 })
    .png()
    .toFile(path.join(ICONS_DIR, 'tray-icon-Template.png'));
  console.log('  ✅ Created tray-icon-Template.png (22x22)');

  console.log(`\n✨ Icon generation complete! Files located in: ${ICONS_DIR}`);

} catch (error) {
  console.error(`\n❌ Fatal Error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
