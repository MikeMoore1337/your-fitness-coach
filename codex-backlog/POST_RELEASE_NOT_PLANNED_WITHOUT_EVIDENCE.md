# Не планируется без отдельного evidence

Этот список запрещённых/speculative направлений не является универсальным real-user gate для
Product v8. После owner decision по Issue `#683` bounded task может попасть в Product v8 без
real-user evidence, если её user job и objective gap подтверждены текущим продуктом, scope
ограничен, есть технически проверяемая acceptance и нет критической external dependency.
Task `124B` / V8-00 удалена из Product v8 и не блокирует такой выбор; synthetic/demo evidence всё
равно нельзя выдавать за real-user evidence.

Даже после release gate `79` и переноса post-release tasks не добавлять автоматически:

- социальную сеть, друзей, ленту и лидерборды;
- публичные before/after и рейтинги тела;
- marketplace/ratings/payments тренерам;
- общий встроенный messenger и видеозвонки;
- GPS tracks/maps;
- автоматический MET calorie engine и eating-back calories;
- medical diagnosis/treatment;
- ААС/SARMs/pharmacology guidance;
- AI body analysis;
- точные калории/порции по одному фото еды и автоматическое сохранение AI-result без проверки;
- autonomous AI program/nutrition changes;
- universal readiness/health score;
- automatic news posting;
- English news channel;
- support for arbitrary files/exports;
- native rewrite только ради app-store presence;
- speculative admin hierarchy.

Любая новая идея проходит product discovery, trigger, boundaries, security/privacy/domain review и owner decision.
