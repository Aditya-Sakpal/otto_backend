"""
SQLAlchemy base model.

All ORM models should inherit from this base.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.
    
    All ORM models inherit from this.
    """
    pass

