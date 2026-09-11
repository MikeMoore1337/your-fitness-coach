// Авторские геометрические пиктограммы YFC. SVG используется только при сборке
// растров: интерфейс получает WebP, без стороннего векторного набора.
import { chromium } from "../frontend/node_modules/playwright/index.mjs";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const paths = {
  calendar:
    "M8 6H24V22H8ZM8 11H24M12 3V8M20 3V8M12 15H13M19 15H20M12 19H13M19 19H20",
  dumbbell: "M6 10V18M10 7V21M22 7V21M26 10V18M10 14H22",
  nutrition: "M6 12H26C25 24 7 24 6 12ZM19 12L25 4",
  profile: "M16 10A4 4 0 1 0 16 2A4 4 0 1 0 16 10M8 23V20C8 11 24 11 24 20V23Z",
  progress: "M7 22V15H10V22ZM14 22V10H17V22ZM21 22V4H24V22Z",
  security:
    "M16 3L24 6V13C24 18 19 22 16 24C13 22 8 18 8 13V6ZM12 12L15 15L21 9",
  ai: "M16 3L19 10L26 13L19 16L16 23L13 16L6 13L13 10ZM25 3V7M23 5H27",
  sun: "M21 13A5 5 0 1 1 11 13A5 5 0 1 1 21 13M16 2V4M16 22V24M5 13H7M25 13H27M8 5L10 7M22 19L24 21M8 21L10 19M22 7L24 5",
  moon: "M19 3A10 10 0 1 0 26 19C16 22 11 10 19 3Z",
  logout: "M15 4H8V22H15M14 13H26M21 8L26 13L21 18",
  "arrow-left": "M16 7L10 12L16 17M10 12H22",
  "arrow-right": "M16 7L22 12L16 17M10 12H22",
  check: "M9 12L13 16L22 7",
  "chevron-down": "M10 10L16 16L22 10",
  "chevron-left": "M19 6L13 12L19 18",
  "chevron-right": "M13 6L19 12L13 18",
  "chevron-up": "M10 15L16 9L22 15",
  close: "M11 7L21 17M21 7L11 17",
  "disclosure-closed": "M13 7L19 12L13 17",
  "disclosure-open": "M11 9L16 14L21 9",
  "external-link": "M17 6H23V12M23 6L15 14M13 7H9V19H21V15",
  menu: "M9 7H23M9 12H23M9 17H23",
  "mini-app": "M11 4H21V20H11ZM15 17H17",
  minus: "M10 12H22",
  "more-horizontal": "M10 12H10.2M16 12H16.2M22 12H22.2",
  "move-down": "M16 5V17M11 12L16 17L21 12M10 21H22",
  "move-up": "M16 20V8M11 13L16 8L21 13M10 4H22",
  plus: "M10 12H22M16 6V18",
  star: "M16 4L18.5 9L24 10L20 14L21 20L16 17L11 20L12 14L8 10L13.5 9Z",
  sync: "M10 8A7 7 0 0 1 23 10M23 5V10H18M22 16A7 7 0 0 1 9 14M9 19V14H14",
  timer: "M13 3H19M16 3V6M16 9V13L19 15M23 13A7 7 0 1 1 9 13A7 7 0 1 1 23 13",
  trash: "M9 7H23M13 7V4H19V7M11 7L12 21H20L21 7M15 11V17M18 11V17",
  "web-app":
    "M24 12A8 8 0 1 1 8 12A8 8 0 1 1 24 12M8 12H24M16 4C11 8 11 16 16 20C21 16 21 8 16 4",
  "confidence-insufficient": "M10 19V16M16 19V13M22 19V10M10 6L22 18",
  "confidence-limited": "M10 19V15M16 19V10M22 19V6",
  "confidence-stale": "M11 8A7 7 0 1 1 9 15M9 4V9H14M16 9V13H20",
  "confidence-sufficient": "M9 17V13M14 17V9M18 12L21 15L25 9",
  "nav-knowledge":
    "M16 7C13 4 10 4 7 5V19C10 18 13 18 16 21C19 18 22 18 25 19V5C22 4 19 4 16 7V21",
  "nav-admin":
    "M16 4L23 7V13C23 17 19 20 16 22C13 20 9 17 9 13V7ZM12 12L15 15L20 9",
  "nav-coach":
    "M16 11A3 3 0 1 0 16 5A3 3 0 1 0 16 11M9 21V18C9 12 23 12 23 18V21M23 6H27M25 4V8",
  achievement:
    "M11 4H21V11C21 17 11 17 11 11ZM11 7H7V10C7 13 11 13 11 13M21 7H25V10C25 13 21 13 21 13M16 16V21M12 21H20",
  "body-measurement": "M8 8H24V18H8ZM12 8V12M16 8V14M20 8V12",
  "body-weight": "M9 5H23V21H9ZM12 9Q16 5 20 9M16 8V12",
  calories: "M17 3C19 9 24 9 23 15C22 24 9 23 9 15C9 11 13 9 13 6L15 11Z",
  checklist: "M8 7L10 9L13 5M16 7H24M8 15L10 17L13 13M16 15H24M16 20H23",
  download: "M16 4V16M11 11L16 16L21 11M8 17V21H24V17",
  edit: "M9 16L20 5L24 9L13 20L8 21ZM17 8L21 12",
  print: "M11 9V4H21V9M11 18H8V10H24V18H21M11 15H21V22H11ZM21 12H21.1",
  protein: "M10 8C10 3 17 3 18 7C23 4 27 11 23 15L16 21L9 17C5 14 6 9 10 8Z",
  water:
    "M16 3C14 8 9 12 9 16A7 7 0 0 0 23 16C23 12 18 8 16 3ZM12 16C12 19 14 20 16 20",
  "workout-volume": "M8 10V16M11 7V19M21 7V19M24 10V16M11 13H21",
  error: "M16 4L24 8V17L16 22L8 17V8ZM12 9L20 17M20 9L12 17",
  info: "M16 4A9 9 0 1 1 16 22A9 9 0 1 1 16 4M16 11V18M16 8V8.1",
  loading: "M16 4A9 9 0 1 1 7 13",
  "permission-denied": "M11 11V8A5 5 0 0 1 21 8V11M9 11H23V22H9ZM16 15V18",
  warning: "M16 4L26 22H6ZM16 10V15M16 18V18.1",
  "week-cardio": "M7 14H11L14 7L18 19L21 12H26",
  "week-in-progress": "M12 5L23 13L12 21Z",
  "week-nutrition-complete": "M7 9H25C24 22 8 22 7 9ZM12 5L15 7L20 3",
  "week-nutrition-fasted": "M10 5L22 21M8 9H24C23 22 9 22 8 9",
  "week-nutrition-incomplete": "M7 9H25C24 22 8 22 7 9ZM16 11V16M16 19V19.1",
  "week-nutrition-missing": "M7 9H25C24 22 8 22 7 9ZM13 14H19",
  "week-planned": "M8 6H24V22H8ZM8 11H24M12 3V8M20 3V8M13 16H19M16 13V19",
  "week-rest": "M8 13V20M24 13V20M8 16H24M11 16V10H21V16M11 20V22M21 20V22",
  "week-skipped": "M10 6L21 13L10 20ZM24 6V20",
};
const aliases = {
  "star-filled": "star",
  "nav-more": "more-horizontal",
  "status-stale": "confidence-stale",
  success: "check",
  "week-completed": "check",
};
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  for (const [name, path] of Object.entries({
    ...paths,
    ...Object.fromEntries(
      Object.entries(aliases).map(([name, key]) => [name, paths[key]]),
    ),
  })) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 32 32"><g transform="translate(0 3)" fill="none" stroke="#b5f20b" stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"><path d="${path}" fill="${name === "star-filled" ? "#b5f20b" : "none"}"/></g></svg>`;
    const encoded = await page.evaluate(async (source) => {
      const image = new Image();
      image.src =
        "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 96;
      canvas.getContext("2d").drawImage(image, 0, 0);
      return canvas.toDataURL("image/webp", 0.85).split(",")[1];
    }, svg);
    await writeFile(
      fileURLToPath(
        new URL(
          `../frontend/public/assets/icons/flat-${name}.webp`,
          import.meta.url,
        ),
      ),
      Buffer.from(encoded, "base64"),
    );
  }
} finally {
  await browser.close();
}
