"""Проверенные USDA Foundation и SR Legacy записи: точные FDC ID и названия источника.

Энергия Foundation может быть 2048 (Atwater specific), 2047 (Atwater general)
или legacy 1008. Не смешивать значения из разных FDC записей/основ питания.
"""

from __future__ import annotations

# id: (русское имя, точное английское описание USDA, dataType)
USDA_REVIEWED_FOUNDATION_LEGACY_V4: dict[str, tuple[str, str, str]] = {
    "1750340": ("Яблоко сорта Фуджи сырое с кожурой", "Apples, fuji, with skin, raw", "Foundation"),
    "1105073": ("Банан перезрелый сырой", "Bananas, overripe, raw", "Foundation"),
    "747447": ("Брокколи сырая, данные Foundation", "Broccoli, raw", "Foundation"),
    "2646170": (
        "Куриная грудка сырая без костей и кожи, данные Foundation",
        "Chicken, breast, boneless, skinless, raw",
        "Foundation",
    ),
    "748967": (
        "Яйца куриные категории A, крупные, целые",
        "Eggs, Grade A, Large, egg whole",
        "Foundation",
    ),
    "2346401": (
        "Картофель сорта Рассет сырой без кожуры",
        "Potatoes, russet, without skin, raw",
        "Foundation",
    ),
    "2512380": (
        "Рис бурый длиннозёрный необогащённый сухой",
        "Rice, brown, long grain, unenriched, raw",
        "Foundation",
    ),
    "2346393": (
        "Миндаль цельный сырой, данные Foundation",
        "Nuts, almonds, whole, raw",
        "Foundation",
    ),
    "2258586": ("Морковь зрелая сырая", "Carrots, mature, raw", "Foundation"),
    "173944": ("Банан сырой, данные SR Legacy", "Bananas, raw", "SR Legacy"),
    "170379": ("Брокколи сырая, данные SR Legacy", "Broccoli, raw", "SR Legacy"),
    "171077": (
        "Куриная грудка сырая без костей и кожи, данные SR Legacy",
        "Chicken, broiler or fryers, breast, skinless, boneless, meat only, raw",
        "SR Legacy",
    ),
    "171287": ("Яйцо куриное целое сырое свежее", "Egg, whole, raw, fresh", "SR Legacy"),
    "170026": ("Картофель сырой с кожурой и мякотью", "Potatoes, flesh and skin, raw", "SR Legacy"),
    "169703": (
        "Рис бурый длиннозёрный сухой, данные SR Legacy",
        "Rice, brown, long-grain, raw (Includes foods for USDA's Food Distribution Program)",
        "SR Legacy",
    ),
    "170567": ("Миндаль, данные SR Legacy", "Nuts, almonds", "SR Legacy"),
    "171689": ("Яблоко сырое без кожуры", "Apples, raw, without skin", "SR Legacy"),
    "171052": (
        "Мясо куриное сырое без кожи, данные SR Legacy",
        "Chicken, broilers or fryers, meat only, raw",
        "SR Legacy",
    ),
}

USDA_REVIEWED_SEARCH_GROUPS_V4: dict[str, tuple[str, ...]] = {
    "банан": ("1105073", "173944"),
    "банан перезрелый": ("1105073",),
    "брокколи": ("747447", "170379"),
    "куриная грудка": ("2646170", "171077"),
    "куриная грудка сырая": ("2646170", "171077"),
    "куриное мясо сырое": ("171052",),
    "яйца": ("748967", "171287"),
    "яйцо сырое": ("171287",),
    "яблоко": ("1750340", "171689"),
    "яблоко без кожуры": ("171689",),
    "морковь": ("2258586",),
    "картофель": ("2346401", "170026"),
    "картофель сырой": ("2346401", "170026"),
    "рис": ("2512380", "169703"),
    "рис бурый сухой": ("2512380", "169703"),
    "миндаль": ("2346393", "170567"),
    "миндаль сырой": ("2346393",),
}
