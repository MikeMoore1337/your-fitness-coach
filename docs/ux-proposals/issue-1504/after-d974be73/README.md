# Dock 4+1: фактическая реализация

Коммит приложения: `d974be73db77c50331b706646170e32cc6b90c49`. Issue #1504, PR #1505.
Снимки получены локально в Chromium и WebKit на тестовых данных. Ширины 320, 360, 390, 393 и 430 CSS px, тёмная и светлая темы. Zoom 200% проверен в Chromium. Demo снят до финального исправления возврата фокуса; его вид не менялся.

## Экраны

### Chromium
- 320px, dark: [today](chromium/today-320-dark.png) · [programs](chromium/programs-320-dark.png) · [nutrition](chromium/nutrition-320-dark.png) · [progress](chromium/progress-320-dark.png) · [quick-add](chromium/quick-add-320-dark.png)
- 360px, dark: [today](chromium/today-360-dark.png) · [programs](chromium/programs-360-dark.png) · [nutrition](chromium/nutrition-360-dark.png) · [progress](chromium/progress-360-dark.png) · [quick-add](chromium/quick-add-360-dark.png)
- 390px, dark: [today](chromium/today-390-dark.png) · [programs](chromium/programs-390-dark.png) · [nutrition](chromium/nutrition-390-dark.png) · [progress](chromium/progress-390-dark.png) · [quick-add](chromium/quick-add-390-dark.png)
- 393px, dark: [today](chromium/today-393-dark.png) · [programs](chromium/programs-393-dark.png) · [nutrition](chromium/nutrition-393-dark.png) · [progress](chromium/progress-393-dark.png) · [quick-add](chromium/quick-add-393-dark.png)
- 430px, dark: [today](chromium/today-430-dark.png) · [programs](chromium/programs-430-dark.png) · [nutrition](chromium/nutrition-430-dark.png) · [progress](chromium/progress-430-dark.png) · [quick-add](chromium/quick-add-430-dark.png)
- 320px, light: [today](chromium/today-320-light.png) · [programs](chromium/programs-320-light.png) · [nutrition](chromium/nutrition-320-light.png) · [progress](chromium/progress-320-light.png) · [quick-add](chromium/quick-add-320-light.png)
- 360px, light: [today](chromium/today-360-light.png) · [programs](chromium/programs-360-light.png) · [nutrition](chromium/nutrition-360-light.png) · [progress](chromium/progress-360-light.png) · [quick-add](chromium/quick-add-360-light.png)
- 390px, light: [today](chromium/today-390-light.png) · [programs](chromium/programs-390-light.png) · [nutrition](chromium/nutrition-390-light.png) · [progress](chromium/progress-390-light.png) · [quick-add](chromium/quick-add-390-light.png)
- 393px, light: [today](chromium/today-393-light.png) · [programs](chromium/programs-393-light.png) · [nutrition](chromium/nutrition-393-light.png) · [progress](chromium/progress-393-light.png) · [quick-add](chromium/quick-add-393-light.png)
- 430px, light: [today](chromium/today-430-light.png) · [programs](chromium/programs-430-light.png) · [nutrition](chromium/nutrition-430-light.png) · [progress](chromium/progress-430-light.png) · [quick-add](chromium/quick-add-430-light.png)

### Webkit
- 320px, dark: [today](webkit/today-320-dark.png) · [programs](webkit/programs-320-dark.png) · [nutrition](webkit/nutrition-320-dark.png) · [progress](webkit/progress-320-dark.png) · [quick-add](webkit/quick-add-320-dark.png)
- 360px, dark: [today](webkit/today-360-dark.png) · [programs](webkit/programs-360-dark.png) · [nutrition](webkit/nutrition-360-dark.png) · [progress](webkit/progress-360-dark.png) · [quick-add](webkit/quick-add-360-dark.png)
- 390px, dark: [today](webkit/today-390-dark.png) · [programs](webkit/programs-390-dark.png) · [nutrition](webkit/nutrition-390-dark.png) · [progress](webkit/progress-390-dark.png) · [quick-add](webkit/quick-add-390-dark.png)
- 393px, dark: [today](webkit/today-393-dark.png) · [programs](webkit/programs-393-dark.png) · [nutrition](webkit/nutrition-393-dark.png) · [progress](webkit/progress-393-dark.png) · [quick-add](webkit/quick-add-393-dark.png)
- 430px, dark: [today](webkit/today-430-dark.png) · [programs](webkit/programs-430-dark.png) · [nutrition](webkit/nutrition-430-dark.png) · [progress](webkit/progress-430-dark.png) · [quick-add](webkit/quick-add-430-dark.png)
- 320px, light: [today](webkit/today-320-light.png) · [programs](webkit/programs-320-light.png) · [nutrition](webkit/nutrition-320-light.png) · [progress](webkit/progress-320-light.png) · [quick-add](webkit/quick-add-320-light.png)
- 360px, light: [today](webkit/today-360-light.png) · [programs](webkit/programs-360-light.png) · [nutrition](webkit/nutrition-360-light.png) · [progress](webkit/progress-360-light.png) · [quick-add](webkit/quick-add-360-light.png)
- 390px, light: [today](webkit/today-390-light.png) · [programs](webkit/programs-390-light.png) · [nutrition](webkit/nutrition-390-light.png) · [progress](webkit/progress-390-light.png) · [quick-add](webkit/quick-add-390-light.png)
- 393px, light: [today](webkit/today-393-light.png) · [programs](webkit/programs-393-light.png) · [nutrition](webkit/nutrition-393-light.png) · [progress](webkit/progress-393-light.png) · [quick-add](webkit/quick-add-393-light.png)
- 430px, light: [today](webkit/today-430-light.png) · [programs](webkit/programs-430-light.png) · [nutrition](webkit/nutrition-430-light.png) · [progress](webkit/progress-430-light.png) · [quick-add](webkit/quick-add-430-light.png)

## Demo и масштаб

- [demo-mode-production-compo-11a0b-board-focus-phone-430-dark--chromium](demo/demo-mode-production-compo-11a0b-board-focus-phone-430-dark--chromium.png)
- [demo-mode-production-compo-11a0b-board-focus-phone-430-dark--webkit](demo/demo-mode-production-compo-11a0b-board-focus-phone-430-dark--webkit.png)
- [demo-mode-production-compo-2a5c5-oard-focus-phone-390-light--chromium](demo/demo-mode-production-compo-2a5c5-oard-focus-phone-390-light--chromium.png)
- [demo-mode-production-compo-2a5c5-oard-focus-phone-390-light--webkit](demo/demo-mode-production-compo-2a5c5-oard-focus-phone-390-light--webkit.png)
- [demo-mode-production-compo-321ba-board-focus-phone-360-dark--chromium](demo/demo-mode-production-compo-321ba-board-focus-phone-360-dark--chromium.png)
- [demo-mode-production-compo-321ba-board-focus-phone-360-dark--webkit](demo/demo-mode-production-compo-321ba-board-focus-phone-360-dark--webkit.png)
- [demo-mode-production-compo-3c141-board-focus-phone-320-dark--chromium](demo/demo-mode-production-compo-3c141-board-focus-phone-320-dark--chromium.png)
- [demo-mode-production-compo-3c141-board-focus-phone-320-dark--webkit](demo/demo-mode-production-compo-3c141-board-focus-phone-320-dark--webkit.png)
- [demo-mode-production-compo-3f354-board-focus-phone-390-dark--chromium](demo/demo-mode-production-compo-3f354-board-focus-phone-390-dark--chromium.png)
- [demo-mode-production-compo-3f354-board-focus-phone-390-dark--webkit](demo/demo-mode-production-compo-3f354-board-focus-phone-390-dark--webkit.png)
- [demo-mode-production-compo-6b5fe-oard-focus-phone-360-light--chromium](demo/demo-mode-production-compo-6b5fe-oard-focus-phone-360-light--chromium.png)
- [demo-mode-production-compo-6b5fe-oard-focus-phone-360-light--webkit](demo/demo-mode-production-compo-6b5fe-oard-focus-phone-360-light--webkit.png)
- [demo-mode-production-compo-6becd-oard-focus-phone-430-light--chromium](demo/demo-mode-production-compo-6becd-oard-focus-phone-430-light--chromium.png)
- [demo-mode-production-compo-6becd-oard-focus-phone-430-light--webkit](demo/demo-mode-production-compo-6becd-oard-focus-phone-430-light--webkit.png)
- [demo-mode-production-compo-6e79a-oard-focus-tablet-768-dark--chromium](demo/demo-mode-production-compo-6e79a-oard-focus-tablet-768-dark--chromium.png)
- [demo-mode-production-compo-6e79a-oard-focus-tablet-768-dark--webkit](demo/demo-mode-production-compo-6e79a-oard-focus-tablet-768-dark--webkit.png)
- [demo-mode-production-compo-88f42-oard-focus-phone-320-light--chromium](demo/demo-mode-production-compo-88f42-oard-focus-phone-320-light--chromium.png)
- [demo-mode-production-compo-88f42-oard-focus-phone-320-light--webkit](demo/demo-mode-production-compo-88f42-oard-focus-phone-320-light--webkit.png)
- [demo-mode-production-compo-d96b8-ard-focus-tablet-768-light--chromium](demo/demo-mode-production-compo-d96b8-ard-focus-tablet-768-light--chromium.png)
- [demo-mode-production-compo-d96b8-ard-focus-tablet-768-light--webkit](demo/demo-mode-production-compo-d96b8-ard-focus-tablet-768-light--webkit.png)
- [dock-zoom-200-light](zoom/dock-zoom-200-light.png)
- [dock-zoom-200-dark](zoom/dock-zoom-200-dark.png)