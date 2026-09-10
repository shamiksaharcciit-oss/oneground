# adapters/

One directory per engine, all implementing the same `VectorEngine` protocol.
oneground has no engine of its own and no favourite: every engine sits behind
this one adapter protocol, so finalists from simulation can be verified against
the real thing on equal terms. Adapters have a contract, so each one carries
conformance tests. Adapters never send a user's vectors anywhere.
