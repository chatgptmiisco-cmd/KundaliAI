from fastapi import APIRouter

from app.api.v1 import admin, analysis, auth, chart, chat, dasha, horoscope, kundali, subscription, user, voice

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(chart.router)
api_router.include_router(dasha.router)
api_router.include_router(horoscope.router)
api_router.include_router(analysis.router)
api_router.include_router(kundali.router)
api_router.include_router(voice.router)
api_router.include_router(chat.router)
api_router.include_router(subscription.router)
api_router.include_router(admin.router)
