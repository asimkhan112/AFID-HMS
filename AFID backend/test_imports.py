import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from database import engine, Base
import models
import schemas
import auth
from routers import auth as r_auth, patients, doctors, procedures, leaves, staff, hod
print("ALL IMPORTS OK")
print("DB URL:", settings.DATABASE_URL)
