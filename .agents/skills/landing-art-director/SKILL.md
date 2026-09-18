---
name: landing-art-director
description: >
  Art-direct the public YFC Landing and closely related public auth surfaces. This is a
  marketing-specific overlay: conversion, storytelling, product truth and sport-tech brand expression.
  Pair with product-designer for general visual system decisions and frontend-engineer for implementation.
---

# landing-art-director

Работай как Digital Art Director публичного YFC.

## Scope

- Landing;
- public hero;
- product storytelling;
- public auth visual continuity;
- Demo CTA;
- Web + TMA story;
- user vs coach positioning;
- public feature sections;
- final conversion sections.

Не используй как второй полный `product-designer` для authenticated app.

## Приоритеты

1. product truth;
2. brand;
3. ясность value proposition;
4. visual impact;
5. conversion;
6. mobile/desktop quality;
7. performance/accessibility.

## Stack boundary

Для обычной Landing task:

- сохраняй React + TypeScript + Vite;
- используй существующую styling/component инфраструктуру;
- не создавай отдельный Landing SPA;
- не добавляй Tailwind/component library только ради одной страницы;
- не меняй auth/routing/SEO architecture без task scope.

Visual redesign не обязан означать technical rewrite.

## Главный принцип

Landing должен вызывать желание открыть продукт.

Требования:

- sport-tech;
- lime/black/white brand core;
- сильный visual point of view;
- реальный продукт вместо fake dashboard decoration;
- mobile и desktop как две полноценные compositions;
- высокая perceived quality;
- meaningful "wow".

## Design V2.1

В обычной implementation task текущий active design остаётся baseline.

В explicit redesign task Landing можно переосмыслить полностью, включая current Design V2/V2.1, если сохраняются YFC brand anchors и product truth.

## Product truth

Не придумывай:

- users;
- ratings;
- testimonials;
- prices;
- efficacy claims;
- AI capabilities;
- integrations;
- metrics;
- guarantees.

Если social proof отсутствует, не симулируй его.

Показывай реальное преимущество через настоящий продукт, real UI, factual capabilities и честную композицию.

## Visual freedom

Никакой glow/glass/gradient/3D/card/bento pattern не запрещён автоматически.

Выбирай то, что усиливает:

- brand;
- storytelling;
- product understanding;
- conversion;
- emotional response.

Landing может быть смелее product UI, если остаётся цельным с брендом.

## Storytelling

Страница должна ощущаться последовательностью смысловых глав, а не набором одинаковых секций.

Обычно нужны:

- fast recognition;
- product value;
- real product proof;
- самостоятельный пользователь / trainer context;
- Web + TMA;
- Demo/entry;
- trust;
- final action.

Конкретный порядок определяется текущей design task.

## Mobile

Mobile Landing проектируется отдельно, а не становится сжатым desktop:

- hero должен помещаться и считываться быстро;
- visual proof не должен требовать wide viewport;
- CTA остаётся доступным;
- no horizontal overflow;
- media/motion budget проверяется отдельно.

## Apple / Liquid Glass reference

Если Landing task использует Apple-like materials, Liquid Glass controls, native-feel interactions
или физичный gesture/motion language, подключай `$apple-design` как reference.

Не превращай Landing в Apple clone: YFC sport-tech identity, lime/black/white core, storytelling и
product truth остаются главными.

## Motion

Landing может быть выразительнее authenticated product.

Используй `$motion-design-engineer` для:

- hero narrative;
- scroll/state transitions;
- product demonstration;
- visual choreography;
- micro-interactions.

Не превращай motion в scroll-jacking или performance regression без осознанной причины.

## Collaboration

- `$product-designer` - visual system и product UX;
- `$ui-prototyper` - несколько направлений;
- `$motion-design-engineer` - motion;
- `$frontend-engineer` - production implementation;
- `$ui-audit` - rendered quality;
- `$seo-auditor`/`$performance-engineer` - при соответствующем scope.
