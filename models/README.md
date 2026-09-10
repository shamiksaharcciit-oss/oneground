# models/

One directory per architecture family, each a runnable simulator. A model
simulates a retrieval architecture on a corpus of embeddings against exact
k-NN ground truth, so an architecture can be scored before any real engine is
stood up. Models are measured on the user's own vectors — never on a canned
dataset — and no architecture here is a default or a favourite.
