"""Accesso alla sessione Flask-SQLAlchemy configurata da dflango."""

from typing import cast

from dflango.db import db
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def get_engine() -> Engine:
    return db.engine


def get_session() -> Session:
    return cast(Session, db.session)
