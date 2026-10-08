import os, sys, tempfile
os.environ["EMBEDDING_BACKEND"] = "hash"
os.environ["CHROMA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
