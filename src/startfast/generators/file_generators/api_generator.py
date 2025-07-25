"""
API Generator
Generates API endpoints and routers
"""

from ...generators.base_generator import BaseGenerator
from ...core.config import ProjectType, AuthType


class APIGenerator(BaseGenerator):
    """Generates API endpoints"""

    def generate(self):
        """Generate API files"""
        # Generate main endpoints
        endpoints_content = self._get_endpoints_template()
        self.write_file(
            f"{self.config.path}/app/api/v1/endpoints.py", endpoints_content
        )

        # Generate auth endpoints if authentication is enabled
        if self.config.auth_type != AuthType.NONE:
            auth_endpoints_content = self._get_auth_endpoints_template()
            self.write_file(
                f"{self.config.path}/app/api/v1/auth.py", auth_endpoints_content
            )

        # Generate __init__.py that exports the router
        init_content = self._get_init_template()
        self.write_file(f"{self.config.path}/app/api/v1/__init__.py", init_content)

    def _get_endpoints_template(self) -> str:
        """Get main endpoints template"""
        template = '''"""
Main API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
{auth_imports}
{database_imports}

router = APIRouter()

{auth_endpoints_include}

@router.get("/")
async def root():
    """Root endpoint"""
    return {{"message": "Welcome to {project_name} API", "version": "1.0.0"}}


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {{"status": "healthy", "service": "{project_name}"}}

{project_specific_endpoints}
'''

        # Customize based on configuration
        auth_imports = ""
        auth_endpoints_include = ""
        database_imports = ""
        project_specific_endpoints = ""

        if self.config.auth_type != AuthType.NONE:
            auth_imports = "from app.core.security import get_current_user"
            auth_endpoints_include = (
                ""  # Add database imports based on database type and auth type
            )
        if self.config.auth_type == AuthType.JWT:
            if self.should_generate_sqlalchemy_files():
                # SQL database imports
                if self.config.is_async:
                    database_imports = "from app.db.database import get_db\nfrom sqlalchemy.ext.asyncio import AsyncSession\nfrom app.models.auth import User"
                else:
                    database_imports = "from app.db.database import get_db\nfrom sqlalchemy.orm import Session\nfrom app.models.auth import User"
            elif self.config.database_type.value == "redis":
                # Redis imports
                database_imports = "from app.schemas.auth import User"
            elif self.config.database_type.value == "mongodb":
                # MongoDB imports
                database_imports = "from app.schemas.auth import User"

        # Add project-specific endpoints
        if self.config.project_type == ProjectType.ML_API:
            project_specific_endpoints = self._get_ml_endpoints()
        elif self.config.project_type == ProjectType.MICROSERVICE:
            project_specific_endpoints = self._get_microservice_endpoints()

        return template.format(
            project_name=self.get_template_vars()["project_name"],
            auth_imports=auth_imports,
            auth_endpoints_include=auth_endpoints_include,
            database_imports=database_imports,
            project_specific_endpoints=project_specific_endpoints,
        )

    def _get_ml_endpoints(self) -> str:
        """Get ML API specific endpoints"""
        return '''
@router.post("/predict")
async def predict(
    input_data: dict
):
    """Make ML prediction"""
    from app.services.prediction_service import make_prediction
    try:
        result = await make_prediction(input_data)
        return {{"prediction": result, "status": "success"}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/model/info")
async def get_model_info(
):
    """Get ML model information"""
    return {{
        "model_name": "DefaultModel",
        "version": "1.0.0",
        "description": "Machine Learning model for predictions"
    }}
'''.format(
            has_auth=self.config.auth_type != AuthType.NONE
        )

    def _get_microservice_endpoints(self) -> str:
        """Get microservice specific endpoints"""
        return '''
@router.get("/status")
async def service_status():
    """Get service status"""
    return {{
        "service": "{project_name}",
        "status": "running",
        "version": "1.0.0"
    }}


@router.post("/process")
async def process_data(
    data: dict,
    current_user: User = Depends(get_current_user) if {has_auth} else None
):
    """Process data"""
    from app.services.processing_service import process_data
    try:
        result = await process_data(data)
        return {{"result": result, "status": "processed"}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
'''.format(
            project_name=self.config.name,
            has_auth=self.config.auth_type != AuthType.NONE,
        )

    def _get_auth_endpoints_template(self) -> str:
        """Get authentication endpoints template"""
        if self.config.auth_type == AuthType.OAUTH2:
            return self._get_oauth2_auth_endpoints()
        elif self.config.auth_type == AuthType.JWT:
            return self._get_jwt_auth_endpoints()
        elif self.config.auth_type == AuthType.API_KEY:
            return self._get_api_key_auth_endpoints()
        return ""

    def _get_jwt_auth_endpoints(self) -> str:
        """Get JWT authentication endpoints"""
        if self.config.database_type.value == "redis":
            return self._get_jwt_redis_auth_endpoints()

        # Original SQL-based JWT auth endpoints
        if self.config.is_async:
            session_import = "from sqlalchemy.ext.asyncio import AsyncSession"
            session_type = "AsyncSession"
            await_keyword = "await "
        else:
            session_import = "from sqlalchemy.orm import Session"
            session_type = "Session"
            await_keyword = ""

        return f'''"""
JWT Authentication Endpoints
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
{session_import}
from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import Token, UserLogin, UserCreate, User as UserSchema
from app.core.security import authenticate_user, create_access_token, get_current_user, create_user

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(
    user_credentials: UserLogin,
    db: {session_type} = Depends(get_db)
):
    """Login endpoint to get access token"""
    user = {await_keyword}authenticate_user(db, user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={{"WWW-Authenticate": "Bearer"}},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={{"sub": user.id}}, expires_delta=access_token_expires
    )

    return {{"access_token": access_token, "token_type": "bearer"}}


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: {session_type} = Depends(get_db)
):
    """Register new user"""
    # Check if user already exists
    from app.core.security import get_user_by_email
    existing_user = {await_keyword}get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = {await_keyword}create_user(db, user_data.email, user_data.password)
    return user


@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@router.put("/me", response_model=UserSchema)
async def update_user_me(
    user_update: dict,
    current_user: UserSchema = Depends(get_current_user),
    db: {session_type} = Depends(get_db)
):      """Update current user information"""
    # Implementation for updating user profile
    # This is a placeholder - implement based on your needs
    return current_user
'''

    def _get_jwt_redis_auth_endpoints(self) -> str:
        """Get JWT authentication endpoints for Redis"""
        if self.config.is_async:
            await_keyword = "await "
            async_keyword = "async "
        else:
            await_keyword = ""
            async_keyword = ""

        template = f'''"""
JWT Authentication Endpoints with Redis
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.config import settings
from app.schemas.auth import Token, UserLogin, UserCreate, User as UserSchema
from app.core.security import authenticate_user, create_access_token, get_current_user

router = APIRouter()


@router.post("/token", response_model=Token)
{async_keyword}def login_for_access_token(user_credentials: UserLogin):
    """Login endpoint to get access token"""
    user = {await_keyword}authenticate_user(user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={{"WWW-Authenticate": "Bearer"}},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={{"sub": user.email}}, expires_delta=access_token_expires
    )
    return {{"access_token": access_token, "token_type": "bearer"}}


@router.post("/register", response_model=UserSchema)
{async_keyword}def register_user(user_data: UserCreate):
    """Register new user"""
    # TODO: Implement your Redis user registration logic here
    # Use the Redis service for data storage:
    # from app.services.redis_service import redis_service
    # 
    # Example implementation:
    # 1. Check if user already exists: {await_keyword}redis_service.exists(f"user:{{user_data.email}}")
    # 2. Hash the password: hashed_password = hash_password(user_data.password)
    # 3. Store user data: {await_keyword}redis_service.hset(f"user:{{user_data.email}}", "profile", user_data.dict())
    # 4. Return the created user
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User registration not implemented. Please implement your Redis user logic."
    )


@router.get("/me", response_model=UserSchema)
{async_keyword}def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@router.put("/me", response_model=UserSchema)
{async_keyword}def update_user_me(
    user_update: dict,
    current_user: UserSchema = Depends(get_current_user)
):    
    """Update current user information"""
    # TODO: Implement your Redis user update logic here
    # Use the Redis service for data operations:
    # from app.services.redis_service import redis_service
    # 
    # Example implementation:
    # 1. Update user data: {await_keyword}redis_service.hset(f"user:{{current_user.email}}", "profile", updated_data)
    # 2. Return the updated user object
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User update not implemented. Please implement your Redis user logic."
    )
'''
        return template

    def _get_oauth2_auth_endpoints(self) -> str:
        """Get OAuth2 authentication endpoints"""
        if self.should_generate_sqlalchemy_files():
            # OAuth2 with database backend
            if self.config.is_async:
                return self._get_oauth2_with_db_async_endpoints()
            else:
                return self._get_oauth2_with_db_sync_endpoints()
        else:
            # OAuth2 without database (simple implementation)
            return self._get_oauth2_simple_endpoints()

    def _get_oauth2_with_db_async_endpoints(self) -> str:
        """Get OAuth2 endpoints with async database support"""
        return '''"""
OAuth2 Authentication Endpoints with Database
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import Token, UserCreate, User as UserSchema
from app.core.security import (
    authenticate_user, 
    create_access_token, 
    get_current_active_user,
    get_user_by_email,
    create_user
)

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """OAuth2 compatible token login, get an access token for future requests"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register new user"""
    # Check if user already exists
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = await create_user(db, user_data.email, user_data.password)
    return user


@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user


@router.put("/me", response_model=UserSchema)
async def update_user_me(
    user_update: dict,
    current_user: UserSchema = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):    
    """Update current user information"""
    # Implementation for updating user profile
    # This is a placeholder - implement based on your needs
    return current_user
'''

    def _get_oauth2_with_db_sync_endpoints(self) -> str:
        """Get OAuth2 endpoints with sync database support"""
        return '''"""
OAuth2 Authentication Endpoints with Database
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import Token, UserCreate, User as UserSchema
from app.core.security import (
    authenticate_user, 
    create_access_token, 
    get_current_active_user,
    get_user_by_email,
    create_user
)

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 compatible token login, get an access token for future requests"""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Register new user"""
    # Check if user already exists
    existing_user = get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = create_user(db, user_data.email, user_data.password)
    return user


@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user


@router.put("/me", response_model=UserSchema)
async def update_user_me(
    user_update: dict,
    current_user: UserSchema = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):    
    """Update current user information"""
    # Implementation for updating user profile
    # This is a placeholder - implement based on your needs
    return current_user
'''

    def _get_oauth2_simple_endpoints(self) -> str:
        """Get simple OAuth2 endpoints without database"""
        return f'''"""
OAuth2 Authentication Endpoints (Simple)
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.config import settings
from app.core.security import (
    authenticate_user, 
    create_access_token, 
    get_current_active_user
)

router = APIRouter()


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 compatible token login, get an access token for future requests"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    """Get current user information"""
    return {"username": current_user["username"], "email": current_user["email"]}


@router.post("/logout")
async def logout():
    """Logout endpoint"""
    # OAuth2 logout logic would be implemented here
    # This depends on your OAuth2 provider (Google, GitHub, Auth0, etc.)
    return {"message": "Logout successful"}
'''

    def _get_api_key_auth_endpoints(self) -> str:
        """Get API Key authentication endpoints"""
        return '''"""
API Key Authentication Endpoints
"""

from fastapi import APIRouter, Depends
from app.core.security import get_api_key

router = APIRouter()


@router.get("/verify")
async def verify_api_key(api_key: str = Depends(get_api_key)):
    """Verify API key"""
    return {"message": "API key is valid", "api_key": api_key[:8] + "***"}
'''

    def _get_init_template(self) -> str:
        """Get __init__.py template that exports the router"""
        from ...core.config import AuthType

        if self.config.auth_type != AuthType.NONE:
            template = '''"""
API v1 Router
"""

from fastapi import APIRouter
from .endpoints import router as endpoints_router
from .auth import router as auth_router

router = APIRouter()
router.include_router(endpoints_router)
router.include_router(auth_router, prefix="/auth", tags=["authentication"])
'''
        else:
            template = '''"""
API v1 Router
"""

from .endpoints import router
'''

        return template
