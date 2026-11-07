"""Enable vector support and create the initial paper table."""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("papers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("openalex_id", sa.String(255), nullable=False), sa.Column("title", sa.Text(), nullable=False), sa.Column("abstract", sa.Text()), sa.Column("publication_date", sa.Date()), sa.Column("doi", sa.String(512)))
    op.create_index("ix_papers_openalex_id", "papers", ["openalex_id"], unique=True)


def downgrade():
    op.drop_index("ix_papers_openalex_id", table_name="papers")
    op.drop_table("papers")
    # Keep the shared vector extension; other tables may depend on it.
