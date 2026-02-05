"""
Posts API routes for sales rep.

GET /post?company_id - list posts (sort by date, likes, etc)
GET /post/:post_id - one post
POST /post - create post with appointment
PATCH /post/:post_id - edit post
DELETE /post/:post_id - delete post
POST /post/:post_id/like - like a post
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.core.dependencies import DbSession, get_current_user
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.schemas.post import PostCreate, PostUpdate
from app.services.post_service import PostService

router = APIRouter(tags=["posts"])


@router.get("/post")
async def list_posts(
    db: DbSession,
    company_id: UUID = Query(..., description="Company UUID"),
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    sort_by: str = Query("created_at", description="Sort field: created_at, likes"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),
):
    """
    Get all posts for a company, sorted by date, likes, etc.
    """
    service = PostService(db)
    posts = await service.list_posts(
        company_id=company_id,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {"posts": posts}


@router.get("/post/{post_id}")
async def get_post(
    post_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """Get one post by ID."""
    service = PostService(db)
    post = await service.get_post(post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.post("/post")
async def create_post(
    db: DbSession,
    body: PostCreate,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """Create a post linked to an appointment (sales rep posts with appointment)."""
    service = PostService(db)
    post = await service.create_post(
        appointment_id=body.appointment_id,
        poster_id=current_user.id,
        note=body.note,
        tags=body.tags,
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment not found or access denied",
        )
    return post


@router.patch("/post/{post_id}")
async def update_post(
    post_id: UUID,
    db: DbSession,
    body: PostUpdate,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """Update a post (edit note/tags)."""
    service = PostService(db)
    post = await service.update_post(
        post_id=post_id,
        note=body.note,
        tags=body.tags,
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.delete("/post/{post_id}")
async def delete_post(
    post_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """Delete a post."""
    service = PostService(db)
    ok = await service.delete_post(post_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return {"ok": True}


@router.post("/post/{post_id}/like")
async def like_post(
    post_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_any_role([UserRole.SALES_REP, UserRole.CSR, UserRole.EXECUTIVE])),
):
    """Like a post (increments like count)."""
    service = PostService(db)
    post = await service.like_post(post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post
