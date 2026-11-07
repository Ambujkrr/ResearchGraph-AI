"""Add normalized topics, authors and source-backed citation relationships."""
from alembic import op
import sqlalchemy as sa
revision='0003_graph_foundation'
down_revision='0002_ingestion'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('topics',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(200),nullable=False),sa.Column('normalized_name',sa.String(200),nullable=False,unique=True))
    op.create_table('authors',sa.Column('id',sa.Integer,primary_key=True),sa.Column('openalex_id',sa.String(255),unique=True),sa.Column('name',sa.Text,nullable=False))
    op.create_table('paper_topics',sa.Column('paper_id',sa.Integer,sa.ForeignKey('papers.id',ondelete='CASCADE'),primary_key=True),sa.Column('topic_id',sa.Integer,sa.ForeignKey('topics.id',ondelete='CASCADE'),primary_key=True),sa.Column('provenance',sa.String(40),nullable=False,server_default='ingestion_query'))
    op.create_table('paper_authors',sa.Column('paper_id',sa.Integer,sa.ForeignKey('papers.id',ondelete='CASCADE'),primary_key=True),sa.Column('author_id',sa.Integer,sa.ForeignKey('authors.id',ondelete='CASCADE'),primary_key=True),sa.Column('position',sa.Integer,nullable=False),sa.Column('provenance',sa.String(40),nullable=False,server_default='openalex'))
    op.create_table('paper_citations',sa.Column('citing_id',sa.Integer,sa.ForeignKey('papers.id',ondelete='CASCADE'),primary_key=True),sa.Column('cited_openalex_id',sa.String(255),primary_key=True),sa.Column('provenance',sa.String(40),nullable=False,server_default='openalex'))
    op.execute("INSERT INTO topics (name,normalized_name) SELECT min(trim(topic)),lower(trim(topic)) FROM papers WHERE topic IS NOT NULL AND trim(topic) <> '' GROUP BY lower(trim(topic))")
    op.execute("INSERT INTO paper_topics (paper_id,topic_id,provenance) SELECT p.id,t.id,'ingestion_query' FROM papers p JOIN topics t ON t.normalized_name=lower(trim(p.topic))")
    # JSON authors without a stable ID remain in the legacy metadata; do not merge by name.
    op.execute("INSERT INTO authors (openalex_id,name) SELECT a->>'openalex_id',min(a->>'name') FROM papers p CROSS JOIN LATERAL json_array_elements(p.authors) a WHERE a->>'openalex_id' ~ '^https://openalex.org/A[0-9]+$' AND coalesce(a->>'name','') <> '' GROUP BY a->>'openalex_id'")
    op.execute("INSERT INTO paper_authors (paper_id,author_id,position,provenance) SELECT DISTINCT ON (p.id,author.id) p.id,author.id,a.ordinality,'openalex' FROM papers p CROSS JOIN LATERAL json_array_elements(p.authors) WITH ORDINALITY a(value,ordinality) JOIN authors author ON author.openalex_id=a.value->>'openalex_id' ORDER BY p.id,author.id,a.ordinality")

def downgrade():
    op.drop_table('paper_citations'); op.drop_table('paper_authors'); op.drop_table('paper_topics'); op.drop_table('authors'); op.drop_table('topics')
