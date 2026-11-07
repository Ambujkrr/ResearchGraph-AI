"""Track hosted generation attempts for a bounded daily request budget."""
from alembic import op
import sqlalchemy as sa
revision='0009_generation_attempts'
down_revision='0008_research_analyses'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('generation_attempts',sa.Column('id',sa.Integer,primary_key=True),sa.Column('analysis_id',sa.Integer,sa.ForeignKey('research_analyses.id'),nullable=False),sa.Column('provider',sa.String(40),nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
def downgrade():op.drop_table('generation_attempts')
