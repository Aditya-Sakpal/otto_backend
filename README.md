# Otto AI Backend v2

A clean, scalable, production-ready backend for an AI-powered Revenue Intelligence platform.

## Architecture

This backend follows **Clean Architecture** and **Domain-Driven Design** principles:

```
backend/
├── app/
│   ├── routes/           # API routes (thin layer)
│   ├── core/             # Core configuration, dependencies
│   ├── domain/           # Domain models, enums, value objects
│   ├── infrastructure/   # External integrations (DB, Shoonya, Vector DB)
│   ├── services/         # Business logic orchestration
│   └── tasks/            # Background job definitions
├── tests/                # Test suite
└── requirements.txt      # Dependencies
```

## Key Design Principles

1. **Separation of Concerns**: Routes → Services → Repositories → Database
2. **Dependency Inversion**: Services depend on abstractions, not implementations
3. **Domain-Driven Design**: Business logic lives in domain models and services
4. **Stage-Based Authorization**: No hardcoded roles; uses stage-based responsibility mapping
5. **Async-First**: All I/O operations are async
6. **Testable**: Every layer can be tested in isolation

## Tech Stack

- Python 3.11+
- FastAPI
- Async SQLAlchemy 2.x
- PostgreSQL
- Pydantic v2
- JWT Authentication (email/password based)
- Shoonya/UWC (AI/ML)
- Vector DB abstraction (Pinecone/Weaviate/PGVector)

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file in the `backend` directory:

```env
# Application Environment
APP_ENV=DEV  # or PROD for production

# Database
DATABASE_URL=sqlite+aiosqlite:///./otto.db  # or PostgreSQL connection string

# JWT Configuration (for token signing)
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Shoonya/UWC Integration (optional)
UWC_BASE_URL=https://...
UWC_API_KEY=...
UWC_HMAC_SECRET=...

# Other configurations...
```

### 3. Start the Server

```bash
uvicorn app.main:app --reload --port 8001
```

The API will be available at `http://127.0.0.1:8001` with interactive docs at `http://127.0.0.1:8001/docs`.

## Authentication

### Overview

The backend uses **JWT-based authentication** with email/password. Users can sign up and log in, receiving JWT tokens for authenticated requests.

### Environment Modes

#### DEV Mode (`APP_ENV=DEV`)

- ✅ **No JWT token required** - All requests work without authentication
- ✅ **Mock user returned** - A default dev user is automatically used
- ✅ **Mock company returned** - A default dev company is automatically used
- ✅ **All endpoints accessible** - No 401/403 errors

**Mock User Details:**
- Email: `dev@example.com`
- Name: `Dev User`
- Roles: `CSR`, `SALES_REP`
- Company: `Dev Company`

**Usage:**
```bash
# Set in .env
APP_ENV=DEV

# Test without tokens
curl http://127.0.0.1:8001/api/v1/auth/me
```

#### PROD Mode (`APP_ENV=PROD`)

- 🔒 **JWT token required** - All protected endpoints require valid JWT access token
- 🔒 **Real authentication** - Uses email/password authentication
- 🔒 **Security enforced** - 401/403 errors for unauthorized requests

**Usage:**
```bash
# Set in .env
APP_ENV=PROD
JWT_SECRET_KEY=your-secret-key-change-in-production

# First signup/login to get a token
curl -X POST http://127.0.0.1:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# Use the access_token from response in subsequent requests
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://127.0.0.1:8001/api/v1/auth/me
```

### Endpoints Behavior

#### Always Public (No Auth Required)
- `GET /health` - Health check
- `POST /api/v1/webhooks/*` - Webhook endpoints

#### Protected Endpoints (Auth behavior depends on APP_ENV)

| Endpoint | DEV Mode | PROD Mode |
|----------|----------|-----------|
| `GET /api/v1/auth/me` | ✅ Works (mock user) | 🔒 Requires JWT |
| `GET /api/v1/auth/verify` | ✅ Works (mock user) | 🔒 Requires JWT |
| `GET /api/v1/calls` | ✅ Works (mock company) | 🔒 Requires JWT + Company |
| `GET /api/v1/calls/{id}` | ✅ Works (mock company) | 🔒 Requires JWT + Company |
| `POST /api/v1/rag/ask-otto` | ✅ Works (mock company) | 🔒 Requires JWT + Company |

### Security Warnings

⚠️ **IMPORTANT:**

1. **Never use DEV mode in production** - Always set `APP_ENV=PROD` in production
2. **Mock user has full access** - In DEV mode, all endpoints are accessible
3. **No real data isolation** - Mock user/company may access all data
4. **Check environment** - Verify `APP_ENV` before deploying

## Testing with Postman

### Import Collection

1. Open Postman
2. Click **Import** button
3. Select `postman_collection.json` from the `backend` directory
4. The collection will be imported with default variables

### Configure Variables

1. Click on **Otto AI Backend v2** collection
2. Go to **Variables** tab
3. Set the following variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `base_url` | `http://127.0.0.1:8001` | Your backend URL |
| `access_token` | `your_token_here` | JWT access token (see below) |
| `company_id` | (auto-filled) | Will be populated after first auth call |
| `call_id` | (auto-filled) | Will be populated after creating a call |

### Getting JWT Token for Postman

#### Signup/Login to Get Token

1. **Signup** (first time):
   ```bash
   curl -X POST http://127.0.0.1:8001/api/v1/auth/signup \
     -H "Content-Type: application/json" \
     -d '{
       "email": "user@example.com",
       "password": "password123",
       "first_name": "John",
       "last_name": "Doe"
     }'
   ```

2. **Login** (if already have account):
   ```bash
   curl -X POST http://127.0.0.1:8001/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{
       "email": "user@example.com",
       "password": "password123"
     }'
   ```

3. Copy the `access_token` from the response
4. Paste it into Postman's `access_token` variable

### Postman Setup by Mode

#### DEV Mode Setup

1. Set `APP_ENV=DEV` in your `.env` file
2. In Postman, you can **remove** the `access_token` variable or leave it empty
3. All requests will work without authentication

#### PROD Mode Setup

1. Set `APP_ENV=PROD` in your `.env` file
2. In Postman, set `access_token` with a valid JWT access token (from login/signup)
3. All requests require the token in the Authorization header

### Postman Test Scripts

#### Auto-Extract Company ID

Add this to **Auth → Get Current User Info** → **Tests** tab:

```javascript
// Extract company_id from response
if (pm.response.code === 200) {
    const response = pm.response.json();
    if (response.company && response.company.id) {
        pm.collectionVariables.set("company_id", response.company.id);
        console.log("Company ID set:", response.company.id);
    }
}
```

#### Automatic Token Refresh (Advanced)

You can use the refresh token endpoint to get new access tokens:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your_refresh_token"}'
```

## API Endpoints

### Authentication

- `GET /api/v1/auth/me` - Get current user info
- `GET /api/v1/auth/verify` - Verify JWT token

### Calls

- `GET /api/v1/calls?company_id={uuid}&skip=0&limit=100` - List calls for a company (with pagination)
  - `company_id` (required): UUID of the company to retrieve calls for
  - `skip` (optional, default=0): Number of records to skip for pagination
  - `limit` (optional, default=100): Maximum number of records to return
- `GET /api/v1/calls/{call_id}` - Get call by ID
  - `call_id` (path parameter): UUID of the call to retrieve (unique identifier)

### Webhooks

- `POST /api/v1/webhooks/telephony/call-complete` - Call completion webhook
- `POST /api/v1/webhooks/shoonya/job-complete` - Shoonya job completion

### RAG / Ask Otto

- `POST /api/v1/rag/ask-otto` - Query Ask Otto AI copilot

### Health

- `GET /health` - Health check endpoint

See `postman_collection.json` for complete request examples with sample data.

## Development

### Project Structure

- **Domain Models**: `app/domain/models/`
- **Repositories**: `app/infrastructure/repositories/`
- **Services**: `app/services/`
- **API Routes**: `app/routes/v1/`
- **Database Models**: `app/infrastructure/database/models/`

### Code Implementation

The authentication bypass is implemented in `app/core/dependencies.py`:

```python
async def require_auth(request: Request) -> User:
    # DEV mode: bypass authentication
    if settings.is_dev_mode:
        return get_mock_user()
    
    # PROD mode: require JWT token
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
```

## Environment Variables

### Required Variables

```env
# Application Environment (DEV or PROD)
APP_ENV=DEV

# Database
DATABASE_URL=sqlite+aiosqlite:///./otto.db
```

### Required for PROD Mode

```env
APP_ENV=PROD
CLERK_SECRET_KEY=sk_test_...
CLERK_ISSUER=https://your-clerk-instance.clerk.accounts.dev
CLERK_API_URL=https://api.clerk.dev/v1
```

### Optional Variables

```env
# Shoonya/UWC
UWC_BASE_URL=https://...
UWC_API_KEY=...
UWC_HMAC_SECRET=...

# Vector DB
VECTOR_DB_PROVIDER=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=otto-embeddings

# OpenAI (fallback LLM)
OPENAI_API_KEY=...

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS
ALLOWED_ORIGINS=http://localhost:3000
ALLOWED_HOSTS=*
```

## Troubleshooting

### Authentication Issues

#### Issue: Still getting 401 errors in DEV mode

**Solution:**
1. Check `APP_ENV` is set to `DEV` (case-insensitive)
2. Restart the server after changing `.env`
3. Verify in logs: Should see "DEV mode: Using mock user"

#### Issue: Not requiring auth in PROD mode

**Solution:**
1. Check `APP_ENV` is set to `PROD` (case-insensitive)
2. Verify `JWT_SECRET_KEY` is configured
3. Restart the server

#### Issue: Token not working in Postman

**Checklist:**
- ✅ Token is set in collection variables
- ✅ Token is not expired (tokens expire after configured time - default 30 minutes)
- ✅ Token format is correct (should start with `eyJ...`)
- ✅ Backend has `JWT_SECRET_KEY` configured
- ✅ Token signature is valid
- ✅ `APP_ENV=PROD` is set (if testing with real tokens)

#### Issue: 403 Forbidden

**Problem:** User doesn't have required permissions or company association.

**Solutions:**
1. Ensure the user is associated with a company
2. Check user role in the database
3. Verify company_id is correct
4. In DEV mode, mock company is automatically provided

### Database Issues

#### Issue: Connection errors

**Solution:**
1. Verify `DATABASE_URL` is correct
2. Check database server is running
3. Verify credentials are correct

### General Issues

#### Issue: Module not found

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

#### Issue: Server won't start

**Solution:**
1. Check all required environment variables are set
2. Verify Python version is 3.11+
3. Check port 8001 is not in use
4. Review server logs for specific errors

## Testing

### Run Tests

```bash
pytest tests/
```

### Test Authentication Modes

You can test the behavior programmatically:

```python
from app.core.config import settings
from app.core.dependencies import get_mock_user

# Check mode
print(f"APP_ENV: {settings.APP_ENV}")
print(f"Is DEV mode: {settings.is_dev_mode}")
print(f"Is PROD mode: {settings.is_prod_mode}")

# Get mock user
if settings.is_dev_mode:
    mock_user = get_mock_user()
    print(f"Mock user: {mock_user.email}")
```

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never use DEV mode in production** - Always set `APP_ENV=PROD` in production
2. **Never commit tokens to version control** - Use environment variables
3. **Rotate tokens regularly** in production
4. **Use different tokens** for different environments (dev/staging/prod)
5. **Token expiration**: Access tokens expire after the configured time (default 30 minutes) - use refresh token endpoint to get new tokens
6. **Check environment** - Verify `APP_ENV` before deploying

## Additional Resources

- **API Documentation**: Visit `http://127.0.0.1:8001/docs` for interactive Swagger UI
- **Postman Collection**: Import `postman_collection.json` for complete API testing
