from fastapi import APIRouter

from fitminiapp_api.api.v1 import (
    admin,
    ai_coach,
    auth,
    bot,
    check_ins,
    coach,
    demo,
    hermes,
    hermes_articles,
    me,
    notifications,
    nutrition,
    program_imports,
    programs,
    public,
    report_handoffs,
    workouts,
)

api_router = APIRouter(prefix="/v1")

api_router.include_router(public.router, tags=["public"])
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai_coach.router, prefix="/ai-coach", tags=["ai-coach"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(programs.router, prefix="/programs", tags=["programs"])
api_router.include_router(
    program_imports.router, prefix="/programs/imports", tags=["program-imports"]
)
api_router.include_router(coach.router, prefix="/coach", tags=["coach"])
api_router.include_router(workouts.router, prefix="/workouts", tags=["workouts"])
api_router.include_router(check_ins.router, prefix="/check-ins", tags=["check-ins"])
api_router.include_router(nutrition.router, prefix="/nutrition", tags=["nutrition"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(
    report_handoffs.router, prefix="/report-handoffs", tags=["report-handoffs"]
)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(bot.router, prefix="/bot", tags=["bot"])
api_router.include_router(hermes.router, prefix="/hermes", tags=["hermes"])
api_router.include_router(hermes_articles.router, prefix="/hermes", tags=["hermes"])
