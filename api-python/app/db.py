import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/users_db"
)

pool = ConnectionPool(DATABASE_URL, kwargs={"row_factory": dict_row}, open=False)