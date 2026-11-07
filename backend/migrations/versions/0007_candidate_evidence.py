"""Add transparent training-graph evidence and baseline ranks to candidates."""
from alembic import op
import sqlalchemy as sa
revision='0007_candidate_evidence'
down_revision='0006_gnn_experiments'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('gnn_candidate_links',sa.Column('popularity_score',sa.Float(),nullable=True))
    op.add_column('gnn_candidate_links',sa.Column('popularity_rank',sa.Integer(),nullable=True))
    op.add_column('gnn_candidate_links',sa.Column('evidence',sa.JSON(),nullable=True))
def downgrade():
    op.drop_column('gnn_candidate_links','evidence');op.drop_column('gnn_candidate_links','popularity_rank');op.drop_column('gnn_candidate_links','popularity_score')
