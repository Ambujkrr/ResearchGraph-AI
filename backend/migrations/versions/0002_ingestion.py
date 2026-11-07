"""Add paper metadata and ingestion history without removing existing records."""
from alembic import op
import sqlalchemy as sa
revision = "0002_ingestion"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('papers', sa.Column('normalized_doi', sa.String(512)))
    # Abort rather than silently merge pre-existing DOI collisions.
    op.execute("UPDATE papers SET normalized_doi = NULLIF(lower(regexp_replace(trim(doi), '^(https?://(dx\\.)?doi\\.org/|doi:\\s*)', '', 'i')), '') WHERE doi IS NOT NULL")
    op.create_unique_constraint('uq_papers_normalized_doi', 'papers', ['normalized_doi'])
    op.add_column('papers', sa.Column('publication_year', sa.Integer()))
    op.execute('UPDATE papers SET publication_year = EXTRACT(YEAR FROM publication_date)::integer WHERE publication_date IS NOT NULL')
    op.add_column('papers', sa.Column('authors', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('papers', sa.Column('citation_count', sa.Integer()))
    op.add_column('papers', sa.Column('source_url', sa.Text()))
    op.add_column('papers', sa.Column('topic', sa.String(200)))
    op.add_column('papers', sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column('papers', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table('ingestion_runs', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('topic', sa.String(200), nullable=False), sa.Column('status', sa.String(20), nullable=False), sa.Column('requested', sa.Integer(), nullable=False), sa.Column('saved', sa.Integer(), nullable=False, server_default='0'), sa.Column('error', sa.Text()), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table('ingestion_runs')
    for col in ['updated_at','ingested_at','topic','source_url','citation_count','authors','publication_year']:
        op.drop_column('papers', col)
    op.drop_constraint('uq_papers_normalized_doi','papers',type_='unique')
    op.drop_column('papers','normalized_doi')
