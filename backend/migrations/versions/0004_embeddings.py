"""Store model-versioned 384-dimensional vectors."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
revision='0004_embeddings'
down_revision='0003_graph_foundation'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('paper_embeddings',sa.Column('paper_id',sa.Integer,sa.ForeignKey('papers.id',ondelete='CASCADE'),primary_key=True),sa.Column('model_name',sa.String(255),primary_key=True),sa.Column('model_revision',sa.String(64),primary_key=True),sa.Column('content_hash',sa.String(64),nullable=False),sa.Column('vector',Vector(384),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))

def downgrade(): op.drop_table('paper_embeddings')
