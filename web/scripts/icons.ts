// Regenerate PWA icons: bun run icons. Full-bleed square (no rx) so OS masks apply cleanly.
import sharp from "sharp";

const svg = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0e4f45"/><circle cx="32" cy="38" r="12" fill="#f2b84b"/><rect x="0" y="38" width="64" height="26" fill="#0e4f45"/><path d="M10 38h44" stroke="#eaf6f1" stroke-width="3" stroke-linecap="round"/><path d="M16 46h32M22 53h20" stroke="#7fd1b5" stroke-width="3" stroke-linecap="round"/></svg>`,
);

for (const size of [192, 512]) {
  await sharp(svg, { density: (72 * size) / 64 }).resize(size, size).png().toFile(`public/icon-${size}.png`);
}
