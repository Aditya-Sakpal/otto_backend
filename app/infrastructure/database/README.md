# Database Schema Management

## Overview

This backend supports two approaches for managing database schema:

1. **Automatic Table Creation** (Development only)
2. **Alembic Migrations** (Production recommended)

## Why Use Migrations Instead of Auto-Creation?

While SQLAlchemy can automatically create tables, **migrations are strongly recommended** for the following reasons:

### 1. **Version Control**
- Track all schema changes over time
- See exactly what changed and when
- Review schema changes in pull requests

### 2. **Data Safety**
- Migrations can handle data transformations
- Can migrate existing data when schema changes
- Example: Renaming a column while preserving data

### 3. **Production Safety**
- Never auto-modify production databases
- Explicit control over when changes are applied
- Can test migrations before applying

### 4. **Rollback Capability**
- Can revert schema changes if needed
- Track migration history
- Rollback to previous schema version

### 5. **Team Collaboration**
- Everyone applies the same migrations
- Consistent database state across environments
- No "works on my machine" issues

### 6. **Complex Changes**
- Can add indexes, constraints, triggers
- Handle data migrations (e.g., backfill new columns)
- Support for database-specific features

## Automatic Table Creation (Development)

For quick development and prototyping, you can enable automatic table creation:

### Enable Auto-Creation

Add to your `.env` file:
```env
AUTO_CREATE_TABLES=True
ENVIRONMENT=development
```

The server will automatically create all tables on startup if they don't exist.

**⚠️ WARNING:** This is disabled in production for safety. Never enable in production!

### Manual Table Creation

You can also create tables manually:

```bash
cd backend
python -m app.infrastructure.database.init_db
```

## Alembic Migrations (Recommended for Production)

Alembic is already installed (`alembic==1.12.1` in requirements.txt), but not yet configured.

### Setting Up Alembic

1. **Initialize Alembic** (if not already done):
```bash
cd backend
alembic init migrations
```

2. **Configure `alembic.ini`**:
   - Set `sqlalchemy.url` to your database URL
   - Or use environment variable: `sqlalchemy.url = ${DATABASE_URL}`

3. **Configure `migrations/env.py`**:
   - Import your models and Base
   - Set `target_metadata = Base.metadata`

4. **Create Initial Migration**:
```bash
alembic revision --autogenerate -m "Initial schema"
```

5. **Apply Migrations**:
```bash
alembic upgrade head
```

### Migration Workflow

1. **Modify your ORM models** (e.g., add a column)
2. **Generate migration**:
   ```bash
   alembic revision --autogenerate -m "Add new column to users"
   ```
3. **Review the generated migration** (in `migrations/versions/`)
4. **Apply migration**:
   ```bash
   alembic upgrade head
   ```
5. **Commit both model changes and migration file** to git

## Current Setup

Currently, the backend uses:
- **Manual SQL schema**: `database_schema.sql` (for initial setup)
- **Alembic installed** but not configured
- **No automatic creation** by default

## Recommended Approach

1. **Development**: Use `AUTO_CREATE_TABLES=True` for quick iteration
2. **Staging/Production**: Use Alembic migrations for controlled schema changes
3. **Initial Setup**: Run `database_schema.sql` or use Alembic's initial migration

## Files

- `init_db.py` - Automatic table creation utility
- `database_schema.sql` - Manual SQL schema (for reference)
- `migrations/` - Alembic migration files (when configured)
- `base.py` - SQLAlchemy Base class
- `models/` - ORM model definitions
