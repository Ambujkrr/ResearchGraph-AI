"""Opt-in integration test: downloads/loads the pinned local model."""
import os
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('RUN_MODEL_TESTS')!='1',reason='Set RUN_MODEL_TESTS=1 to exercise the real CPU model')

def test_real_model_is_repeatable_and_orders_similarity():
    import numpy as np
    from app.services.embeddings import encode, DIMENSION
    vectors=encode(['graph neural networks','graph neural networks','banana recipes'])
    assert len(vectors[0])==DIMENSION==384
    assert np.allclose(vectors[0],vectors[1],atol=1e-6)
    assert np.dot(vectors[0],vectors[1])>np.dot(vectors[0],vectors[2])
