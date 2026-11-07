import os
import subprocess
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# 1. Parse DATABASE_URL and explicitly set database to researchgraph_test
orig_url = make_url(os.environ['DATABASE_URL'])
test_url = orig_url.set(database='researchgraph_test')

# 2. Fail-closed assertion: database must be exactly researchgraph_test
assert test_url.database == 'researchgraph_test', f"Safety check failed: database is {test_url.database}"
assert test_url.database != orig_url.database, "Safety check failed: test database cannot match original database"

# 3. Verify connection, active database name, and Alembic migration head
test_conn_str = test_url.render_as_string(hide_password=False)
engine = create_engine(test_conn_str)
with engine.connect() as conn:
    active_db = conn.scalar(text("SELECT current_database()"))
    assert active_db == 'researchgraph_test', f"Safety check failed: active DB is {active_db}"
    alembic_head = conn.scalar(text("SELECT version_num FROM alembic_version"))
    assert alembic_head == '0009_generation_attempts', f"Safety check failed: migration head is {alembic_head}"
    print(f"Safety check PASSED: database '{active_db}' verified at Alembic head '{alembic_head}'.", flush=True)

# 4. Prepare isolated test environment
# Unset remote provider keys so tests run fully self-contained and don't make real API calls
env = os.environ.copy()
env['DATABASE_URL'] = test_conn_str
env['PYTHONPATH'] = '/app'
env['RUN_MODEL_TESTS'] = '1'
env['GEMINI_API_KEY'] = ''
env['GEMINI_FREE_TIER_CONFIRMED'] = 'false'

print("Executing full backend pytest suite (RUN_MODEL_TESTS=1) in isolated test environment...", flush=True)
res = subprocess.run(['pytest', 'tests/', '-v'], env=env, cwd='/app')
sys.exit(res.returncode)
