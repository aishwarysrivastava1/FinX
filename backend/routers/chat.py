# backend/routers/chat.py
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional
from database import db_execute, db_fetchall
from services.gpt import chat_response
import uuid
from routes.auth import get_current_v2_user

router = APIRouter()

_MAX_MESSAGE_LEN = 2000


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message:    str

    @field_validator('message')
    @classmethod
    def message_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('message cannot be empty')
        if len(v) > _MAX_MESSAGE_LEN:
            raise ValueError(f'message too long (max {_MAX_MESSAGE_LEN} chars)')
        return v


@router.post('/chat')
def chat(req: ChatRequest, user=Depends(get_current_v2_user)):
    """
    Stateful multi-turn chat endpoint.
    Uses Groq (Llama-3.3-70B); falls back to OpenAI if unavailable.
    """
    try:
        session_id = req.session_id or str(uuid.uuid4())
        # v2 auth user.id is a UUID string; SQLite accepts it even if chat_sessions.user_id is typed as INTEGER.
        user_id = str(user.id)

        # Save incoming user message
        db_execute(
            'INSERT INTO chat_sessions (session_id, user_id, role, content) VALUES (?,?,?,?)',
            (session_id, user_id, 'user', req.message)
        )

        # Load last 10 turns (DESC from DB, then reverse for chronological order)
        history = db_fetchall(
            '''SELECT role, content FROM chat_sessions
               WHERE session_id=? AND user_id=?
               ORDER BY created_at DESC LIMIT 10''',
            (session_id, user_id)
        )
        history.reverse()

        # Get AI response with live market context
        reply = chat_response(history)

        # Save assistant reply
        db_execute(
            'INSERT INTO chat_sessions (session_id, user_id, role, content) VALUES (?,?,?,?)',
            (session_id, user_id, 'assistant', reply)
        )

        # Get total message count
        total = db_fetchall(
            'SELECT COUNT(*) as cnt FROM chat_sessions WHERE session_id=? AND user_id=?',
            (session_id, user_id)
        )

        return {
            'success': True,
            'data': {
                'session_id':    session_id,
                'reply':         reply,
                'message_count': total[0]['cnt'] if total else 0,
            },
            'error': None,
        }
    except ValueError as e:
        return JSONResponse(
            status_code=422,
            content={'success': False, 'data': None, 'error': str(e)},
        )
    except Exception as e:
        print(f'[Chat] Unhandled error: {e}')
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': 'Chat service temporarily unavailable.'},
        )


@router.delete('/chat/{session_id}')
def clear_chat(session_id: str, user=Depends(get_current_v2_user)):
    """Deletes all messages for a session."""
    try:
        db_execute(
            'DELETE FROM chat_sessions WHERE session_id=? AND user_id=?',
            (session_id, str(user.id)),
        )
        return {
            'success': True,
            'data': {'cleared': True, 'session_id': session_id},
            'error': None,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )
