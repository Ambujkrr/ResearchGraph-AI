"""Add resumable collection checkpoints."""
from alembic import op
import sqlalchemy as sa
revision='0005_collection'
down_revision='0004_embeddings'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('collection_jobs',sa.Column('id',sa.Integer,primary_key=True),sa.Column('topic',sa.String(200),nullable=False),sa.Column('target',sa.Integer,nullable=False),sa.Column('processed',sa.Integer,nullable=False,server_default='0'),sa.Column('next_page',sa.Integer,nullable=False,server_default='1'),sa.Column('status',sa.String(20),nullable=False),sa.Column('error',sa.Text()),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
def downgrade(): op.drop_table('collection_jobs')
