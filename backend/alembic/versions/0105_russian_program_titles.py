"""Normalize legacy system program titles to Russian-first product copy."""

from collections.abc import Sequence

from alembic import op

revision: str = "0105_russian_program_titles"
down_revision: str | None = "0104_photo_meal_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_notes = (
    "Idempotently localizes only the small built-in system program catalog: known template/day "
    "titles, exercise notes and the legacy AMRAP 12 display value. User-owned and custom "
    "program content is never rewritten."
)
online_rollout_batch_size = 100
online_rollout_idempotent = True


def upgrade() -> None:
    op.execute(
        """UPDATE program_templates
        SET title = CASE title
            WHEN 'Beginner Full Body' THEN 'Для начинающих - всё тело'
            WHEN 'Beginner Strength' THEN 'Для начинающих - развитие силы'
            WHEN 'Beginner Hypertrophy' THEN 'Для начинающих - рост мышц'
            WHEN 'Beginner Upper/Lower' THEN 'Для начинающих - верх/низ'
            WHEN 'Beginner Push/Pull/Legs' THEN 'Для начинающих - толкай/тяни/ноги (PPL)'
            WHEN 'Intermediate Full Body' THEN 'Средний уровень - всё тело'
            WHEN 'Intermediate Strength' THEN 'Средний уровень - развитие силы'
            WHEN 'Intermediate Hypertrophy' THEN 'Средний уровень - рост мышц'
            WHEN 'Intermediate Upper/Lower' THEN 'Средний уровень - верх/низ'
            WHEN 'Intermediate Push/Pull/Legs' THEN 'Средний уровень - толкай/тяни/ноги (PPL)'
            WHEN 'Advanced Full Body' THEN 'Продвинутый уровень - всё тело'
            WHEN 'Advanced Strength' THEN 'Продвинутый уровень - развитие силы'
            WHEN 'Advanced Hypertrophy' THEN 'Продвинутый уровень - рост мышц'
            WHEN 'Advanced Upper/Lower' THEN 'Продвинутый уровень - верх/низ'
            WHEN 'Advanced Push/Pull/Legs' THEN 'Продвинутый уровень - толкай/тяни/ноги (PPL)'
            WHEN 'Фуллбади 3 дня' THEN 'Всё тело · 3 дня'
            WHEN 'Тяни/Толкай/Ноги/Фуллбади · 4 дня' THEN 'Толкай/тяни/ноги/всё тело · 4 дня'
            WHEN 'Тяни/Толкай/Ноги/Фуллбади · 8 дней' THEN 'Толкай/тяни/ноги/всё тело · 8 дней'
            WHEN 'Тяни-толкай-ноги 6 дней' THEN 'Толкай/тяни/ноги (PPL) · 6 дней'
            WHEN 'Верх-низ 4 дня' THEN 'Верх/низ · 4 дня'
            WHEN 'PHUL (сила и гипертрофия, верх/низ)' THEN 'PHUL (сила и рост мышц, верх/низ)'
            WHEN 'Линейная прогрессия Metallicdpa - PPL (толкай/тяни/ноги)'
                THEN 'Линейная прогрессия Metallicdpa - толкай/тяни/ноги (PPL)'
            WHEN 'Гантельная PPL (толкай/тяни/ноги)'
                THEN 'Гантельная программа «толкай/тяни/ноги» (PPL)'
            ELSE title
        END
        WHERE owner_user_id IS NULL
          AND created_by_user_id IS NULL
          AND title IN (
            'Beginner Full Body', 'Beginner Strength', 'Beginner Hypertrophy',
            'Beginner Upper/Lower', 'Beginner Push/Pull/Legs',
            'Intermediate Full Body', 'Intermediate Strength', 'Intermediate Hypertrophy',
            'Intermediate Upper/Lower', 'Intermediate Push/Pull/Legs',
            'Advanced Full Body', 'Advanced Strength', 'Advanced Hypertrophy',
            'Advanced Upper/Lower', 'Advanced Push/Pull/Legs',
            'Фуллбади 3 дня', 'Тяни/Толкай/Ноги/Фуллбади · 4 дня',
            'Тяни/Толкай/Ноги/Фуллбади · 8 дней', 'Тяни-толкай-ноги 6 дней',
            'Верх-низ 4 дня', 'PHUL (сила и гипертрофия, верх/низ)',
            'Линейная прогрессия Metallicdpa - PPL (толкай/тяни/ноги)',
            'Гантельная PPL (толкай/тяни/ноги)'
          )"""
    )
    op.execute(
        """UPDATE program_template_days
        SET title = CASE title
            WHEN 'Фуллбади' THEN 'Всё тело'
            WHEN 'Фуллбади A' THEN 'Всё тело A'
            WHEN 'Фуллбади B' THEN 'Всё тело B'
            WHEN 'Фуллбади C' THEN 'Всё тело C'
            WHEN 'Фуллбади D' THEN 'Всё тело D'
            WHEN 'Фуллбади E' THEN 'Всё тело E'
            ELSE title
        END
        WHERE program_id IN (
            SELECT id FROM program_templates
            WHERE owner_user_id IS NULL AND created_by_user_id IS NULL
        )
          AND title IN (
            'Фуллбади', 'Фуллбади A', 'Фуллбади B',
            'Фуллбади C', 'Фуллбади D', 'Фуллбади E'
          )"""
    )
    op.execute(
        """UPDATE program_template_exercises
        SET notes = CASE
            WHEN notes LIKE 'T1%last set AMRAP'
                THEN 'T1 - основное тяжёлое упражнение, последний подход - максимум повторений (AMRAP)'
            WHEN notes = 'T2'
                THEN 'T2 - объёмное базовое упражнение'
            WHEN notes LIKE 'T3%last set AMRAP' AND notes NOT LIKE '%selected DB row variant%'
                THEN 'T3 - вспомогательное упражнение, последний подход - максимум повторений (AMRAP)'
            WHEN notes LIKE 'T3%selected DB row variant%last set AMRAP'
                THEN 'T3 - вспомогательное упражнение, выбран вариант тяги гантели, последний подход - максимум повторений (AMRAP)'
            WHEN notes LIKE 'Main lift%percentage basis is TRAINING_MAX'
                THEN 'Основное упражнение, проценты от тренировочного максимума'
            WHEN notes LIKE 'FSL%first-set Training Max load'
                THEN 'Повтор первого рабочего подхода (FSL), вес от тренировочного максимума'
            WHEN notes = 'Assistance boundary'
                THEN 'Вспомогательное упражнение'
            WHEN notes LIKE 'Source range%4 sets selected'
                THEN 'Диапазон из источника, выбрано 4 подхода'
            WHEN notes LIKE 'Source range%3 sets selected'
                THEN 'Диапазон из источника, выбрано 3 подхода'
            WHEN notes LIKE 'T1%ordered TRAINING_MAX loads%final AMRAP'
                THEN 'T1 - основное упражнение, веса по процентам от тренировочного максимума, последний подход - максимум повторений (AMRAP)'
            WHEN notes LIKE 'T2%ordered TRAINING_MAX loads%final AMRAP'
                THEN 'T2 - второе базовое упражнение, веса по процентам от тренировочного максимума, последний подход - максимум повторений (AMRAP)'
            WHEN notes LIKE 'Main lift%final set AMRAP'
                THEN 'Основное упражнение, последний подход - максимум повторений (AMRAP)'
            WHEN notes LIKE 'Alternating main lift%final set AMRAP'
                THEN 'Чередующееся основное упражнение, последний подход - максимум повторений (AMRAP)'
            ELSE notes
        END
        WHERE day_id IN (
            SELECT day.id
            FROM program_template_days AS day
            JOIN program_templates AS template ON template.id = day.program_id
            WHERE template.owner_user_id IS NULL AND template.created_by_user_id IS NULL
        )
          AND (
            notes = 'T2'
            OR notes = 'Assistance boundary'
            OR notes LIKE 'T1%last set AMRAP'
            OR notes LIKE 'T3%last set AMRAP'
            OR notes LIKE 'Main lift%percentage basis is TRAINING_MAX'
            OR notes LIKE 'FSL%first-set Training Max load'
            OR notes LIKE 'Source range%4 sets selected'
            OR notes LIKE 'Source range%3 sets selected'
            OR notes LIKE 'T1%ordered TRAINING_MAX loads%final AMRAP'
            OR notes LIKE 'T2%ordered TRAINING_MAX loads%final AMRAP'
            OR notes LIKE 'Main lift%final set AMRAP'
            OR notes LIKE 'Alternating main lift%final set AMRAP'
          )"""
    )
    op.execute(
        """UPDATE program_template_exercises
        SET prescribed_reps = 'максимум до 12'
        WHERE prescribed_reps = 'AMRAP 12'
          AND day_id IN (
            SELECT day.id
            FROM program_template_days AS day
            JOIN program_templates AS template ON template.id = day.program_id
            WHERE template.owner_user_id IS NULL AND template.created_by_user_id IS NULL
          )"""
    )


def downgrade() -> None:
    pass
