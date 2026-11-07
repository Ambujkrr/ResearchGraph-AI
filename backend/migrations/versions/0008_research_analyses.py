"""Persist evidence snapshots and analysis outcomes."""
from alembic import op
import sqlalchemy as sa
revision='0008_research_analyses'
down_revision='0007_candidate_evidence'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('research_analyses',sa.Column('id',sa.Integer,primary_key=True),sa.Column('experiment_id',sa.Integer,sa.ForeignKey('gnn_experiments.id'),nullable=False),sa.Column('source_id',sa.Integer,sa.ForeignKey('papers.id'),nullable=False),sa.Column('target_id',sa.Integer,sa.ForeignKey('papers.id'),nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('config',sa.JSON,nullable=False),sa.Column('evidence',sa.JSON),sa.Column('synthesis',sa.JSON),sa.Column('provider',sa.String(100),nullable=False,server_default='deterministic'),sa.Column('model_name',sa.String(255)),sa.Column('error',sa.Text),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
def downgrade(): op.drop_table('research_analyses')
