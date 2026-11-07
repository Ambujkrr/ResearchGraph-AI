"""Persist exploratory experiments and predicted candidate links."""
from alembic import op
import sqlalchemy as sa
revision='0006_gnn_experiments'
down_revision='0005_collection'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('gnn_experiments',sa.Column('id',sa.Integer,primary_key=True),sa.Column('status',sa.String(24),nullable=False),sa.Column('config',sa.JSON,nullable=False),sa.Column('metrics',sa.JSON),sa.Column('dataset_hash',sa.String(64)),sa.Column('error',sa.Text),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_table('gnn_candidate_links',sa.Column('experiment_id',sa.Integer,sa.ForeignKey('gnn_experiments.id',ondelete='CASCADE'),primary_key=True),sa.Column('source_id',sa.Integer,sa.ForeignKey('papers.id'),primary_key=True),sa.Column('target_id',sa.Integer,sa.ForeignKey('papers.id'),primary_key=True),sa.Column('rank',sa.Integer,nullable=False),sa.Column('score',sa.Float,nullable=False))

def downgrade():
    op.drop_table('gnn_candidate_links');op.drop_table('gnn_experiments')
